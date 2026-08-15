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


class MidiClockMirror:
    """Forwards realtime Clock messages from one source to destinations."""

    def __init__(self, source_port_id: str, destination_port_ids: list[str]) -> None:
        if not source_port_id:
            raise ValueError("Clock source is required")
        self.source_port_id = source_port_id
        self.destination_port_ids = tuple(destination_port_ids)
        self.running = False
        self.stats = ClockStats()

    def forward(self, message: MidiMessage, send) -> int:
        if message.port_id != self.source_port_id or message.status not in {
            _START,
            _CONTINUE,
            _STOP,
            _CLOCK,
        }:
            self.stats.ignored += 1
            return 0
        if message.status in {_START, _CONTINUE}:
            self.running = True
        elif message.status == _STOP:
            self.running = False
        count = 0
        for destination in self.destination_port_ids:
            send(destination, message)
            count += 1
        self.stats.forwarded += count
        return count


__all__ = ["ClockStats", "MidiClockMirror"]
