"""Behringer CMD LC-1 MIDI profile.

No official MIDI message list is known to exist for this controller: every
value here was captured from the maintainer's own unit with Controller Setup's
live learning (factory settings, MIDI channel 8) and cross-checked against
their real Serato export (data/serato/cmd-lc1.xml.zip, notes 32-63).

Below the encoders, the face is 13 rows of 4 buttons, numbered by row from the
top with notes running left to right:

- rows 1-2: buttons printed 1-8, notes 16-23 (notes 24-31 are unused);
- rows 3-10: an unlabelled 4x8 grid, notes 32-63;
- rows 11-13: MUTE, SOLO and RECORD, one per column, notes 64-75.

The 8 encoders (CC 16 and up on channel 8) are endless rotaries without a
push switch; like every continuous control they are left out of the catalog.
"""

from __future__ import annotations

from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register

_NAME = "Behringer CMD LC-1"
_CHANNELS = ("8",)
_COLUMNS = 4


def _button(section: str, name: str, note: int) -> ControlInfo:
    return ControlInfo(_NAME, section, name, "NOTE", _CHANNELS, str(note))


_STATIC = [
    *(_button("NUMBER", f"Button {n}", 15 + n) for n in range(1, 9)),
    *(
        _button("GRID", f"Row {row} Button {col}", 32 + (row - 1) * _COLUMNS + (col - 1))
        for row in range(1, 9)
        for col in range(1, _COLUMNS + 1)
    ),
    *(
        _button(section, f"{section} {col}", first + col - 1)
        for section, first in (("MUTE", 64), ("SOLO", 68), ("RECORD", 72))
        for col in range(1, _COLUMNS + 1)
    ),
]


register(
    ControllerDefinition(
        name=_NAME,
        plugin_id="behringer.cmd-lc-1",
        manufacturer="Behringer",
        port_names=("CMD LC-1",),
        reference_image="hardware/behringer/CMD-LC-1/reference.png",
        supported_software=("serato",),
        static_entries=_STATIC,
        section_order=("NUMBER", "GRID", "MUTE", "SOLO", "RECORD"),
        display_order=70,
    )
)
