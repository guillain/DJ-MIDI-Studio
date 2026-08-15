"""MIDI Clock mirror policy, independent of physical MIDI ports."""

from __future__ import annotations

from dataclasses import dataclass

from djmidi.midi_api import MidiMessage

_START = 0xFA
_CONTINUE = 0xFB
_STOP = 0xFC
_CLOCK = 0xF8


@dataclass
class ClockStats:
    forwarded: int = 0
    ignored: int = 0
    jitter_dropped: int = 0
    jitter_samples: int = 0
    max_jitter_ms: float = 0.0
    last_interval_ms: float | None = None
    last_message_time: float | None = None
    last_message_status: int | None = None
    last_clock_time: float | None = None


class MidiClockMirror:
    """Forwards realtime Clock messages from one source to destinations."""

    def __init__(
        self,
        source_port_id: str,
        destination_port_ids: list[str],
        *,
        min_clock_interval_ms: float = 0.5,
        expected_interval_ms: float | None = None,
    ) -> None:
        if not source_port_id:
            raise ValueError("Clock source is required")
        if min_clock_interval_ms < 0:
            raise ValueError("minimum Clock interval cannot be negative")
        if expected_interval_ms is not None and expected_interval_ms <= 0:
            raise ValueError("expected Clock interval must be positive")
        if not destination_port_ids:
            raise ValueError("at least one Clock destination is required")
        if source_port_id in destination_port_ids:
            raise ValueError("Clock source cannot target itself")
        if len(set(destination_port_ids)) != len(destination_port_ids):
            raise ValueError("Clock destinations must be unique")
        self.source_port_id = source_port_id
        self.destination_port_ids = tuple(destination_port_ids)
        self.min_clock_interval_ms = min_clock_interval_ms
        self.expected_interval_ms = expected_interval_ms
        self.running = False
        self.stats = ClockStats()
        self._last_clock_time: float | None = None

    def forward(self, message: MidiMessage, send) -> int:
        if message.port_id != self.source_port_id or message.status not in {
            _START,
            _CONTINUE,
            _STOP,
            _CLOCK,
        }:
            self.stats.ignored += 1
            return 0
        self.stats.last_message_time = message.received_time
        self.stats.last_message_status = message.status
        if message.status in {_START, _CONTINUE}:
            self.running = True
            # START begins a new song position; CONTINUE resumes after an
            # arbitrary pause. Neither gap is a Clock-jitter sample.
            self._last_clock_time = None
            self.stats.last_clock_time = None
        elif message.status == _STOP:
            self.running = False
            self._last_clock_time = None
            self.stats.last_clock_time = None
        if message.status == _CLOCK:
            if self._last_clock_time is not None:
                interval_ms = round((message.received_time - self._last_clock_time) * 1000, 6)
                self.stats.last_interval_ms = interval_ms
                if interval_ms < self.min_clock_interval_ms:
                    self._last_clock_time = message.received_time
                    self.stats.last_clock_time = message.received_time
                    self.stats.jitter_dropped += 1
                    return 0
                if self.expected_interval_ms is not None:
                    jitter_ms = abs(interval_ms - self.expected_interval_ms)
                    self.stats.jitter_samples += 1
                    self.stats.max_jitter_ms = max(self.stats.max_jitter_ms, jitter_ms)
            self._last_clock_time = message.received_time
            self.stats.last_clock_time = message.received_time
        count = 0
        for destination in self.destination_port_ids:
            send(destination, message)
            count += 1
        self.stats.forwarded += count
        return count

    def clock_active(self, now: float, *, timeout_s: float = 0.5) -> bool:
        """Return whether a recent Clock tick has arrived from this source."""
        if timeout_s <= 0:
            raise ValueError("Clock activity timeout must be positive")
        last_clock = self.stats.last_clock_time
        return last_clock is not None and now - last_clock <= timeout_s

    def message_active(self, now: float, *, timeout_s: float = 0.5) -> bool:
        """Return whether any accepted realtime message recently arrived."""
        if timeout_s <= 0:
            raise ValueError("Clock activity timeout must be positive")
        last_message = self.stats.last_message_time
        return last_message is not None and now - last_message <= timeout_s


__all__ = ["ClockStats", "MidiClockMirror"]
