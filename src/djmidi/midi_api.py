"""Normalized MIDI concepts used by integrations and detection.

The shape follows Web MIDI API concepts (port identity, state, connection,
received timestamp and byte data) while remaining a small desktop-side API.
The transport remains MIDI 1.0 through mido/rtmidi; this module deliberately
does not expose a browser dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MidiPortType = Literal["input", "output"]
MidiPortState = Literal["connected", "disconnected"]
MidiConnectionState = Literal["open", "closed", "pending"]


@dataclass(frozen=True)
class MidiPortInfo:
    """Stable, Web-MIDI-shaped identity and state for one MIDI port."""

    id: str
    name: str
    type: MidiPortType
    manufacturer: str = ""
    version: str = ""
    state: MidiPortState = "connected"
    connection: MidiConnectionState = "closed"
    sysex_enabled: bool = False


@dataclass(frozen=True)
class MidiMessage:
    """A normalized MIDI 1.0 byte message.

    ``data`` is the exact byte sequence received or sent.  Keeping the raw
    bytes makes system realtime and future message types observable without
    forcing channel-voice assumptions onto the router.
    """

    data: bytes
    received_time: float
    port_id: str = ""

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError("MIDI message data cannot be empty")
        if any(not 0 <= byte <= 255 for byte in self.data):
            raise ValueError("MIDI message bytes must be in [0, 255]")

    @property
    def status(self) -> int:
        return self.data[0]

    @property
    def is_sysex(self) -> bool:
        return self.status == 0xF0


__all__ = [
    "MidiConnectionState",
    "MidiMessage",
    "MidiPortInfo",
    "MidiPortState",
    "MidiPortType",
]
