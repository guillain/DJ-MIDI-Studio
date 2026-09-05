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
- XDJ-XZ's hot cue pad cluster: the 8-pad grid and the 4 PAD MODE buttons
  (HOT CUE, BEAT LOOP, SLIP LOOP, BEAT JUMP) that select what the grid does.
  XDJ-XZ's mixer strip (TRIM/EQ/faders) has no catalog entries at all --
  continuous controls are out of catalog scope entirely, see
  ``catalog/__init__.py`` -- so there is nothing discrete left to model
  there; a mixer overlay would have to be display-only, like Jog wheel/Tempo.
- DDJ-REV1's transport + pad cluster: PLAY/PAUSE, CUE, AUTO LOOP, 1/2X, 2X,
  SYNC, and the 8-pad grid -- this covers every entry in
  ``catalog/ddj_rev1.py``. ``assets/controllers/ddj-rev1.png`` was replaced
  with a proper flat top-down diagram cropped from the official MIDI Message
  List PDF (``docs/controllers/ddj-rev1-midi-message-list-e1.pdf``) instead
  of the angled marketing photo it shipped with before -- the same
  fraction-based overlay technique used here isn't reliable against a
  perspective photo (a control further from the camera renders smaller and
  shifted in ways a flat x/y/w/h box can't correct for), so a flat diagram
  is a prerequisite for this controller's geometry, not just a nice-to-have.
- Numark Mixtrack Pro FX's transport + pad cluster: PLAY/PAUSE, CUE, SYNC,
  LOOP, and the 8-pad grid -- this covers every entry in
  ``catalog/numark_mixtrack_pro_fx.py``. Same fix as DDJ-REV1:
  ``assets/controllers/numark-mixtrack-pro-fx.png`` was an angled marketing
  photo, replaced with a flat top-down diagram cropped from page 3 of the
  bundled user guide (``docs/controllers/numark-mixtrack-pro-fx-user-guide-v1.2.pdf``,
  the "Top Panel" figure) at 300 DPI -- this PDF is a general user guide, not
  a MIDI message list, so unlike the Pioneer controllers there was no data
  table to cross-check the catalog's trigger values against (the catalog's
  own docstring already discloses this as a "conservative community
  profile"); only the geometry (control positions) came from this PDF.
- DDJ-1000's transport + pad cluster: PLAY/PAUSE, CUE, MASTER TEMPO, BEAT
  SYNC, KEY SYNC, KEY RESET, LOOP IN, LOOP OUT, 4 BEAT LOOP/EXIT, QUANTIZE,
  SLIP, SLIP REVERSE, and the 8-pad grid -- this covers every entry in
  ``catalog/ddj_1000.py`` (fixed to real MIDI values in
  ``v0.47.31-ddj-1000-catalog-fix``, see the ``pioneer-catalog-data-verification``
  project note). ``assets/controllers/ddj-1000.png`` wasn't an angled photo
  like DDJ-REV1/Numark, but a low-DPI dump of the *entire* PDF page (title,
  device diagram, and the MIDI table below it) -- unusably imprecise for
  fraction-based measurement, with the actual device occupying a small
  fraction of the image. Replaced with a tight, 300 DPI crop of just the
  top-view device diagram from ``docs/controllers/ddj-1000-midi-message-list-e1.pdf``
  page 1 (the same PDF the catalog data fix used), which conveniently
  already carries the manufacturer's own Fig./UI-name callouts (D1-L, D2-L,
  ...). Each geometry entry's physical position was matched to its catalog
  name by cross-referencing this PDF's own MIDI assignment table (e.g.
  "D7-L ... BEAT SYNC ... NOTE 88" ties the button drawn at D7-L's position
  directly to the catalog's `BEAT SYNC` entry, Data1 88), not guessed from
  the drawing's layout alone.
- DDJ-FLX10's transport + pad cluster: PLAY/PAUSE, CUE, BEAT SYNC, TEMPO
  RESET, KEY SYNC, ACTIVE PART DRUMS/VOCAL/INST, CUE/LOOP CALL </>, LOOP IN,
  LOOP OUT, 4 BEAT/EXIT, MIX POINT SELECT </>, MIX POINT LINK, SLIP REVERSE,
  QUANTIZE, SLIP, 4 BEAT JUMP </>, SHIFT, and the 8-pad grid -- this covers
  every entry in ``catalog/ddj_flx10.py`` (fully re-transcribed to real MIDI
  values, see ``v0.47.32-ddj-flx10-catalog-fix``). Unlike DDJ-1000,
  ``assets/controllers/ddj-flx10.png`` was already a tight, flat, high-DPI
  crop of just the top-view device diagram -- no asset fix needed here,
  straight to measuring. Each geometry entry's physical position was tied to
  its catalog name the same way as DDJ-1000's, by cross-referencing this
  controller's own MIDI Message List PDF (``docs/controllers/ddj-flx10-midi-message-list-e1.pdf``)
  Fig./UI-name callouts against its MIDI assignment table.

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
        # Gray-blue: matches DDJ-XP2's PAD MODE utility accent -- these
        # select what the 8-pad grid below does.
        "HOT CUE": ControlGeometry(0.2071, 0.7675, 0.0214, 0.0096, "rect", "#7a8aa0"),
        "BEAT LOOP": ControlGeometry(0.2353, 0.7675, 0.0214, 0.0096, "rect", "#7a8aa0"),
        "SLIP LOOP": ControlGeometry(0.2635, 0.7675, 0.0214, 0.0096, "rect", "#7a8aa0"),
        "BEAT JUMP": ControlGeometry(0.2917, 0.7675, 0.0214, 0.0096, "rect", "#7a8aa0"),
        # Salmon-pink: matches DDJ-XP2's pad grid accent -- same physical role.
        "Pad 1": ControlGeometry(0.2080, 0.7962, 0.0214, 0.0350, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.2363, 0.7962, 0.0214, 0.0350, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.2644, 0.7962, 0.0214, 0.0350, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2927, 0.7962, 0.0214, 0.0350, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.2080, 0.8471, 0.0214, 0.0350, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.2363, 0.8471, 0.0214, 0.0350, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.2644, 0.8471, 0.0214, 0.0350, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2927, 0.8471, 0.0214, 0.0350, "rect", "#e0708f"),
    },
    "DDJ-REV1": {
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.3100, 0.8772, 0.0328, 0.0665, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.2587, 0.9372, 0.0257, 0.0188, "rect", "#e0954a"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "AUTO LOOP": ControlGeometry(0.1440, 0.2797, 0.0257, 0.0159, "rect", "#7a8aa0"),
        "1/2X": ControlGeometry(0.1890, 0.2797, 0.0121, 0.0159, "rect", "#7a8aa0"),
        "2X": ControlGeometry(0.2149, 0.2797, 0.0121, 0.0159, "rect", "#7a8aa0"),
        # Blue: matches SYNC's accent color on the other controllers.
        "SYNC": ControlGeometry(0.2480, 0.2797, 0.0257, 0.0159, "rect", "#4a90d9"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        "Pad 1": ControlGeometry(0.3673, 0.4986, 0.0328, 0.0694, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.4016, 0.4986, 0.0328, 0.0694, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.4358, 0.4986, 0.0328, 0.0694, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.4697, 0.4986, 0.0328, 0.0694, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.3673, 0.5738, 0.0328, 0.0694, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.4016, 0.5738, 0.0328, 0.0694, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.4358, 0.5738, 0.0328, 0.0694, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.4697, 0.5738, 0.0328, 0.0694, "rect", "#e0708f"),
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
    "Numark Mixtrack Pro FX": {
        # Blue: matches SYNC's accent color on the other controllers.
        "SYNC": ControlGeometry(0.0427, 0.6875, 0.0373, 0.0333, "rect", "#4a90d9"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.0427, 0.7465, 0.0373, 0.0313, "rect", "#e0954a"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.0427, 0.8194, 0.0373, 0.0538, "rect", "#3ea86b"),
        # Gray-blue: utility accent, matches loop-style buttons elsewhere.
        "LOOP": ControlGeometry(0.3050, 0.7778, 0.0367, 0.0295, "rect", "#7a8aa0"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        "Pad 1": ControlGeometry(0.0967, 0.7413, 0.0392, 0.0556, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.1433, 0.7413, 0.0383, 0.0556, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.1908, 0.7413, 0.0383, 0.0556, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2367, 0.7413, 0.0383, 0.0556, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.0967, 0.8177, 0.0392, 0.0573, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.1433, 0.8177, 0.0383, 0.0573, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.1908, 0.8177, 0.0383, 0.0573, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2367, 0.8177, 0.0383, 0.0573, "rect", "#e0708f"),
    },
    "DDJ-1000": {
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.0518, 0.8267, 0.0491, 0.0943, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.0518, 0.7143, 0.0461, 0.0933, "circle", "#e0954a"),
        # Teal: matches DDJ-XP2's MASTER TEMPO-adjacent utility accent.
        "MASTER TEMPO": ControlGeometry(0.2814, 0.7111, 0.0161, 0.0254, "rect", "#4ab8a0"),
        # Blue: matches XDJ-XZ/DDJ-XP2's SYNC/BEAT SYNC accent color.
        "BEAT SYNC": ControlGeometry(0.3215, 0.5476, 0.0162, 0.0352, "circle", "#4a90d9"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "KEY SYNC": ControlGeometry(0.2796, 0.8024, 0.0186, 0.0262, "rect", "#7a8aa0"),
        "KEY RESET": ControlGeometry(0.2796, 0.8512, 0.0186, 0.0238, "rect", "#7a8aa0"),
        # Amber: loop cluster, matches DDJ-XP2's loop accent family.
        "LOOP IN": ControlGeometry(0.0461, 0.0667, 0.0249, 0.0540, "circle", "#d9954a"),
        "LOOP OUT": ControlGeometry(0.0804, 0.0683, 0.0234, 0.0508, "circle", "#d9954a"),
        "4 BEAT LOOP/EXIT": ControlGeometry(0.1064, 0.0798, 0.0482, 0.0250, "rect", "#d9954a"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.2314, 0.0798, 0.0214, 0.0250, "rect", "#4ab8a0"),
        # Muted neutral: DDJ-1000's SLIP/SLIP REVERSE aren't a modifier key
        # like SHIFT, but a distinct playback-state toggle family of their own.
        "SLIP": ControlGeometry(0.2555, 0.0798, 0.0208, 0.0250, "rect", "#8f6fae"),
        "SLIP REVERSE": ControlGeometry(0.0499, 0.1552, 0.0323, 0.0238, "rect", "#8f6fae"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        "Pad 1": ControlGeometry(0.1132, 0.7638, 0.0351, 0.0724, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.1531, 0.7638, 0.0355, 0.0724, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.1952, 0.7638, 0.0351, 0.0724, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2360, 0.7638, 0.0360, 0.0724, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.1132, 0.8457, 0.0351, 0.0724, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.1531, 0.8457, 0.0355, 0.0724, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.1952, 0.8457, 0.0351, 0.0724, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2360, 0.8457, 0.0360, 0.0724, "rect", "#e0708f"),
    },
    "DDJ-FLX10": {
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.0345, 0.6603, 0.0552, 0.0762, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.0345, 0.5793, 0.0552, 0.0762, "circle", "#e0954a"),
        # Blue: matches XDJ-XZ/DDJ-XP2's SYNC/BEAT SYNC accent color.
        "BEAT SYNC": ControlGeometry(0.2767, 0.5631, 0.0216, 0.0167, "rect", "#4a90d9"),
        # Teal: matches DDJ-XP2's MASTER TEMPO-adjacent utility accent.
        "TEMPO RESET": ControlGeometry(0.2798, 0.6131, 0.0155, 0.0214, "circle", "#4ab8a0"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "KEY SYNC": ControlGeometry(0.2767, 0.6702, 0.0216, 0.0167, "rect", "#7a8aa0"),
        # Purple: rekordbox stem control -- a distinct function family from
        # the loop/effect/sync accents used elsewhere.
        "ACTIVE PART DRUMS": ControlGeometry(0.0267, 0.1071, 0.0276, 0.0119, "rect", "#9b6fd9"),
        "ACTIVE PART VOCAL": ControlGeometry(0.0612, 0.1071, 0.0276, 0.0119, "rect", "#9b6fd9"),
        "ACTIVE PART INST": ControlGeometry(0.0957, 0.1071, 0.0276, 0.0119, "rect", "#9b6fd9"),
        # Muted neutral: browse/navigation-style buttons, not a function family.
        "CUE/LOOP CALL <": ControlGeometry(0.2112, 0.0988, 0.0121, 0.0167, "circle", "#5f6b7a"),
        "CUE/LOOP CALL >": ControlGeometry(0.2371, 0.0988, 0.0121, 0.0167, "circle", "#5f6b7a"),
        # Amber: loop cluster, matches DDJ-XP2/DDJ-1000's loop accent family.
        "LOOP IN / 1/2X": ControlGeometry(0.0336, 0.1393, 0.0293, 0.0405, "circle", "#d9954a"),
        "LOOP OUT / 2X": ControlGeometry(0.0681, 0.1393, 0.0293, 0.0405, "circle", "#d9954a"),
        "4 BEAT/EXIT": ControlGeometry(0.1026, 0.1393, 0.0293, 0.0405, "circle", "#d9954a"),
        # Muted neutral: mix-point navigation, not a function family.
        "MIX POINT SELECT <": ControlGeometry(0.2112, 0.1571, 0.0121, 0.0167, "circle", "#5f6b7a"),
        "MIX POINT SELECT >": ControlGeometry(0.2371, 0.1571, 0.0121, 0.0167, "circle", "#5f6b7a"),
        "MIX POINT LINK": ControlGeometry(0.2664, 0.1464, 0.0155, 0.0214, "circle", "#5f6b7a"),
        # Muted neutral: a distinct playback-state toggle family, matching
        # DDJ-1000's SLIP/SLIP REVERSE coloring.
        "SLIP REVERSE": ControlGeometry(0.0328, 0.1988, 0.0379, 0.0107, "rect", "#8f6fae"),
        "SLIP": ControlGeometry(0.3155, 0.2036, 0.0207, 0.0107, "rect", "#8f6fae"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.2905, 0.2036, 0.0198, 0.0107, "rect", "#4ab8a0"),
        # Muted neutral: browse/navigation-style buttons, not a function family.
        "4 BEAT JUMP <": ControlGeometry(0.0457, 0.5512, 0.0147, 0.0155, "rect", "#5f6b7a"),
        "4 BEAT JUMP >": ControlGeometry(0.0707, 0.5512, 0.0138, 0.0155, "rect", "#5f6b7a"),
        # Muted neutral: a modifier key, not a function.
        "SHIFT": ControlGeometry(0.0414, 0.5143, 0.0172, 0.0095, "rect", "#5f6b7a"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        "Pad 1": ControlGeometry(0.1052, 0.6286, 0.0345, 0.0429, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.1483, 0.6286, 0.0345, 0.0429, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.1897, 0.6286, 0.0345, 0.0429, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2328, 0.6286, 0.0328, 0.0429, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.1052, 0.6857, 0.0345, 0.0476, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.1483, 0.6857, 0.0345, 0.0476, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.1897, 0.6857, 0.0345, 0.0476, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2328, 0.6857, 0.0328, 0.0476, "rect", "#e0708f"),
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
