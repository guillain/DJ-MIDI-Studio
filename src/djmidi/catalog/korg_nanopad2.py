"""Korg nanoPAD2 MIDI profile.

Korg's official MIDI Implementation (controllers/hardware/korg/nanoPAD2/) documents the
message types but not a note assignment: every pad is user-assignable per scene
through Korg's editor. Every value here was captured from the maintainer's own
unit in all four scenes (the scene change shows up as Korg's documented Scene
Change SysEx, which is how the captures were told apart).

All four scenes send on MIDI channel 1 and use disjoint notes, so they can
coexist in one profile. They are modelled like a Pioneer pad grid's pad
modes: one 16-pad grid (pad 1-8 top row, 9-16 bottom row, left to right)
whose entries are named "Pad N (SCENE S)", so every view groups the four
scenes onto the same physical pad. Each row is two runs of four consecutive
notes, 24 apart:

- top row: base+0..3, then base+24..27;
- bottom row: base+12..15, then base+36..39;

with base 0, 4, 48 and 52 for scenes 1-4. The bundled reference-midi.png (the
"MIDI info" view) is a Korg editor screenshot of a different Scene 1, notes
36-51, the layout the maintainer's Traktor export also maps: it shows where the
pads are, not the notes this unit sends.

The X-Y touch pad (continuous) is left out like every continuous control. The
HOLD / GATE ARP / TOUCH SCALE / KEY/RANGE / SCALE/TAP / SCENE buttons were
pressed during the capture too and send no note or CC (SCENE only sends the
SysEx above): they change the controller's own state, so there is nothing to
map.
"""

from __future__ import annotations

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    _parse_midi_note,
    register,
)

_NAME = "Korg nanoPAD2"
_CHANNELS = ("1",)
_SCENE_BASES = (0, 4, 48, 52)
# Note offsets from a scene's base, left to right.
_TOP_ROW = (0, 1, 2, 3, 24, 25, 26, 27)
_BOTTOM_ROW = (12, 13, 14, 15, 36, 37, 38, 39)

# note -> (scene, pad), pads 1-8 top row then 9-16 bottom row.
_NOTE_TO_PAD = {
    base + offset: (scene, pad)
    for scene, base in enumerate(_SCENE_BASES, start=1)
    for pad, offset in enumerate(_TOP_ROW + _BOTTOM_ROW, start=1)
}


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _CHANNELS:
        return None
    note = _parse_midi_note(data1)
    hit = _NOTE_TO_PAD.get(note) if note is not None else None
    if hit is None:
        return None
    scene, pad = hit
    return ControlInfo(_NAME, "PAD", f"Pad {pad} (SCENE {scene})", "NOTE", _CHANNELS, data1)


register(
    ControllerDefinition(
        name=_NAME,
        plugin_id="korg.nanopad2",
        manufacturer="Korg",
        port_names=("nanoPAD2",),
        reference_image="hardware/korg/nanoPAD2/reference.png",
        pad_lookup=_pad_lookup,
        pad_count=16,
        pad_columns=8,
        display_order=80,
    )
)
