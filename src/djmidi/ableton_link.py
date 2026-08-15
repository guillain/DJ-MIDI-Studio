"""Ableton Link follower and MIDI Clock generator.

The Link transport is deliberately isolated behind ``LinkStateProvider``.  This
keeps the scheduler deterministic in tests and lets the desktop build use an
optional native Link binding without making the MIDI engine depend on it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import ceil
from typing import Protocol

from djmidi.midi_api import MidiMessage
from djmidi.midi_clock import ClockStats

ABLETON_LINK_CLOCK_SOURCE_NAME = "Ableton Link (DJ MIDI Studio)"
PPQN = 24


@dataclass(frozen=True)
class LinkState:
    tempo: float
    beat: float
    playing: bool


class LinkStateProvider(Protocol):
    def state_at(self, now: float) -> LinkState: ...

    def close(self) -> None: ...


class LinkBackendUnavailable(RuntimeError):
    """Raised when the optional native Ableton Link binding is not installed."""


class AalinkStateProvider:
    """Small compatibility adapter for the optional ``aalink`` package."""

    def __init__(self, tempo: float = 120.0) -> None:
        try:
            from aalink import Link  # type: ignore[import-not-found]
        except ImportError as exc:
            raise LinkBackendUnavailable(
                "Ableton Link support requires the optional 'aalink' package"
            ) from exc
        self._link = Link(tempo)
        for method in ("enable", "start"):
            callback = getattr(self._link, method, None)
            if callback is not None:
                callback()

    def state_at(self, now: float) -> LinkState:
        capture = getattr(self._link, "captureSessionState", None) or getattr(
            self._link, "capture_session_state", None
        )
        if capture is None:
            raise LinkBackendUnavailable("aalink does not expose session-state capture")
        state = capture()
        tempo = float(state.tempo)
        is_playing = getattr(state, "isPlaying", None) or getattr(state, "is_playing", None)
        playing = bool(is_playing() if callable(is_playing) else is_playing)
        beat_at_time = getattr(state, "beatAtTime", None) or getattr(state, "beat_at_time", None)
        if beat_at_time is None:
            raise LinkBackendUnavailable("aalink does not expose beat-at-time")
        return LinkState(tempo=tempo, beat=float(beat_at_time(now, 4.0)), playing=playing)

    def close(self) -> None:
        for method in ("disable", "stop"):
            callback = getattr(self._link, method, None)
            if callback is not None:
                callback()


class LinkClockFollower:
    """Follows Link tempo/phase and emits standard MIDI Clock at 24 PPQN.

    Link remains authoritative: this class never calls a tempo setter.  The
    provider's monotonic beat position determines tick scheduling, while
    transport transitions generate Start/Continue/Stop exactly once.
    """

    def __init__(
        self,
        destination_port_ids: list[str],
        provider: LinkStateProvider,
        *,
        source_port_id: str = ABLETON_LINK_CLOCK_SOURCE_NAME,
        clock_fn=time.monotonic,
    ) -> None:
        if not destination_port_ids:
            raise ValueError("at least one Link Clock destination is required")
        if len(set(destination_port_ids)) != len(destination_port_ids):
            raise ValueError("Link Clock destinations must be unique")
        self.source_port_id = source_port_id
        self.destination_port_ids = tuple(destination_port_ids)
        self.provider = provider
        self.clock_fn = clock_fn
        self.running = False
        self.stats = ClockStats()
        self._last_playing = False
        self._next_tick: float | None = None
        self._last_tick: float | None = None

    def poll(self, send, *, now: float | None = None) -> int:
        now = self.clock_fn() if now is None else now
        state = self.provider.state_at(now)
        if state.tempo <= 0:
            raise ValueError("Ableton Link tempo must be positive")
        count = 0
        if state.playing and not self._last_playing:
            status = 0xFA if self._next_tick is None else 0xFB
            count += self._emit(status, now, send)
            self.running = True
            # Align the first tick to Link's current beat phase.  A Link beat
            # is a quarter-note by convention here, and MIDI Clock has 24
            # ticks per beat.
            beat_ticks = state.beat * PPQN
            self._next_tick = now + (ceil(beat_ticks - 1e-9) - beat_ticks) * (
                60.0 / state.tempo / PPQN
            )
        elif not state.playing and self._last_playing:
            count += self._emit(0xFC, now, send)
            self.running = False
            self._next_tick = None
        self._last_playing = state.playing
        if not state.playing:
            return count

        interval = 60.0 / state.tempo / PPQN
        if self._next_tick is None:
            self._next_tick = now
        # Bound catch-up after a GUI pause; never emit a burst of stale ticks.
        if now - self._next_tick > interval * 4:
            self._next_tick = now
        while self._next_tick <= now:
            count += self._emit(0xF8, self._next_tick, send)
            self._next_tick += interval
        return count

    def _emit(self, status: int, timestamp: float, send) -> int:
        message = MidiMessage(bytes((status,)), timestamp, self.source_port_id)
        for destination in self.destination_port_ids:
            send(destination, message)
        self.stats.forwarded += len(self.destination_port_ids)
        self.stats.last_message_time = timestamp
        self.stats.last_message_status = status
        if status == 0xF8:
            self.stats.last_clock_time = timestamp
            self._last_tick = timestamp
        return len(self.destination_port_ids)

    def clock_active(self, now: float, *, timeout_s: float = 0.5) -> bool:
        last = self.stats.last_clock_time
        return last is not None and now - last <= timeout_s

    def close(self) -> None:
        self.provider.close()

    def reset(self) -> None:
        """Reset the generated transport boundary for the next routing run."""
        self.running = False
        self._last_playing = False
        self._next_tick = None


__all__ = [
    "ABLETON_LINK_CLOCK_SOURCE_NAME",
    "AalinkStateProvider",
    "LinkBackendUnavailable",
    "LinkClockFollower",
    "LinkState",
    "LinkStateProvider",
]
