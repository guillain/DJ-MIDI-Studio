"""Real per-control geometry (position + shape + a semantic resting color)
for overlaying on top of a controller's actual reference photo
(``assets/controllers/``, see ``controller_image_view.py``) instead of the
abstract uniform-card schematic in ``layout_view.py``.

Coordinates are fractions (0..1) of the *full* reference image's width/height,
measured by eye against ``assets/controllers/<file>.png`` at full resolution.
A uniform fixed-size schematic card, as used elsewhere in the app, can't
represent a giant jog wheel and a small button at their true relative scale
without overlapping neighbours once real spacing is honoured -- overlaying
directly on the real photo sidesteps that entirely, since the photo already
encodes correct proportions and spacing.

Part of the "DJ layout visual fidelity" chantier (CLAUDE.md / TODO.md /
issue #13), extended one verified batch at a time (see the project's rule
against building visual-polish features blind -- every entry here was
checked by cropping the region of the real image it claims to describe and
screenshotting the rendered overlay against it, not guessed from the PDF
callout numbers alone):

- XDJ-XZ's transport cluster: PLAY/PAUSE, CUE, SYNC, jog wheel, tempo fader.
- DDJ-XP2's pad cluster: the 16-pad grid, the 4 PAD MODE buttons, the
  SLIDE FX bank (EFFECT 1/2/3, FX LEVEL, TOUCH STRIP HOLD).
- DDJ-XP2's DECK/BROWSE/OTHER sections: LOOP (4 BEAT LOOP, 1/2X, 2X),
  QUANTIZE, BEAT SYNC, SILENT CUE, KEY -/+, the central Rotary Selector, the
  two LOAD buttons, and SHIFT -- this completes every DDJ-XP2 catalog
  section except MIDI-OUT (four output-only "Loaded (Deck N)" LEDs, not a
  user control; left for whenever an output-direction glyph exists, same
  status as the VU meter glyph on XDJ-XZ).

Both controllers have a mirrored/repeated physical layout that the schematic
already collapses to one cell regardless of which copy is used:

- XDJ-XZ has two deck sides (left tray = deck 1, right tray = deck 2); only
  the left side's coordinates are recorded here.
- DDJ-XP2 has two 4x4 pad grids, two SLIDE FX banks, and two LOOP/QUANTIZE/
  KEY clusters (one per side); only the left copy's coordinates are recorded
  here.
- A physical button shared by more than one logical trigger gets *one*
  geometry entry, labelled with every name it answers to, to avoid drawing
  identical markers stacked on top of each other:
  - DDJ-XP2's 4 PAD MODE buttons each emit a different NOTE on a single vs.
    a double click (PAD MODE 1 and PAD MODE 5 share one button, etc.).
  - DDJ-XP2 has only two physical LOAD buttons (left/right) for four
    logical "LOAD DECK 1/2/3/4" triggers, disambiguated by SHIFT the same
    way its pad channels are (see ``catalog/ddj_xp2.py``): left = decks
    1/3, right = decks 2/4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from djmidi.gui.layout import _PAD_NUM_RE, _base_name

Shape = Literal["rect", "circle"]


@dataclass(frozen=True)
class ControlGeometry:
    """A control's bounding box, as fractions of the reference image's full
    width/height, plus a semantic resting color for the overlay."""

    x: float
    y: float
    w: float
    h: float
    shape: Shape
    color: str


# controller -> a free-form label (shown as the marker's tooltip; a
# display-only label like "Jog wheel"/"Tempo" is used for a continuous
# control with no catalog entry) -> geometry.
CONTROL_GEOMETRY: dict[str, dict[str, ControlGeometry]] = {
    "XDJ-XZ": {
        # Green: play state, matching the PLAY/PAUSE LED's real color.
        "PLAY/PAUSE": ControlGeometry(0.1497, 0.8420, 0.0296, 0.0484, "circle", "#3ea86b"),
        # Amber: matches the CUE LED's real color.
        "CUE": ControlGeometry(0.1521, 0.7726, 0.0249, 0.0408, "circle", "#e0954a"),
        # Blue: the conventional DJ-gear "sync" accent color.
        "SYNC": ControlGeometry(0.3532, 0.5312, 0.0187, 0.0306, "circle", "#4a90d9"),
        # Display-only (continuous, not a discrete catalog trigger): the
        # jog wheel and the tempo fader still deserve a place in the overlay.
        "Jog wheel": ControlGeometry(0.1439, 0.4268, 0.1944, 0.3185, "circle", "#586b82"),
        "Tempo": ControlGeometry(0.3560, 0.6911, 0.0156, 0.1911, "rect", "#6fa8c9"),
    },
    "DDJ-XP2": {
        # Salmon-pink: matches the pad grid's own highlight color in the
        # reference photo.
        "Pad 1": ControlGeometry(0.3332, 0.5971, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.3736, 0.5971, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.4134, 0.5971, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.4530, 0.5971, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.3332, 0.6785, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.3736, 0.6785, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.4134, 0.6785, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.4530, 0.6785, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 9": ControlGeometry(0.3332, 0.7686, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 10": ControlGeometry(0.3736, 0.7686, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 11": ControlGeometry(0.4134, 0.7686, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 12": ControlGeometry(0.4530, 0.7686, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 13": ControlGeometry(0.3332, 0.8558, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 14": ControlGeometry(0.3736, 0.8558, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 15": ControlGeometry(0.4134, 0.8558, 0.0357, 0.0674, "rect", "#e0708f"),
        "Pad 16": ControlGeometry(0.4530, 0.8558, 0.0357, 0.0674, "rect", "#e0708f"),
        # One physical button per entry -- see the module docstring.
        "PAD MODE 1/5": ControlGeometry(0.3351, 0.5364, 0.0324, 0.0262, "rect", "#7a8aa0"),
        "PAD MODE 2/6": ControlGeometry(0.3752, 0.5364, 0.0324, 0.0262, "rect", "#7a8aa0"),
        "PAD MODE 3/7": ControlGeometry(0.4151, 0.5364, 0.0324, 0.0262, "rect", "#7a8aa0"),
        "PAD MODE 4/8": ControlGeometry(0.4546, 0.5364, 0.0324, 0.0262, "rect", "#7a8aa0"),
        # Purple: the conventional DJ-gear "effect" accent color.
        "EFFECT 1": ControlGeometry(0.3099, 0.3491, 0.0151, 0.0320, "circle", "#9b6fd9"),
        "EFFECT 2": ControlGeometry(0.3099, 0.4247, 0.0151, 0.0320, "circle", "#9b6fd9"),
        "EFFECT 3": ControlGeometry(0.3099, 0.4997, 0.0151, 0.0320, "circle", "#9b6fd9"),
        "TOUCH STRIP HOLD": ControlGeometry(0.2969, 0.9038, 0.0330, 0.0320, "rect", "#8fa0b3"),
        # Display-only (continuous, not a discrete catalog trigger).
        "FX LEVEL": ControlGeometry(0.3120, 0.5698, 0.0110, 0.2791, "rect", "#6fa8c9"),
        # Amber: loop/quantize cluster.
        "4 BEAT LOOP": ControlGeometry(0.3393, 0.3517, 0.0289, 0.0291, "rect", "#d9954a"),
        "1/2X": ControlGeometry(0.3271, 0.4116, 0.0247, 0.0349, "rect", "#d9954a"),
        "2X": ControlGeometry(0.3532, 0.4116, 0.0247, 0.0349, "rect", "#d9954a"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.3869, 0.3509, 0.0151, 0.0320, "circle", "#4ab8a0"),
        # Blue: matches XDJ-XZ's SYNC accent color -- same function family.
        "BEAT SYNC": ControlGeometry(0.4293, 0.4145, 0.0165, 0.0291, "rect", "#4a90d9"),
        # Amber: matches XDJ-XZ's CUE accent color -- same function family.
        "SILENT CUE": ControlGeometry(0.3752, 0.4535, 0.0385, 0.0465, "rect", "#e0954a"),
        "KEY -": ControlGeometry(0.4110, 0.4564, 0.0192, 0.0407, "rect", "#7a8aa0"),
        "KEY +": ControlGeometry(0.4264, 0.4564, 0.0192, 0.0407, "rect", "#7a8aa0"),
        # Magenta: a slate/gray marker is nearly invisible against this
        # knob's bright chrome finish, unlike every other DDJ-XP2 button.
        "Rotary Selector": ControlGeometry(0.4756, 0.3198, 0.0357, 0.0756, "circle", "#c9548f"),
        # Green: matches PLAY/PAUSE's accent color -- loading leads to playback.
        "LOAD DECK 1/3": ControlGeometry(0.4233, 0.3509, 0.0220, 0.0320, "rect", "#3ea86b"),
        "LOAD DECK 2/4": ControlGeometry(0.5459, 0.3509, 0.0220, 0.0320, "rect", "#3ea86b"),
        # Muted neutral: a modifier key, not a function.
        "SHIFT": ControlGeometry(0.4781, 0.4821, 0.0323, 0.0218, "rect", "#5f6b7a"),
    },
}


# A combined-label suffix like "PAD MODE 1/5" or "LOAD DECK 1/3" names two
# (or more) full logical names sharing one physical marker (see the module
# docstring); this pulls both back out so a live catalog.lookup() hit's raw
# name -- "PAD MODE 5", never "PAD MODE 1/5" -- can find its marker.
_COMBINED_LABEL_RE = re.compile(r"^(?P<prefix>.+ )(?P<numbers>\d+(?:/\d+)+)$")


def _label_alternatives(label: str) -> tuple[str, ...]:
    match = _COMBINED_LABEL_RE.match(label)
    if match is None:
        return (label,)
    prefix = match.group("prefix")
    return tuple(f"{prefix}{n}" for n in match.group("numbers").split("/"))


_REVERSE_INDEX_CACHE: dict[str, dict[str, str]] = {}


def _reverse_index(controller: str) -> dict[str, str]:
    index = _REVERSE_INDEX_CACHE.get(controller)
    if index is None:
        index = {}
        for label in CONTROL_GEOMETRY.get(controller, {}):
            for alternative in _label_alternatives(label):
                index[alternative] = label
        _REVERSE_INDEX_CACHE[controller] = index
    return index


def resolve_geometry_label(controller: str, hit_name: str) -> str | None:
    """Maps a live ``catalog.lookup()`` hit's raw ``ControlInfo.name`` (e.g.
    ``"PLAY/PAUSE"``, ``"Deck 1 Pad 3 (PAD MODE 2)"``, ``"PAD MODE 5"``) to
    the ``CONTROL_GEOMETRY`` label it should flash, or ``None`` if that
    control isn't modeled yet. Used to drive a live-MIDI flash on the real
    photo overlay, mirroring ``ControllerLayoutView.flash_key`` on the
    schematic tabs (see ``controller_image_view.ControllerImageView.flash_key``)."""
    index = _reverse_index(controller)
    if hit_name in index:
        return index[hit_name]
    pad_match = _PAD_NUM_RE.search(hit_name)
    if pad_match is not None:
        candidate = f"Pad {pad_match.group(1)}"
        if candidate in index:
            return index[candidate]
    base = _base_name(hit_name)
    return index.get(base)


__all__ = ["CONTROL_GEOMETRY", "ControlGeometry", "Shape", "resolve_geometry_label"]
