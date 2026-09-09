"""Real per-control geometry (position + shape + a semantic resting color)
for overlaying on top of a controller's actual reference photo
(``assets/controllers/``, see ``controller_image_view.py``) instead of the
abstract uniform-card schematic in ``layout_view.py``.

Coordinates are fractions (0..1) of the *full* reference image's width/height,
measured by eye against ``assets/controllers/<file>.png`` at full resolution.

NOTE (v0.47.53..58): every controller now bundles a clean ``<slug>.png``
render *and* an annotated ``<slug>-midi.png`` (MIDI Message List callouts
printed over it), and every ``CONTROL_GEOMETRY`` block (plus
``layout_view._RIGHT_MIRROR_GEOMETRY`` for DDJ-XP2/XDJ-XZ) has been
re-measured against the clean render, one controller per PR: DDJ-XP2
(v0.47.54), XDJ-XZ (v0.47.55), DDJ-1000 (v0.47.57), DDJ-FLX10 / DDJ-REV1 /
Numark (v0.47.58). All ``catalog`` ``reference_image`` values name the clean
``<slug>.png``. The historical ``<file>.png`` filenames in the per-controller
notes below refer to what is now the ``-midi`` variant.
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
  ``catalog/ddj_rev1.py``. ``assets/controllers/ddj-rev1-midi.png`` was replaced
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
  project note). ``assets/controllers/ddj-1000-midi.png`` wasn't an angled photo
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
  ``assets/controllers/ddj-flx10-midi.png`` was already a tight, flat, high-DPI
  crop of just the top-view device diagram -- no asset fix needed here,
  straight to measuring. Each geometry entry's physical position was tied to
  its catalog name the same way as DDJ-1000's, by cross-referencing this
  controller's own MIDI Message List PDF (``docs/controllers/ddj-flx10-midi-message-list-e1.pdf``)
  Fig./UI-name callouts against its MIDI assignment table.

Both controllers have a mirrored/repeated physical layout that the schematic
already collapses to one cell regardless of which copy is used:

- XDJ-XZ has two deck sides (left tray = deck 1, right tray = deck 2, each
  also switchable to deck 3/4 respectively -- see below); its pad grid is
  the only cluster with both sides recorded (see "Right pad grid" below) --
  the rest of the mixer strip has no discrete catalog entries at all
  (continuous controls are out of catalog scope), so there is nothing left
  to duplicate.
- DDJ-XP2 has two 4x4 pad grids, two SLIDE FX banks, and two LOOP/QUANTIZE/
  KEY clusters (one per side); only the pad grids have both sides recorded
  (see "Right pad grid" below) -- the SLIDE FX/LOOP/QUANTIZE/KEY clusters
  still only have their left copy recorded, same known limitation as before.
- A physical button shared by more than one logical trigger gets *one*
  geometry entry, labelled with every name it answers to, to avoid drawing
  identical markers stacked on top of each other:
  - DDJ-XP2's 4 PAD MODE buttons each emit a different NOTE on a single vs.
    a double click (PAD MODE 1 and PAD MODE 5 share one button, etc.).
  - DDJ-XP2 has only two physical LOAD buttons (left/right) for four
    logical "LOAD DECK 1/2/3/4" triggers, disambiguated by SHIFT the same
    way its pad channels are (see ``catalog/ddj_xp2.py``): left = decks
    1/3, right = decks 2/4.

Right pad grid (DDJ-XP2 and XDJ-XZ): both controllers have a *second*,
physically distinct pad grid to the right of the one described above, which
earlier revisions of this module didn't record at all -- a live hit on that
grid (deck 2 or 4 on DDJ-XP2; deck 2 on XDJ-XZ) would fall back to flashing
the *left* grid's same-numbered marker instead of its own (or nothing),
which is what the maintainer reported (issue: "pad rows are inverted" +
"the right pad grid is absent and its hits land on the left grid",
confirmed on real DDJ-XP2 and XDJ-XZ hardware over the Live Monitor tab).
The right grid's own entries are recorded here under a name suffixed
" (R)" (e.g. "Pad 3 (R)"), measured the same way as everything else --
cropping the real photo and reading off pixel bounds -- and
``resolve_geometry_label`` picks between the plain and " (R)" labels by
looking at which deck the live hit's raw name carries (see
``_RIGHT_GRID_DECKS`` below). DDJ-XP2's left/right split (decks 1/3 = left,
2/4 = right) is confirmed by both the official MIDI Message List's LOAD
button table and a real hardware press over Live Monitor (deck 1 -> left
grid, deck 2 -> right grid); XDJ-XZ's deck 1/2 split is likewise confirmed
on real hardware, but its deck 3/4 assignment to left/right is inferred by
symmetry with DDJ-XP2, not independently hardware-tested.
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
        # Re-measured against the clean render assets/controllers/xdj-xz.png
        # (3024x1623) in v0.47.55 -- the earlier fractions were for the
        # callout-annotated xdj-xz-midi.png, a different crop/aspect. Left
        # tray = deck 1 (also deck 3).
        # Green: play state, matching the PLAY/PAUSE LED's real color.
        "PLAY/PAUSE": ControlGeometry(0.021, 0.882, 0.052, 0.096, "circle", "#3ea86b"),
        # Amber: matches the CUE LED's real color.
        "CUE": ControlGeometry(0.022, 0.783, 0.051, 0.095, "circle", "#e0954a"),
        # Blue: the conventional DJ-gear "sync" accent color. The white SYNC
        # ring in the BEAT SYNC pair beside the jog wheel.
        "SYNC": ControlGeometry(0.299, 0.470, 0.026, 0.037, "circle", "#4a90d9"),
        # Display-only (continuous, not a discrete catalog trigger): the
        # jog wheel and the tempo fader still deserve a place in the overlay.
        "Jog wheel": ControlGeometry(0.062, 0.310, 0.216, 0.378, "circle", "#586b82"),
        "Tempo": ControlGeometry(0.300, 0.700, 0.028, 0.250, "rect", "#6fa8c9"),
        # Muted neutral: a modifier key, not a function. The small [SHIFT]
        # button below DIRECTION on the left tray -- added in v0.47.68 so the
        # Controller Emulator's SHIFT-held state has a marker to click here
        # (catalog entry NOTE 63 already existed).
        "SHIFT": ControlGeometry(0.0185, 0.622, 0.026, 0.034, "rect", "#5f6b7a"),
        # Gray-blue: matches DDJ-XP2's PAD MODE utility accent -- these
        # select what the 8-pad grid below does.
        "HOT CUE": ControlGeometry(0.093, 0.800, 0.055, 0.018, "rect", "#7a8aa0"),
        "BEAT LOOP": ControlGeometry(0.152, 0.800, 0.056, 0.018, "rect", "#7a8aa0"),
        "SLIP LOOP": ControlGeometry(0.212, 0.800, 0.056, 0.018, "rect", "#7a8aa0"),
        "BEAT JUMP": ControlGeometry(0.272, 0.800, 0.053, 0.018, "rect", "#7a8aa0"),
        # Salmon-pink: matches DDJ-XP2's pad grid accent -- same physical role.
        # cols x = 0.088/0.155/0.222/0.288 (w 0.060), rows y = 0.818/0.900.
        "Pad 1": ControlGeometry(0.088, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.155, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.222, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.288, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.088, 0.900, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.155, 0.900, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.222, 0.900, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.288, 0.900, 0.060, 0.068, "rect", "#e0708f"),
        # The second, physically distinct pad grid on the right tray (deck
        # 2, or deck 4 by symmetry) -- see "Right pad grid" in the module
        # docstring. Same row Y's/size as the left grid; cols x =
        # 0.745/0.807/0.868/0.928.
        "Pad 1 (R)": ControlGeometry(0.730, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.797, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.863, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.930, 0.818, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.730, 0.900, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.797, 0.900, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.863, 0.900, 0.060, 0.068, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.930, 0.900, 0.060, 0.068, "rect", "#e0708f"),
    },
    "DDJ-REV1": {
        # Re-measured against the clean render assets/controllers/ddj-rev1.png
        # (1792x1316) in v0.47.58 -- the earlier fractions were for the
        # callout-annotated ddj-rev1-midi.png, a different crop/aspect. Deck 1
        # (left jog, top-left LOOP/SYNC cluster, centre-left pad bank).
        # Display-only continuous control (see the note above): the (large,
        # battle-style) left jog platter. Blue-grey, matching the other
        # controllers' "Jog wheel". Turned by ControllerLayoutView.spin_jog
        # from live relative jog MIDI (v0.47.66, gui/jog.py) -- decorative,
        # no catalog entry.
        "Jog wheel": ControlGeometry(0.064, 0.358, 0.261, 0.368, "circle", "#586b82"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.303, 0.720, 0.052, 0.070, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.252, 0.740, 0.060, 0.035, "rect", "#e0954a"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "AUTO LOOP": ControlGeometry(0.136, 0.306, 0.062, 0.030, "rect", "#7a8aa0"),
        "1/2X": ControlGeometry(0.219, 0.306, 0.024, 0.033, "rect", "#7a8aa0"),
        "2X": ControlGeometry(0.252, 0.306, 0.025, 0.033, "rect", "#7a8aa0"),
        # Blue: matches SYNC's accent color on the other controllers.
        "SYNC": ControlGeometry(0.302, 0.306, 0.060, 0.030, "rect", "#4a90d9"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        # cols x = 0.362/0.398/0.435/0.472 (w 0.035), rows y = 0.462/0.532.
        "Pad 1": ControlGeometry(0.359, 0.475, 0.034, 0.048, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.398, 0.475, 0.034, 0.048, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.437, 0.475, 0.034, 0.048, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.475, 0.475, 0.034, 0.048, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.359, 0.532, 0.034, 0.048, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.398, 0.532, 0.034, 0.048, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.437, 0.532, 0.034, 0.048, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.475, 0.532, 0.034, 0.048, "rect", "#e0708f"),
    },
    "DDJ-XP2": {
        # Re-measured against the clean render assets/controllers/ddj-xp2.png
        # (3950x2900) in v0.47.54 -- the earlier fractions were for the
        # callout-annotated ddj-xp2-midi.png, a different crop/aspect.
        # Salmon-pink: matches the pad grid's own highlight color.
        # Left grid: cols x = 0.135/0.222/0.309/0.396 (w 0.070),
        # rows y = 0.429/0.536/0.659/0.789 (h 0.095) -- the growing row gaps
        # are real on the device.
        "Pad 1": ControlGeometry(0.135, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.222, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.309, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.396, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.135, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.222, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.309, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.396, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 9": ControlGeometry(0.135, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 10": ControlGeometry(0.222, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 11": ControlGeometry(0.309, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 12": ControlGeometry(0.396, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 13": ControlGeometry(0.135, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 14": ControlGeometry(0.222, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 15": ControlGeometry(0.309, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 16": ControlGeometry(0.396, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        # The second, physically distinct pad grid to the right (decks 2/4)
        # -- see "Right pad grid" in the module docstring. Same row Y's/size
        # as the left grid; cols x = 0.535/0.622/0.709/0.796.
        "Pad 1 (R)": ControlGeometry(0.535, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.622, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.709, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.796, 0.429, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.535, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.622, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.709, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.796, 0.536, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 9 (R)": ControlGeometry(0.535, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 10 (R)": ControlGeometry(0.622, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 11 (R)": ControlGeometry(0.709, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 12 (R)": ControlGeometry(0.796, 0.659, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 13 (R)": ControlGeometry(0.535, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 14 (R)": ControlGeometry(0.622, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 15 (R)": ControlGeometry(0.709, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        "Pad 16 (R)": ControlGeometry(0.796, 0.789, 0.076, 0.101, "rect", "#e0708f"),
        # One physical button per entry -- see the module docstring.
        "PAD MODE 1/5": ControlGeometry(0.113, 0.362, 0.092, 0.043, "rect", "#7a8aa0"),
        "PAD MODE 2/6": ControlGeometry(0.222, 0.362, 0.092, 0.043, "rect", "#7a8aa0"),
        "PAD MODE 3/7": ControlGeometry(0.331, 0.362, 0.092, 0.043, "rect", "#7a8aa0"),
        "PAD MODE 4/8": ControlGeometry(0.440, 0.362, 0.092, 0.043, "rect", "#7a8aa0"),
        # Purple: the conventional DJ-gear "effect" accent color. The SLIDE
        # FX 1 panel's 1/2/3 buttons (far-left column).
        "EFFECT 1": ControlGeometry(0.045, 0.109, 0.055, 0.040, "circle", "#9b6fd9"),
        "EFFECT 2": ControlGeometry(0.045, 0.188, 0.055, 0.040, "circle", "#9b6fd9"),
        "EFFECT 3": ControlGeometry(0.045, 0.284, 0.055, 0.040, "circle", "#9b6fd9"),
        "TOUCH STRIP HOLD": ControlGeometry(0.055, 0.853, 0.062, 0.048, "rect", "#8fa0b3"),
        # Display-only (continuous, not a discrete catalog trigger).
        "FX LEVEL": ControlGeometry(0.060, 0.435, 0.045, 0.377, "rect", "#6fa8c9"),
        # Amber: loop/quantize cluster.
        "4 BEAT LOOP": ControlGeometry(0.128, 0.108, 0.086, 0.044, "rect", "#d9954a"),
        "1/2X": ControlGeometry(0.118, 0.183, 0.045, 0.049, "rect", "#d9954a"),
        "2X": ControlGeometry(0.170, 0.183, 0.046, 0.049, "rect", "#d9954a"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.243, 0.093, 0.042, 0.048, "circle", "#4ab8a0"),
        # Blue: matches XDJ-XZ's SYNC accent color -- same function family.
        "BEAT SYNC": ControlGeometry(0.345, 0.191, 0.053, 0.052, "rect", "#4a90d9"),
        # Amber: matches XDJ-XZ's CUE accent color -- same function family.
        "SILENT CUE": ControlGeometry(0.238, 0.276, 0.048, 0.060, "rect", "#e0954a"),
        "KEY -": ControlGeometry(0.303, 0.282, 0.042, 0.053, "rect", "#7a8aa0"),
        "KEY +": ControlGeometry(0.372, 0.282, 0.043, 0.053, "rect", "#7a8aa0"),
        # Magenta: a slate/gray marker is nearly invisible against this
        # knob's bright chrome finish, unlike every other DDJ-XP2 button.
        "Rotary Selector": ControlGeometry(0.452, 0.073, 0.075, 0.084, "circle", "#c9548f"),
        # Green: matches PLAY/PAUSE's accent color -- loading leads to playback.
        "LOAD DECK 1/3": ControlGeometry(0.303, 0.097, 0.095, 0.044, "rect", "#3ea86b"),
        "LOAD DECK 2/4": ControlGeometry(0.523, 0.097, 0.095, 0.044, "rect", "#3ea86b"),
        # Muted neutral: a modifier key, not a function.
        "SHIFT": ControlGeometry(0.506, 0.277, 0.052, 0.052, "rect", "#5f6b7a"),
    },
    "Numark Mixtrack Pro FX": {
        # Re-measured against the clean render
        # assets/controllers/numark-mixtrack-pro-fx.png (624x390) in v0.47.58 --
        # the earlier fractions were for the callout-annotated
        # numark-mixtrack-pro-fx-midi.png, a different crop/aspect. Deck 1.
        # Blue: matches SYNC's accent color on the other controllers.
        "SYNC": ControlGeometry(0.074, 0.658, 0.054, 0.030, "rect", "#4a90d9"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.074, 0.698, 0.054, 0.044, "rect", "#e0954a"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.074, 0.752, 0.054, 0.046, "rect", "#3ea86b"),
        # Gray-blue: utility accent, matches loop-style buttons elsewhere.
        "LOOP": ControlGeometry(0.303, 0.760, 0.038, 0.032, "rect", "#7a8aa0"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        # cols x = 0.145/0.218/0.292/0.365 (w 0.060), rows y = 0.703/0.768.
        "Pad 1": ControlGeometry(0.136, 0.688, 0.058, 0.048, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.209, 0.688, 0.058, 0.048, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.283, 0.688, 0.058, 0.048, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.356, 0.688, 0.058, 0.048, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.136, 0.748, 0.058, 0.048, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.209, 0.748, 0.058, 0.048, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.283, 0.748, 0.058, 0.048, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.356, 0.748, 0.058, 0.048, "rect", "#e0708f"),
    },
    "DDJ-1000": {
        # Re-measured against the clean render assets/controllers/ddj-1000.png
        # (3129x1652) in v0.47.57 -- the earlier fractions were for the
        # callout-annotated ddj-1000-midi.png, a different crop/aspect. Left
        # deck (deck 1/3).
        # Display-only continuous control (see the note above): the left jog
        # platter. Blue-grey, matching XDJ-XZ's "Jog wheel". Turned by
        # ControllerLayoutView.spin_jog from live relative jog MIDI
        # (v0.47.64, gui/jog.py) -- decorative, no catalog entry.
        "Jog wheel": ControlGeometry(0.018, 0.102, 0.255, 0.527, "circle", "#586b82"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.023, 0.795, 0.053, 0.100, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.023, 0.680, 0.053, 0.100, "circle", "#e0954a"),
        # Teal: matches DDJ-XP2's MASTER TEMPO-adjacent utility accent.
        "MASTER TEMPO": ControlGeometry(0.282, 0.683, 0.026, 0.030, "rect", "#4ab8a0"),
        # Blue: matches XDJ-XZ/DDJ-XP2's SYNC/BEAT SYNC accent color.
        "BEAT SYNC": ControlGeometry(0.292, 0.521, 0.026, 0.044, "circle", "#4a90d9"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "KEY SYNC": ControlGeometry(0.282, 0.813, 0.026, 0.033, "rect", "#7a8aa0"),
        "KEY RESET": ControlGeometry(0.282, 0.883, 0.026, 0.030, "rect", "#7a8aa0"),
        # Amber: loop cluster, matches DDJ-XP2's loop accent family.
        "LOOP IN": ControlGeometry(0.018, 0.046, 0.034, 0.069, "circle", "#d9954a"),
        "LOOP OUT": ControlGeometry(0.058, 0.046, 0.034, 0.069, "circle", "#d9954a"),
        "4 BEAT LOOP/EXIT": ControlGeometry(0.098, 0.068, 0.065, 0.040, "rect", "#d9954a"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.203, 0.068, 0.037, 0.040, "rect", "#4ab8a0"),
        # Muted neutral: DDJ-1000's SLIP/SLIP REVERSE aren't a modifier key
        # like SHIFT, but a distinct playback-state toggle family of their own.
        "SLIP": ControlGeometry(0.248, 0.068, 0.037, 0.040, "rect", "#8f6fae"),
        "SLIP REVERSE": ControlGeometry(0.018, 0.168, 0.057, 0.030, "rect", "#8f6fae"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        # cols x = 0.095/0.158/0.220/0.282 (w 0.055), rows y = 0.712/0.805.
        "Pad 1": ControlGeometry(0.088, 0.715, 0.055, 0.078, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.150, 0.710, 0.055, 0.082, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.212, 0.715, 0.055, 0.078, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.273, 0.715, 0.055, 0.078, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.088, 0.803, 0.055, 0.078, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.150, 0.800, 0.055, 0.082, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.212, 0.803, 0.055, 0.078, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.273, 0.803, 0.055, 0.078, "rect", "#e0708f"),
    },
    "DDJ-FLX10": {
        # Re-measured against the clean render assets/controllers/ddj-flx10.png
        # (1792x1316) in v0.47.58 -- the earlier fractions were for the
        # callout-annotated ddj-flx10-midi.png, a different crop/aspect. Left
        # deck (deck 1/3).
        # Display-only continuous control (see the note above): the left jog
        # platter. Blue-grey, matching XDJ-XZ/DDJ-1000's "Jog wheel". Turned
        # by ControllerLayoutView.spin_jog from live relative jog MIDI
        # (v0.47.65, gui/jog.py) -- decorative, no catalog entry.
        "Jog wheel": ControlGeometry(0.067, 0.279, 0.262, 0.387, "circle", "#586b82"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.055, 0.757, 0.066, 0.088, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.055, 0.668, 0.066, 0.088, "circle", "#e0954a"),
        # Blue: matches XDJ-XZ/DDJ-XP2's SYNC/BEAT SYNC accent color.
        "BEAT SYNC": ControlGeometry(0.301, 0.646, 0.034, 0.040, "rect", "#4a90d9"),
        # Teal: matches DDJ-XP2's MASTER TEMPO-adjacent utility accent.
        "TEMPO RESET": ControlGeometry(0.302, 0.710, 0.026, 0.032, "circle", "#4ab8a0"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "KEY SYNC": ControlGeometry(0.301, 0.790, 0.034, 0.038, "rect", "#7a8aa0"),
        # Purple: rekordbox stem control -- a distinct function family from
        # the loop/effect/sync accents used elsewhere.
        "ACTIVE PART DRUMS": ControlGeometry(0.058, 0.203, 0.040, 0.015, "rect", "#9b6fd9"),
        "ACTIVE PART VOCAL": ControlGeometry(0.108, 0.203, 0.040, 0.015, "rect", "#9b6fd9"),
        "ACTIVE PART INST": ControlGeometry(0.158, 0.203, 0.040, 0.015, "rect", "#9b6fd9"),
        # Muted neutral: browse/navigation-style buttons, not a function family.
        "CUE/LOOP CALL <": ControlGeometry(0.222, 0.200, 0.017, 0.023, "circle", "#5f6b7a"),
        "CUE/LOOP CALL >": ControlGeometry(0.253, 0.200, 0.017, 0.023, "circle", "#5f6b7a"),
        # Amber: loop cluster, matches DDJ-XP2/DDJ-1000's loop accent family.
        "LOOP IN / 1/2X": ControlGeometry(0.062, 0.246, 0.038, 0.048, "circle", "#d9954a"),
        "LOOP OUT / 2X": ControlGeometry(0.115, 0.246, 0.038, 0.048, "circle", "#d9954a"),
        "4 BEAT/EXIT": ControlGeometry(0.167, 0.246, 0.038, 0.048, "circle", "#d9954a"),
        # Muted neutral: mix-point navigation, not a function family.
        "MIX POINT SELECT <": ControlGeometry(0.222, 0.246, 0.017, 0.023, "circle", "#5f6b7a"),
        "MIX POINT SELECT >": ControlGeometry(0.253, 0.246, 0.017, 0.023, "circle", "#5f6b7a"),
        "MIX POINT LINK": ControlGeometry(0.267, 0.243, 0.022, 0.028, "circle", "#5f6b7a"),
        # Muted neutral: a distinct playback-state toggle family, matching
        # DDJ-1000's SLIP/SLIP REVERSE coloring.
        "SLIP REVERSE": ControlGeometry(0.055, 0.292, 0.044, 0.020, "rect", "#8f6fae"),
        "SLIP": ControlGeometry(0.340, 0.292, 0.024, 0.020, "rect", "#8f6fae"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.312, 0.292, 0.024, 0.020, "rect", "#4ab8a0"),
        # Muted neutral: browse/navigation-style buttons, not a function family.
        "4 BEAT JUMP <": ControlGeometry(0.059, 0.638, 0.032, 0.034, "rect", "#5f6b7a"),
        "4 BEAT JUMP >": ControlGeometry(0.097, 0.638, 0.032, 0.034, "rect", "#5f6b7a"),
        # Muted neutral: a modifier key, not a function.
        "SHIFT": ControlGeometry(0.054, 0.584, 0.025, 0.030, "rect", "#5f6b7a"),
        # Salmon-pink: matches the pad grid accent used on the other controllers.
        # cols x = 0.124/0.164/0.204/0.245 (w 0.040), rows y = 0.714/0.770 --
        # pixel-scanned against the pad glow borders.
        "Pad 1": ControlGeometry(0.123, 0.714, 0.040, 0.052, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.163, 0.714, 0.040, 0.052, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.203, 0.714, 0.040, 0.052, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.244, 0.714, 0.040, 0.052, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.123, 0.770, 0.040, 0.052, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.163, 0.770, 0.040, 0.052, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.203, 0.770, 0.040, 0.052, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.244, 0.770, 0.040, 0.052, "rect", "#e0708f"),
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


_DECK_NUM_RE = re.compile(r"^Deck (\d+)")

# Which decks land on the physically distinct RIGHT pad grid/tray, for
# controllers with " (R)" geometry entries recorded (see "Right pad grid"
# in the module docstring). Any deck not listed here (or any controller not
# listed at all) resolves to the plain, left-side "Pad N" label.
_RIGHT_GRID_DECKS: dict[str, frozenset[int]] = {
    "DDJ-XP2": frozenset({2, 4}),
    "XDJ-XZ": frozenset({2, 4}),
}


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
        pad_num = pad_match.group(1)
        deck_match = _DECK_NUM_RE.match(hit_name)
        if deck_match is not None and int(deck_match.group(1)) in _RIGHT_GRID_DECKS.get(
            controller, frozenset()
        ):
            right_candidate = f"Pad {pad_num} (R)"
            if right_candidate in index:
                return index[right_candidate]
        candidate = f"Pad {pad_num}"
        if candidate in index:
            return index[candidate]
    base = _base_name(hit_name)
    return index.get(base)


__all__ = ["CONTROL_GEOMETRY", "ControlGeometry", "Shape", "resolve_geometry_label"]
