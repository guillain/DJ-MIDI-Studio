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
class MidiIdentityReply:
    """Universal MIDI Identity Reply (MIDI 1.0 SysEx), normalized."""

    manufacturer_id: bytes
    family_id: bytes
    model_id: bytes
    version: bytes
    device_id: int

    @property
    def identity_id(self) -> bytes:
        return self.manufacturer_id + self.family_id + self.model_id


def parse_midi_identity_reply(data: bytes) -> MidiIdentityReply | None:
    """Parse ``F0 7E/7F device 06 02 ... F7`` without performing I/O."""
    if len(data) < 14 or data[0] != 0xF0 or data[-1] != 0xF7:
        return None
    if data[1] not in (0x7E, 0x7F) or data[3:5] != bytes((0x06, 0x02)):
        return None
    device_id = data[2]
    offset = 5
    if data[offset] == 0:
        if len(data) < offset + 3 + 2 + 2 + 4 + 1:
            return None
        manufacturer_id = data[offset : offset + 3]
        offset += 3
    else:
        manufacturer_id = data[offset : offset + 1]
        offset += 1
    if len(data) < offset + 2 + 2 + 4 + 1:
        return None
    return MidiIdentityReply(
        manufacturer_id=manufacturer_id,
        family_id=data[offset : offset + 2],
        model_id=data[offset + 2 : offset + 4],
        version=data[offset + 4 : offset + 8],
        device_id=device_id,
    )


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
    "MidiIdentityReply",
    "MidiMessage",
    "MidiPortInfo",
    "MidiPortState",
    "MidiPortType",
    "parse_midi_identity_reply",
]
