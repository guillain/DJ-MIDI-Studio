"""In-memory virtual MIDI ports for deterministic integration tests."""

from __future__ import annotations

from collections import deque

from djmidi.midi_api import MidiMessage


class VirtualMidiBus:
    """A tiny port bus implementing the callback expected by ``MidiRouter``."""

    def __init__(self, port_ids: list[str] | None = None) -> None:
        self._queues: dict[str, deque[MidiMessage]] = {
            port_id: deque() for port_id in (port_ids or [])
        }

    def add_port(self, port_id: str) -> None:
        if not port_id.strip():
            raise ValueError("virtual MIDI port ID cannot be empty")
        self._queues.setdefault(port_id, deque())

    def send(self, destination_port_id: str, message: MidiMessage) -> None:
        self.add_port(destination_port_id)
        self._queues[destination_port_id].append(message)

    def receive(self, port_id: str) -> list[MidiMessage]:
        self.add_port(port_id)
        messages = list(self._queues[port_id])
        self._queues[port_id].clear()
        return messages


__all__ = ["VirtualMidiBus"]
