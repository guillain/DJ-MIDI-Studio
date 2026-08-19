"""Deterministic MIDI 1.0 routing primitives, independent of hardware I/O."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

from djmidi.midi_api import MidiMessage

_LOGGER = logging.getLogger(__name__)

SendMessage = Callable[[str, MidiMessage], None]


@dataclass(frozen=True)
class MidiRoute:
    source_port_id: str
    destination_port_id: str
    channels: frozenset[int] = frozenset()
    status_nibbles: frozenset[int] = frozenset()
    allow_sysex: bool = False
    enabled: bool = True

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
            try:
                send(route.destination_port_id, message)
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


__all__ = ["MidiRoute", "MidiRouter", "RouteStats"]
