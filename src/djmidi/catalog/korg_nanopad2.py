"""Korg nanoPAD2 MIDI profile.

Korg's official MIDI Implementation (controllers/hardware/korg/nanoPAD2/) documents the
message types but not a note assignment: every pad is user-assignable per scene
through Korg's editor. Every value here was captured from the maintainer's own
unit in all four scenes (the scene change shows up as Korg's documented Scene
Change SysEx, which is how the captures were told apart).

All four scenes send on MIDI channel 1 and use disjoint notes, so they can
coexist in one profile. The 16 trigger pads form two rows of 8, numbered left
to right; each row is two runs of four consecutive notes, 24 apart:

- top row: base+0..3, then base+24..27;
- bottom row: base+12..15, then base+36..39;

with base 0, 4, 48 and 52 for scenes 1-4. A Korg editor screenshot showing
notes 36-51 for Scene 1 does not match the unit, so it is not bundled as this
controller's "MIDI info" image.

The X-Y touch pad (continuous) is left out like every continuous control. The
HOLD / GATE ARP / TOUCH SCALE / KEY/RANGE / SCALE/TAP / SCENE buttons were
pressed during the capture too and send no note or CC (SCENE only sends the
SysEx above): they change the controller's own state, so there is nothing to
map.
"""

from __future__ import annotations

from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register

_NAME = "Korg nanoPAD2"
_CHANNELS = ("1",)
_SCENE_BASES = (0, 4, 48, 52)
# Note offsets from a scene's base, left to right.
_TOP_ROW = (0, 1, 2, 3, 24, 25, 26, 27)
_BOTTOM_ROW = (12, 13, 14, 15, 36, 37, 38, 39)


def _scene_pads(scene: int, base: int) -> list[ControlInfo]:
    section = f"SCENE {scene}"
    return [
        ControlInfo(_NAME, section, f"Scene {scene} {row} Pad {col}", "NOTE", _CHANNELS, str(base + offset))
        for row, offsets in (("Top", _TOP_ROW), ("Bottom", _BOTTOM_ROW))
        for col, offset in enumerate(offsets, start=1)
    ]


_STATIC = [entry for scene, base in enumerate(_SCENE_BASES, start=1) for entry in _scene_pads(scene, base)]


register(
    ControllerDefinition(
        name=_NAME,
        plugin_id="korg.nanopad2",
        manufacturer="Korg",
        port_names=("nanoPAD2",),
        reference_image="hardware/korg/nanoPAD2/reference.png",
        static_entries=_STATIC,
        section_order=tuple(f"SCENE {scene}" for scene in range(1, len(_SCENE_BASES) + 1)),
        display_order=80,
    )
)
