"""Deterministic MIDI 1.0 routing primitives, independent of hardware I/O."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from djmidi.midi_api import MidiMessage

_LOGGER = logging.getLogger(__name__)

SendMessage = Callable[[str, MidiMessage], None]


NOTE, CC, BLOCK = "note", "cc", "block"


@dataclass(frozen=True)
class RemapRule:
    """One control of a controller remapped (issue #368): every message of
    the source control -- a note's press and release, or a CC's values --
    leaves as the target control instead, or is dropped (``target_kind``
    ``"block"``). The value is kept: a note's velocity becomes the CC value
    and back, a release (Note Off / velocity 0) becomes value 0. Channels
    are 1-16, data1 0-127."""

    source_kind: str  # NOTE or CC
    source_channel: int
    source_data1: int
    target_kind: str  # NOTE, CC or BLOCK
    target_channel: int = 1
    target_data1: int = 0

    def __post_init__(self) -> None:
        if self.source_kind not in (NOTE, CC) or self.target_kind not in (NOTE, CC, BLOCK):
            raise ValueError("a remap goes from a note or CC to a note, a CC, or nothing")
        for channel in (self.source_channel, self.target_channel):
            if not 1 <= channel <= 16:
                raise ValueError("channels are 1-16")
        for number in (self.source_data1, self.target_data1):
            if not 0 <= number <= 127:
                raise ValueError("note and CC numbers are 0-127")

    def matches(self, message: MidiMessage) -> bool:
        if message.is_sysex or len(message.data) < 3:
            return False
        nibble, channel, data1 = message.status & 0xF0, (message.status & 0x0F) + 1, message.data[1]
        kinds = (0x80, 0x90) if self.source_kind == NOTE else (0xB0,)
        return nibble in kinds and channel == self.source_channel and data1 == self.source_data1

    def apply(self, message: MidiMessage) -> MidiMessage | None:
        if self.target_kind == BLOCK:
            return None
        nibble, value = message.status & 0xF0, message.data[2]
        if nibble == 0x80:
            value = 0  # a release, whatever velocity the Note Off carries
        if self.target_kind == CC:
            status = 0xB0
        else:
            status = 0x90 if value > 0 else 0x80
        status |= self.target_channel - 1
        return replace(message, data=bytes((status, self.target_data1, value)))

    def label(self) -> str:
        """"Note 40 ch 1 → CC 7 ch 2", "Note 40 ch 1 → blocked"."""
        def side(kind: str, channel: int, data1: int) -> str:
            return f"{'Note' if kind == NOTE else 'CC'} {data1} ch {channel}"

        target = "blocked" if self.target_kind == BLOCK else side(self.target_kind, self.target_channel, self.target_data1)
        return f"{side(self.source_kind, self.source_channel, self.source_data1)} → {target}"


@dataclass(frozen=True)
class MidiValueTransform:
    """A small, deterministic per-route value transform.

    Deliberately scoped down from general MIDI-translator tools (e.g. Bome
    MIDI Translator's rule engine): no conditionals, variables, or
    message-type conversion — just the handful of value remaps that come up
    on a DJ controller (mirror a pad to another channel, shift a note/CC
    range, invert a fader/knob direction). Only applies to channel-voice
    messages; SysEx and realtime messages pass through unchanged.
    """

    channel_override: int | None = None
    data1_offset: int = 0
    invert_data2: bool = False
    # Per-control remaps (issue #368), checked first: a message one rule
    # matches leaves as that rule says and skips the stream-wide values.
    remaps: tuple[RemapRule, ...] = ()

    def apply(self, message: MidiMessage) -> MidiMessage | None:
        """The message to send, or None when a remap blocks it."""
        if message.is_sysex or not 0x80 <= message.status <= 0xEF:
            return message
        for rule in self.remaps:
            if rule.matches(message):
                return rule.apply(message)
        data = bytearray(message.data)
        if self.channel_override is not None:
            data[0] = (data[0] & 0xF0) | (self.channel_override - 1)
        if self.data1_offset and len(data) > 1:
            data[1] = max(0, min(127, data[1] + self.data1_offset))
        if self.invert_data2 and len(data) > 2:
            data[2] = 127 - data[2]
        return replace(message, data=bytes(data))


@dataclass(frozen=True)
class MidiRoute:
    source_port_id: str
    destination_port_id: str
    channels: frozenset[int] = frozenset()
    status_nibbles: frozenset[int] = frozenset()
    allow_sysex: bool = False
    enabled: bool = True
    transform: MidiValueTransform | None = None

    def accepts(self, message: MidiMessage) -> bool:
        if message.is_sysex:
            return self.allow_sysex
        status_nibble = message.status & 0xF0
        if self.status_nibbles and status_nibble not in self.status_nibbles:
            return False
        if self.channels:
            if not 0x80 <= message.status <= 0xEF:
                return False
            if (message.status & 0x0F) + 1 not in self.channels:
                return False
        return True


@dataclass
class RouteStats:
    forwarded: int = 0
    dropped: int = 0
    errors: int = 0
    last_latency_ms: float | None = None
    error_messages: list[str] = field(default_factory=list)


class MidiRouter:
    """One-way route graph with explicit filters and loop prevention."""

    def __init__(self) -> None:
        self._routes: list[MidiRoute] = []
        self.stats = RouteStats()

    @property
    def routes(self) -> tuple[MidiRoute, ...]:
        return tuple(self._routes)

    def add_route(self, route: MidiRoute) -> None:
        if not route.source_port_id or not route.destination_port_id:
            raise ValueError("route source and destination are required")
        if route.source_port_id == route.destination_port_id:
            raise ValueError("a route cannot target its own source")
        if route in self._routes:
            _LOGGER.debug("Route already present, skipping: %s -> %s", route.source_port_id, route.destination_port_id)
            return
        if self._would_create_cycle(route):
            _LOGGER.warning(
                "Rejected route %s -> %s: would create a MIDI routing loop",
                route.source_port_id,
                route.destination_port_id,
            )
            raise ValueError("route would create a MIDI routing loop")
        self._routes.append(route)
        _LOGGER.info("Added MIDI route: %s -> %s (channels=%s)", route.source_port_id, route.destination_port_id, sorted(route.channels) or "all")

    def remove_route(self, route: MidiRoute) -> None:
        if route in self._routes:
            self._routes.remove(route)
            _LOGGER.info("Removed MIDI route: %s -> %s", route.source_port_id, route.destination_port_id)

    def route_message(self, source_port_id: str, message: MidiMessage, send: SendMessage) -> int:
        """Forward one message and return the number of destinations reached."""
        forwarded = 0
        for route in self._routes:
            if not route.enabled or route.source_port_id != source_port_id:
                continue
            if not route.accepts(message):
                self.stats.dropped += 1
                continue
            outgoing = route.transform.apply(message) if route.transform else message
            if outgoing is None:  # blocked by a remap
                self.stats.dropped += 1
                continue
            try:
                send(route.destination_port_id, outgoing)
            except Exception as exc:  # noqa: BLE001 - route diagnostics must not kill monitoring
                self.stats.errors += 1
                self.stats.error_messages.append(str(exc))
                _LOGGER.warning(
                    "Failed to forward message from %r to %r: %s (errors=%d)",
                    source_port_id,
                    route.destination_port_id,
                    exc,
                    self.stats.errors,
                )
                continue
            forwarded += 1
            self.stats.forwarded += 1
        return forwarded

    def _would_create_cycle(self, candidate: MidiRoute) -> bool:
        graph: dict[str, set[str]] = defaultdict(set)
        for route in self._routes:
            graph[route.source_port_id].add(route.destination_port_id)
        graph[candidate.source_port_id].add(candidate.destination_port_id)
        pending = deque([candidate.destination_port_id])
        visited: set[str] = set()
        while pending:
            port_id = pending.popleft()
            if port_id == candidate.source_port_id:
                return True
            if port_id in visited:
                continue
            visited.add(port_id)
            pending.extend(graph[port_id] - visited)
        return False


__all__ = ["BLOCK", "CC", "NOTE", "MidiRoute", "MidiRouter", "MidiValueTransform", "RemapRule", "RouteStats"]
