"""Real per-control geometry (position + shape + a semantic resting color)
for overlaying on top of a controller's actual reference photo
(``controllers/hardware/<vendor>/<Model>/``, see ``controller_image_view.py``) instead of the
abstract uniform-card schematic in ``layout_view.py``.

Coordinates are fractions (0..1) of the *full* reference image's width/height,
measured by eye against ``controllers/hardware/<vendor>/<Model>/reference.png`` at full resolution.

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
- XDJ-XZ's right tray (v0.47.88, issue #103): the right-tray mirror of the
  transport + hot cue pad-mode cluster above (PLAY/PAUSE, CUE, SHIFT, HOT
  CUE, BEAT LOOP, SLIP LOOP, BEAT JUMP, SYNC), plus display-only Jog wheel
  (R)/Tempo (R) markers -- this had been missing even though the pad grid's
  right side was already recorded back in v0.47.55; see the "Both
  controllers have a mirrored/repeated physical layout" note below for why
  it stayed left-tray-only until now.
- DDJ-REV1's transport + pad cluster: PLAY/PAUSE, CUE, AUTO LOOP, 1/2X, 2X,
  SYNC, and the 8-pad grid -- this covers every entry in
  ``catalog/ddj_rev1.py``. ``controllers/hardware/pioneer/DDJ-REV1/reference-midi.png`` was replaced
  with a proper flat top-down diagram cropped from the official MIDI Message
  List PDF (``controllers/hardware/pioneer/DDJ-REV1/ddj-rev1-midi-message-list-e1.pdf``) instead
  of the angled marketing photo it shipped with before -- the same
  fraction-based overlay technique used here isn't reliable against a
  perspective photo (a control further from the camera renders smaller and
  shifted in ways a flat x/y/w/h box can't correct for), so a flat diagram
  is a prerequisite for this controller's geometry, not just a nice-to-have.
- Numark Mixtrack Pro FX's transport + pad cluster: PLAY/PAUSE, CUE, SYNC,
  LOOP, and the 8-pad grid -- this covers every entry in
  ``catalog/numark_mixtrack_pro_fx.py``. Same fix as DDJ-REV1:
  ``controllers/hardware/numark/Mixtrack-Pro-FX/reference.png`` was an angled marketing
  photo, replaced with a flat top-down diagram cropped from page 3 of the
  bundled user guide (``controllers/hardware/numark/Mixtrack-Pro-FX/numark-mixtrack-pro-fx-user-guide-v1.2.pdf``,
  the "Top Panel" figure) at 300 DPI -- this PDF is a general user guide, not
  a MIDI message list, so unlike the Pioneer controllers there was no data
  table to cross-check the catalog's trigger values against (the catalog's
  own docstring already discloses this as a "conservative community
  profile"); only the geometry (control positions) came from this PDF.
  **Update (v0.47.89, issue #103):** the v0.47.58 rename above (this
  flat diagram becoming the "-midi" variant in favor of a newly-sourced
  "clean" photorealistic render) turned out to be a regression -- that
  low-res 624x390 photo couldn't be measured reliably (a tight crop of
  the shipped left "SYNC" entry didn't clearly land on the button). Every
  entry was re-measured from scratch against a freshly-cropped, higher-DPI
  version of this same PDF diagram, which is now back to being the "clean"
  primary render; the old photorealistic file and the "-midi" variant slot
  were both dropped (this controller now bundles a single image, "MIDI
  info" disabled, same as a Controller Setup attachment with no sibling).
  A right-deck (deck 2) `" (R)"` copy of every entry was added in the same
  pass -- Numark's two decks are two separate physical trays, same gap
  issue #103 flagged on DDJ-1000/DDJ-REV1/DDJ-FLX10.
- DDJ-1000's transport + pad cluster: PLAY/PAUSE, CUE, MASTER TEMPO, BEAT
  SYNC, KEY SYNC, KEY RESET, LOOP IN, LOOP OUT, 4 BEAT LOOP/EXIT, QUANTIZE,
  SLIP, SLIP REVERSE, and the 8-pad grid -- this covers every entry in
  ``catalog/ddj_1000.py`` (fixed to real MIDI values in
  ``v0.47.31-ddj-1000-catalog-fix``, see the ``pioneer-catalog-data-verification``
  project note). ``controllers/hardware/pioneer/DDJ-1000/reference-midi.png`` wasn't an angled photo
  like DDJ-REV1/Numark, but a low-DPI dump of the *entire* PDF page (title,
  device diagram, and the MIDI table below it) -- unusably imprecise for
  fraction-based measurement, with the actual device occupying a small
  fraction of the image. Replaced with a tight, 300 DPI crop of just the
  top-view device diagram from ``controllers/hardware/pioneer/DDJ-1000/ddj-1000-midi-message-list-e1.pdf``
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
  ``controllers/hardware/pioneer/DDJ-FLX10/reference-midi.png`` was already a tight, flat, high-DPI
  crop of just the top-view device diagram -- no asset fix needed here,
  straight to measuring. Each geometry entry's physical position was tied to
  its catalog name the same way as DDJ-1000's, by cross-referencing this
  controller's own MIDI Message List PDF (``controllers/hardware/pioneer/DDJ-FLX10/ddj-flx10-midi-message-list-e1.pdf``)
  Fig./UI-name callouts against its MIDI assignment table.

Both controllers have a mirrored/repeated physical layout that the schematic
already collapses to one cell regardless of which copy is used:

- XDJ-XZ has two deck sides (left tray = deck 1, right tray = deck 2, each
  also switchable to deck 3/4 respectively -- see below). As of
  ``v0.47.88`` both the pad grid *and* the transport/pad-mode cluster
  (PLAY/PAUSE, CUE, SHIFT, HOT CUE, BEAT LOOP, SLIP LOOP, BEAT JUMP, SYNC)
  have both sides recorded (see "Right pad grid" below for the pad grid;
  the transport cluster's `" (R)"` entries live alongside the left copies
  in the XDJ-XZ block below), plus display-only Jog wheel (R)/Tempo (R)
  markers for the two continuous controls that already had a left-side
  entry. An earlier version of this comment claimed the rest of the mixer
  strip had no discrete catalog entries at all and so nothing was left to
  duplicate -- that was wrong; the transport cluster above is real,
  catalog-backed, and simply had no geometry recorded yet. What remains
  genuinely out of catalog scope (continuous controls with no discrete
  catalog entry at all, e.g. TRIM/EQ/channel fader) is unaffected by this
  and still has no geometry, on either side.
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

Right pad grid (DDJ-XP2, XDJ-XZ, DDJ-1000, DDJ-FLX10, Numark Mixtrack Pro
FX): each of these controllers has a *second*, physically distinct pad grid
to the right of the one described above, which earlier revisions of this
module didn't record at all -- a live hit on that grid (deck 2 or 4 on
DDJ-XP2/DDJ-1000/DDJ-FLX10; deck 2 on XDJ-XZ/Numark) would fall back to
flashing the *left* grid's same-numbered marker instead of its own (or
nothing), which is what the maintainer reported for DDJ-XP2/XDJ-XZ (issue:
"pad rows are inverted" + "the right pad grid is absent and its hits land
on the left grid", confirmed on real DDJ-XP2 and XDJ-XZ hardware over the
Live Monitor tab) and what a later proactive audit found repeated across
every other controller with geometry (issue #103). The right grid's own
entries are recorded here under a name suffixed " (R)" (e.g. "Pad 3 (R)"),
measured the same way as everything else -- cropping the real photo and
reading off pixel bounds -- and ``resolve_geometry_label`` picks between
the plain and " (R)" labels by looking at which deck the live hit's raw
name carries (see ``_RIGHT_GRID_DECKS`` below). DDJ-XP2's left/right split
(decks 1/3 = left, 2/4 = right) is confirmed by both the official MIDI
Message List's LOAD button table and a real hardware press over Live
Monitor (deck 1 -> left grid, deck 2 -> right grid); XDJ-XZ's deck 1/2
split is likewise confirmed on real hardware, but its deck 3/4 assignment
to left/right is inferred by symmetry with DDJ-XP2, not independently
hardware-tested. DDJ-1000/DDJ-FLX10/Numark's left/right splits all come
from each controller's own channel-per-deck catalog convention (deck N maps
directly to a fixed MIDI channel per ``_DECK_CHANNELS``/``_PAD_CHANNELS``),
not hardware-tested independently of that convention either.
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
# v0.48.46: every reference image was normalized by
# scripts/process_controller_images.py (transparent background, margin
# cropped, 2000 px wide) and the fractions below were remapped from each
# crop box (x' = (x*W - left) / crop_w, w' = w*W / crop_w; the uniform resize
# leaves fractions unchanged), then checked on screen. Pixel sizes quoted in
# the per-controller comments refer to the images as originally measured.
CONTROL_GEOMETRY: dict[str, dict[str, ControlGeometry]] = {
    "XDJ-XZ": {
        # Re-measured against the clean render controllers/hardware/pioneer/XDJ-XZ/reference.png
        # (3024x1623) in v0.47.55 -- the earlier fractions were for the
        # callout-annotated xdj-xz-midi.png, a different crop/aspect. Left
        # tray = deck 1 (also deck 3).
        # Green: play state, matching the PLAY/PAUSE LED's real color.
        "PLAY/PAUSE": ControlGeometry(0.0210, 0.8819, 0.0520, 0.0961, "circle", "#3ea86b"),
        # Amber: matches the CUE LED's real color.
        "CUE": ControlGeometry(0.0220, 0.7829, 0.0510, 0.0951, "circle", "#e0954a"),
        # Blue: the conventional DJ-gear "sync" accent color. The white SYNC
        # ring in the BEAT SYNC pair beside the jog wheel.
        "SYNC": ControlGeometry(0.2980, 0.4677, 0.0270, 0.0270, "circle", "#4a90d9"),
        # Display-only (continuous, not a discrete catalog trigger): the
        # jog wheel and the tempo fader still deserve a place in the overlay.
        "Jog wheel": ControlGeometry(0.0620, 0.3096, 0.2160, 0.3782, "circle", "#586b82"),
        "Tempo": ControlGeometry(0.2980, 0.6868, 0.0260, 0.2752, "rect", "#6fa8c9"),
        # Muted neutral: a modifier key, not a function. The small [SHIFT]
        # button below DIRECTION on the left tray -- added in v0.47.68 so the
        # Controller Emulator's SHIFT-held state has a marker to click here
        # (catalog entry NOTE 63 already existed).
        "SHIFT": ControlGeometry(0.0185, 0.6218, 0.0260, 0.0340, "rect", "#5f6b7a"),
        # Gray-blue: matches DDJ-XP2's PAD MODE utility accent -- these
        # select what the 8-pad grid below does.
        "HOT CUE": ControlGeometry(0.0910, 0.7919, 0.0570, 0.0160, "rect", "#7a8aa0"),
        "BEAT LOOP": ControlGeometry(0.1520, 0.7919, 0.0560, 0.0160, "rect", "#7a8aa0"),
        "SLIP LOOP": ControlGeometry(0.2120, 0.7919, 0.0560, 0.0160, "rect", "#7a8aa0"),
        "BEAT JUMP": ControlGeometry(0.2720, 0.7919, 0.0530, 0.0160, "rect", "#7a8aa0"),
        # Salmon-pink: matches DDJ-XP2's pad grid accent -- same physical
        # role. Re-measured in the issue-#118 pass ("layout" session), twice:
        # the first pass (w 0.060->0.046, h 0.068->0.055) only fixed pad
        # *size*, not *pitch* -- it kept the old 0.057 column spacing, which
        # was itself wrong (real pads sit much closer together, pitch
        # ~0.037), so the boxes still didn't hug the real pads and the
        # maintainer reported it "tjs ko" against Controller Images. Verified
        # this time with a tight, gridlined crop of all 8 pads at once (not
        # a single-pad crop, which had been the source of the pitch error --
        # too little context to catch that the gap between pads is much
        # smaller than a pad's own width). cols x = 0.101/0.141/0.177/0.213
        # (w 0.032, pitch ~0.037), rows y = 0.830/0.898 (h 0.053).
        "Pad 1": ControlGeometry(0.1010, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.1410, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.1770, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2130, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.1010, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.1410, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.1770, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2130, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        # The second, physically distinct pad grid on the right tray (deck
        # 2, or deck 4 by symmetry) -- see "Right pad grid" in the module
        # docstring. Same row Y's/size as the left grid; cols x =
        # 0.759/0.796/0.833/0.869 (same ~0.037 pitch, independently measured
        # against the real photo, not mirrored from the left columns).
        "Pad 1 (R)": ControlGeometry(0.7590, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.7960, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.8330, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.8690, 0.8299, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.7590, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.7960, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.8330, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.8690, 0.8979, 0.0320, 0.0530, "rect", "#e0708f"),
        # Right tray transport + pad-mode cluster -- issue #103. The module
        # docstring above used to claim "the rest of the mixer strip has no
        # discrete catalog entries at all... so there is nothing left to
        # duplicate" for XDJ-XZ; that was wrong. The right tray has its own
        # physical CUE/PLAY-PAUSE/SHIFT/HOT CUE/BEAT LOOP/SLIP LOOP/BEAT
        # JUMP cluster (confirmed against the reference photo, not assumed
        # from symmetry) that simply had no geometry recorded, on top of
        # the pad grid above which already did. Plus display-only Jog wheel
        # and Tempo (continuous, no catalog entry, same as their left
        # counterparts). Each independently measured and crop-verified
        # against controllers/hardware/pioneer/XDJ-XZ/reference.png, same discipline as
        # DDJ-1000/DDJ-REV1/DDJ-FLX10's right-deck work. Live-hit flash
        # resolution stays left-tray-only for these (reachable via the
        # static overlay only): unlike the pad grid, whose names carry a
        # "Deck N" prefix that resolve_geometry_label already keys off,
        # XDJ-XZ's other DECK entries (PLAY/PAUSE, CUE, SYNC, SHIFT, HOT
        # CUE, ...) carry no deck info in their name at all -- same
        # limitation as DDJ-1000/DDJ-REV1/DDJ-FLX10's non-pad entries.
        "PLAY/PAUSE (R)": ControlGeometry(0.6750, 0.8819, 0.0520, 0.0961, "circle", "#3ea86b"),
        "CUE (R)": ControlGeometry(0.6750, 0.7829, 0.0510, 0.0951, "circle", "#e0954a"),
        "SYNC (R)": ControlGeometry(0.9400, 0.4677, 0.0270, 0.0270, "circle", "#4a90d9"),
        "Jog wheel (R)": ControlGeometry(0.7186, 0.3413, 0.2160, 0.3782, "circle", "#586b82"),
        "Tempo (R)": ControlGeometry(0.9430, 0.6868, 0.0260, 0.2752, "rect", "#6fa8c9"),
        "SHIFT (R)": ControlGeometry(0.6725, 0.6218, 0.0260, 0.0340, "rect", "#5f6b7a"),
        # x re-measured -- the previous fractions drifted further off the
        # real button the further right they went (a ~0.066 gap by BEAT
        # JUMP), not just imprecise like the left side's minor rounding.
        "HOT CUE (R)": ControlGeometry(0.7450, 0.7919, 0.0530, 0.0160, "rect", "#7a8aa0"),
        "BEAT LOOP (R)": ControlGeometry(0.8030, 0.7919, 0.0550, 0.0160, "rect", "#7a8aa0"),
        "SLIP LOOP (R)": ControlGeometry(0.8620, 0.7919, 0.0550, 0.0160, "rect", "#7a8aa0"),
        "BEAT JUMP (R)": ControlGeometry(0.9210, 0.7919, 0.0520, 0.0160, "rect", "#7a8aa0"),
    },
    "DDJ-REV1": {
        # Re-measured against the clean render controllers/hardware/pioneer/DDJ-REV1/reference.png
        # (1792x1316) in v0.47.58 -- the earlier fractions were for the
        # callout-annotated ddj-rev1-midi.png, a different crop/aspect. Deck 1
        # (left jog, top-left LOOP/SYNC cluster, centre-left pad bank).
        # Display-only continuous control (see the note above): the (large,
        # battle-style) left jog platter. Blue-grey, matching the other
        # controllers' "Jog wheel". Turned by ControllerLayoutView.spin_jog
        # from live relative jog MIDI (v0.47.66, gui/jog.py) -- decorative,
        # no catalog entry.
        "Jog wheel": ControlGeometry(0.0305, 0.2716, 0.2811, 0.5920, "circle", "#586b82"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        # x re-measured (issue #118, "layout" session): both PLAY/PAUSE and
        # CUE below sat far to the left of the real buttons -- close to the
        # AUTO LOOP/2X cluster's x instead of where PLAY/PAUSE and CUE
        # actually are, in front of the jog wheel's lower-right edge.
        "PLAY/PAUSE": ControlGeometry(0.2825, 0.8652, 0.0592, 0.0869, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.2254, 0.9167, 0.0355, 0.0290, "rect", "#e0954a"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons
        # elsewhere. Height re-measured (issue #118, "layout" session): all
        # four of these ran roughly double the real button's height,
        # reaching down into the "RELOOP/EXIT"/"IN"/"OUT"/"OFF" labels below.
        "AUTO LOOP": ControlGeometry(0.1080, 0.1815, 0.0528, 0.0257, "rect", "#7a8aa0"),
        "1/2X": ControlGeometry(0.1974, 0.1815, 0.0226, 0.0225, "rect", "#7a8aa0"),
        "2X": ControlGeometry(0.2340, 0.1815, 0.0226, 0.0225, "rect", "#7a8aa0"),
        # Blue: matches SYNC's accent color on the other controllers.
        "SYNC": ControlGeometry(0.2868, 0.1815, 0.0517, 0.0257, "rect", "#4a90d9"),
        # Salmon-pink: matches the pad grid accent used on the other
        # controllers. Re-measured in the issue-#118 ("layout") pass: height
        # ran noticeably taller than the real pad (0.048 vs 0.031), reaching
        # past its bottom edge, and row 2 sat a further 0.022 too low on top
        # of that. cols x = 0.360/0.400/0.440/0.481 (w 0.039), rows y =
        # 0.470/0.510 (h 0.031).
        "Pad 1": ControlGeometry(0.3492, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.3923, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.4354, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.4795, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.3492, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.3923, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.4354, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.4795, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        # Right deck (deck 2/4) -- issue #103, same treatment as DDJ-1000
        # (v0.47.83): every entry above only ever had its left-deck (deck
        # 1/3) copy recorded. Every entry below was independently measured
        # and crop-verified against controllers/hardware/pioneer/DDJ-REV1/reference.png, not
        # mirrored around a single axis -- same lesson as DDJ-1000's
        # right-deck PR: an axis that fits one control doesn't reliably fit
        # the rest. The pad grid's right-deck copy (the 8-pad grid showing
        # HOT CUE/AUTO LOOP/TRACKING/SAMPLER mode labels, a different pad
        # mode than the left deck's BEAT JUMP/ROLL/TRANS/SCRATCH BANK, but
        # the same physical 8-pad grid) was a known-remaining gap (issue
        # #103) -- filled in the issue-#118 ("layout") pass, the same one
        # that fixed the left grid's oversized height above. Measured off
        # the SAMPLER/jog-wheel boundary (the one edge that cropped
        # unambiguously against the platter) and walked left in the same
        # 0.040 pitch confirmed on the left grid, since a direct per-pad
        # crop kept landing on a pad boundary rather than a pad center, same
        # difficulty the original attempt ran into. cols x =
        # 0.502/0.542/0.582/0.622 (w 0.039), rows y = 0.470/0.510 (h 0.031,
        # same rows as the left grid -- both banks sit at the same height).
        # Live-hit flash resolution stays left-deck-only for these, same
        # reason as DDJ-1000: resolve_geometry_label only keys off deck
        # number for pad-numbered hits, and DDJ-REV1's non-pad ControlInfo
        # names carry no "Deck N" prefix to resolve a deck from.
        "Pad 1 (R)": ControlGeometry(0.5022, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.5452, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.5883, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.6314, 0.4517, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.5022, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.5452, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.5883, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.6314, 0.5161, 0.0420, 0.0499, "rect", "#e0708f"),
        "Jog wheel (R)": ControlGeometry(0.7073, 0.2716, 0.2811, 0.5920, "circle", "#586b82"),
        # Re-measured with the left copies above in the issue-#118 pass --
        # same over-tall AUTO LOOP/1-2X/2X/SYNC bug, plus SYNC (R) itself
        # had drifted 0.042 left of the real button (nearly on top of where
        # 2X (R) actually is).
        "PLAY/PAUSE (R)": ControlGeometry(0.9329, 0.8652, 0.0528, 0.0869, "circle", "#3ea86b"),
        "CUE (R)": ControlGeometry(0.8791, 0.9167, 0.0485, 0.0290, "rect", "#e0954a"),
        "AUTO LOOP (R)": ControlGeometry(0.7326, 0.1815, 0.0538, 0.0225, "rect", "#7a8aa0"),
        "1/2X (R)": ControlGeometry(0.8015, 0.1815, 0.0237, 0.0225, "rect", "#7a8aa0"),
        "2X (R)": ControlGeometry(0.8403, 0.1815, 0.0237, 0.0225, "rect", "#7a8aa0"),
        "SYNC (R)": ControlGeometry(0.8931, 0.1815, 0.0517, 0.0225, "rect", "#4a90d9"),
    },
    "DDJ-XP2": {
        # Re-measured against the clean render controllers/hardware/pioneer/DDJ-XP2/reference.png
        # (3950x2900) in v0.47.54 -- the earlier fractions were for the
        # callout-annotated ddj-xp2-midi.png, a different crop/aspect.
        # Salmon-pink: matches the pad grid's own highlight color.
        # Left grid: cols x = 0.135/0.222/0.309/0.396 (w 0.070),
        # rows y = 0.429/0.536/0.659/0.789 (h 0.095) -- the growing row gaps
        # are real on the device.
        "Pad 1": ControlGeometry(0.1082, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.2017, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.2951, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.3885, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.1082, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.2017, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.2951, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.3885, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 9": ControlGeometry(0.1082, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 10": ControlGeometry(0.2017, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 11": ControlGeometry(0.2951, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 12": ControlGeometry(0.3885, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 13": ControlGeometry(0.1082, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 14": ControlGeometry(0.2017, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 15": ControlGeometry(0.2951, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 16": ControlGeometry(0.3885, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        # The second, physically distinct pad grid to the right (decks 2/4)
        # -- see "Right pad grid" in the module docstring. Same row Y's/size
        # as the left grid; cols x = 0.535/0.622/0.709/0.796.
        "Pad 1 (R)": ControlGeometry(0.5377, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.6311, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.7245, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.8179, 0.4254, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.5377, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.6311, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.7245, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.8179, 0.5448, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 9 (R)": ControlGeometry(0.5377, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 10 (R)": ControlGeometry(0.6311, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 11 (R)": ControlGeometry(0.7245, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 12 (R)": ControlGeometry(0.8179, 0.6820, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 13 (R)": ControlGeometry(0.5377, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 14 (R)": ControlGeometry(0.6311, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 15 (R)": ControlGeometry(0.7245, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        "Pad 16 (R)": ControlGeometry(0.8179, 0.8270, 0.0816, 0.1127, "rect", "#e0708f"),
        # Re-measured in the issue-#118 pass ("layout" session): every entry
        # below this point (everything except the pad grid) had drifted well
        # off the real button on the clean render -- some by up to a third
        # of the image's width (QUANTIZE/BEAT SYNC/SILENT CUE/KEY -/KEY +/
        # LOAD were sitting over an unrelated neighbouring control entirely,
        # not just imprecise) -- and the whole right-hand cluster (decks
        # 2/4) had no entries here at all outside the pad grid; the
        # schematic/emulator view got a right cluster only via
        # layout_view._RIGHT_MIRROR_GEOMETRY, and Controller Images got none.
        # That mirror table's own theory for why it had to live apart from
        # this one (a same-named "(R)" entry here would collide with the
        # left one in _reverse_index) didn't hold up on inspection -- see
        # its own comment -- so the right cluster now lives here directly,
        # as ordinary "X (R)" entries, covering both views at once; the
        # DDJ-XP2 entry was removed from _RIGHT_MIRROR_GEOMETRY once this
        # table's right cluster existed, to avoid double-drawing every
        # marker in the schematic view. One physical button answers to both
        # a single- and double-click name -- see the module docstring.
        "PAD MODE 1/5": ControlGeometry(0.1082, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        "PAD MODE 2/6": ControlGeometry(0.2017, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        "PAD MODE 3/7": ControlGeometry(0.2951, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        "PAD MODE 4/8": ControlGeometry(0.3885, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        # Right-tray copy (decks 2/4) -- previously entirely unmodeled here.
        "PAD MODE 1/5 (R)": ControlGeometry(0.5216, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        "PAD MODE 2/6 (R)": ControlGeometry(0.6150, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        "PAD MODE 3/7 (R)": ControlGeometry(0.7084, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        "PAD MODE 4/8 (R)": ControlGeometry(0.8018, 0.3485, 0.0934, 0.0558, "rect", "#7a8aa0"),
        # Purple: the conventional DJ-gear "effect" accent color. The SLIDE
        # FX 1 panel's 1/2/3 buttons (far-left column).
        "EFFECT 1": ControlGeometry(0.0363, 0.0730, 0.0429, 0.0379, "circle", "#9b6fd9"),
        "EFFECT 2": ControlGeometry(0.0363, 0.1667, 0.0429, 0.0379, "circle", "#9b6fd9"),
        "EFFECT 3": ControlGeometry(0.0363, 0.2603, 0.0429, 0.0379, "circle", "#9b6fd9"),
        "TOUCH STRIP HOLD": ControlGeometry(0.0138, 0.9017, 0.0612, 0.0435, "rect", "#8fa0b3"),
        # Display-only (continuous, not a discrete catalog trigger).
        "FX LEVEL": ControlGeometry(0.0148, 0.4321, 0.0429, 0.4049, "rect", "#6fa8c9"),
        # SLIDE FX 2 bank (right, decks 2/4) -- previously entirely unmodeled.
        "EFFECT 1 (R)": ControlGeometry(0.9199, 0.0730, 0.0429, 0.0379, "circle", "#9b6fd9"),
        "EFFECT 2 (R)": ControlGeometry(0.9199, 0.1667, 0.0429, 0.0379, "circle", "#9b6fd9"),
        "EFFECT 3 (R)": ControlGeometry(0.9199, 0.2603, 0.0429, 0.0379, "circle", "#9b6fd9"),
        "TOUCH STRIP HOLD (R)": ControlGeometry(0.9060, 0.9017, 0.0612, 0.0435, "rect", "#8fa0b3"),
        # Named "Slide FX 2" directly, not "FX LEVEL (R)": the schematic's
        # own cell_key_for_geometry_label() strips a trailing " (R)" *before*
        # consulting _LABEL_ALIASES, so a "FX LEVEL (R)" label would resolve
        # through the "FX LEVEL" -> "Slide FX 1" alias above and land on the
        # left fader's cell instead of its own -- same reason the previous
        # layout_view._RIGHT_MIRROR_GEOMETRY copy of this fader used this
        # exact name rather than an " (R)" suffix.
        "Slide FX 2": ControlGeometry(0.9167, 0.4321, 0.0397, 0.4015, "rect", "#6fa8c9"),
        # Amber: loop/quantize cluster (left, decks 1/3).
        "4 BEAT LOOP": ControlGeometry(0.1168, 0.0730, 0.0977, 0.0368, "rect", "#d9954a"),
        "1/2X": ControlGeometry(0.1168, 0.1667, 0.0419, 0.0368, "rect", "#d9954a"),
        "2X": ControlGeometry(0.1727, 0.1667, 0.0419, 0.0368, "rect", "#d9954a"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.2392, 0.0663, 0.0440, 0.0457, "circle", "#4ab8a0"),
        # Blue: matches XDJ-XZ's SYNC accent color -- same function family.
        "BEAT SYNC": ControlGeometry(0.3606, 0.1667, 0.0429, 0.0379, "rect", "#4a90d9"),
        # Amber: matches XDJ-XZ's CUE accent color -- same function family.
        "SILENT CUE": ControlGeometry(0.2403, 0.2615, 0.0408, 0.0323, "rect", "#e0954a"),
        "KEY -": ControlGeometry(0.3047, 0.2603, 0.0429, 0.0379, "rect", "#7a8aa0"),
        "KEY +": ControlGeometry(0.3606, 0.2603, 0.0429, 0.0379, "rect", "#7a8aa0"),
        # Loop/quantize cluster (right, decks 2/4) -- previously entirely
        # unmodeled here (layout_view._RIGHT_MIRROR_GEOMETRY used to carry
        # an imprecise copy for the schematic view only -- see the comment
        # above and that table's own updated comment).
        "4 BEAT LOOP (R)": ControlGeometry(0.7814, 0.0730, 0.0977, 0.0368, "rect", "#d9954a"),
        "1/2X (R)": ControlGeometry(0.7836, 0.1667, 0.0440, 0.0390, "rect", "#d9954a"),
        "2X (R)": ControlGeometry(0.8394, 0.1667, 0.0440, 0.0390, "rect", "#d9954a"),
        "QUANTIZE (R)": ControlGeometry(0.7181, 0.0663, 0.0440, 0.0457, "circle", "#4ab8a0"),
        "BEAT SYNC (R)": ControlGeometry(0.6515, 0.1667, 0.0429, 0.0390, "rect", "#4a90d9"),
        "SILENT CUE (R)": ControlGeometry(0.7245, 0.2626, 0.0344, 0.0323, "rect", "#e0954a"),
        "KEY - (R)": ControlGeometry(0.5957, 0.2603, 0.0440, 0.0379, "rect", "#7a8aa0"),
        "KEY + (R)": ControlGeometry(0.6515, 0.2603, 0.0429, 0.0379, "rect", "#7a8aa0"),
        # Magenta: a slate/gray marker is nearly invisible against this
        # knob's bright chrome finish, unlike every other DDJ-XP2 button.
        # Single physical control, centered between the two decks/pad banks
        # -- no right-side copy.
        "Rotary Selector": ControlGeometry(0.4303, 0.0339, 0.0966, 0.1004, "circle", "#c9548f"),
        # Green: matches PLAY/PAUSE's accent color -- loading leads to playback.
        "LOAD DECK 1/3": ControlGeometry(0.3047, 0.0730, 0.0977, 0.0368, "rect", "#3ea86b"),
        "LOAD DECK 2/4": ControlGeometry(0.5957, 0.0730, 0.0988, 0.0379, "rect", "#3ea86b"),
        # Muted neutral: a modifier key, not a function. Single physical
        # button (channel 7, shared by all 4 decks) -- no right-side copy.
        "SHIFT": ControlGeometry(0.4830, 0.2682, 0.0344, 0.0223, "rect", "#5f6b7a"),
    },
    "Numark Mixtrack Pro FX": {
        # v0.47.89 (issue #103): re-measured from scratch against a brand new
        # reference image. The old "clean" render (624x390, photorealistic)
        # proved too low-resolution to measure reliably -- a tight crop of
        # even the shipped left "SYNC" entry didn't clearly land on the
        # button. Swapped it for a flat, high-DPI top-view diagram cropped
        # from the bundled user guide PDF (controllers/hardware/numark/Mixtrack-Pro-FX/
        # numark-mixtrack-pro-fx-user-guide-v1.2.pdf page 3, 300 DPI,
        # tight-cropped to just the device) -- the same source this controller's geometry already
        # used once before, in v0.47.33, prior to the v0.47.58 rename that
        # demoted it to the "-midi" variant in favor of the (now-removed)
        # low-res photo. That PDF diagram has its own numbered legend
        # circles baked into the raster (not a separate overlay), so unlike
        # every other controller's "clean" render this one isn't callout-
        # free -- a deliberate, user-approved trade-off to get a reliable
        # measurement source (see issue #103). The controller's `-midi`
        # variant was dropped rather than kept as a second, semantically-
        # backwards "MIDI info" view; "MIDI info" is disabled for this
        # controller now (single bundled variant), matching how a Controller
        # Setup attachment with no `-midi` sibling already behaves.
        #
        # Unlike the previous single-marker-only measurement, this pass also
        # added a right-deck (deck 2) " (R)" copy of every entry -- Numark's
        # two decks are two separate physical trays (left = deck 1, right =
        # deck 2), the same shape of gap issue #103 flagged on DDJ-1000/
        # DDJ-REV1/DDJ-FLX10. Non-pad entries stay static-overlay-only, same
        # known limitation as those three: the catalog's _STATIC ControlInfo
        # entries (catalog/numark_mixtrack_pro_fx.py) collapse both channels
        # into one shared name ("PLAY/PAUSE", not "Deck 2 PLAY/PAUSE"), so
        # there's no per-deck name for resolve_geometry_label to key live-hit
        # flash resolution off. Pad names *do* already carry a "Deck N"
        # prefix (_pad_lookup), so the pad grid's right side works for free
        # once _RIGHT_GRID_DECKS carries an entry for this controller (see
        # below) -- same mechanism as DDJ-1000/DDJ-FLX10.
        #
        # Blue: matches SYNC's accent color on the other controllers.
        # x/y re-measured twice in the issue-#118 ("layout") pass: the
        # first fix landed on the "30/31" pad-mode legend circles instead
        # of the real SYNC/CUE/PLAY-PAUSE buttons (confirmed wrong by
        # screenshotting the actual running app, not just a PIL render) --
        # the real buttons sit tight against the "27/28/29" circles
        # immediately to their right, not the "30/31" pair one column over.
        "SYNC": ControlGeometry(0.0269, 0.6987, 0.0475, 0.0428, "rect", "#4a90d9"),
        "SYNC (R)": ControlGeometry(0.6253, 0.6987, 0.0475, 0.0428, "rect", "#4a90d9"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.0269, 0.7598, 0.0475, 0.0326, "rect", "#e0954a"),
        "CUE (R)": ControlGeometry(0.6253, 0.7598, 0.0475, 0.0326, "rect", "#e0954a"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.0269, 0.8342, 0.0475, 0.0408, "rect", "#3ea86b"),
        "PLAY/PAUSE (R)": ControlGeometry(0.6253, 0.8342, 0.0475, 0.0408, "rect", "#3ea86b"),
        # Gray-blue: utility accent, matches loop-style buttons elsewhere.
        # x re-measured (issue #118 pass): sat a full button-width left of
        # the real "LOOP" button, over blank panel.
        "LOOP": ControlGeometry(0.3297, 0.7659, 0.0403, 0.0479, "rect", "#7a8aa0"),
        "LOOP (R)": ControlGeometry(0.8981, 0.7659, 0.0403, 0.0479, "rect", "#7a8aa0"),
        # Salmon-pink: matches the pad grid accent used on the other
        # controllers. x re-measured (issue #118 pass): columns had drifted
        # up to 0.028 left of the real pad by column 4.
        "Pad 1": ControlGeometry(0.0910, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.1499, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.2077, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2656, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.0910, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.1499, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.2077, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2656, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
        "Pad 1 (R)": ControlGeometry(0.6904, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.7493, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.8082, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.8671, 0.7527, 0.0413, 0.0734, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.6904, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.7493, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.8082, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.8671, 0.8342, 0.0413, 0.0764, "rect", "#e0708f"),
    },
    "DDJ-1000": {
        # Re-measured against the clean render controllers/hardware/pioneer/DDJ-1000/reference.png
        # (3129x1652) in v0.47.57 -- the earlier fractions were for the
        # callout-annotated ddj-1000-midi.png, a different crop/aspect. Left
        # deck (deck 1/3).
        # Display-only continuous control (see the note above): the left jog
        # platter. Blue-grey, matching XDJ-XZ's "Jog wheel". Turned by
        # ControllerLayoutView.spin_jog from live relative jog MIDI
        # (v0.47.64, gui/jog.py) -- decorative, no catalog entry.
        "Jog wheel": ControlGeometry(0.0180, 0.1029, 0.2550, 0.5315, "circle", "#586b82"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.0230, 0.8018, 0.0530, 0.1009, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.0230, 0.6858, 0.0530, 0.1009, "circle", "#e0954a"),
        # Teal: matches DDJ-XP2's MASTER TEMPO-adjacent utility accent.
        "MASTER TEMPO": ControlGeometry(0.2580, 0.6888, 0.0340, 0.0303, "rect", "#4ab8a0"),
        # Blue: matches XDJ-XZ/DDJ-XP2's SYNC/BEAT SYNC accent color.
        "BEAT SYNC": ControlGeometry(0.2920, 0.5255, 0.0260, 0.0444, "circle", "#4a90d9"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "KEY SYNC": ControlGeometry(0.2580, 0.7786, 0.0340, 0.0282, "rect", "#7a8aa0"),
        "KEY RESET": ControlGeometry(0.2580, 0.8290, 0.0340, 0.0303, "rect", "#7a8aa0"),
        # Amber: loop cluster, matches DDJ-XP2's loop accent family.
        "LOOP IN": ControlGeometry(0.0180, 0.0464, 0.0340, 0.0696, "circle", "#d9954a"),
        "LOOP OUT": ControlGeometry(0.0580, 0.0464, 0.0340, 0.0696, "circle", "#d9954a"),
        "4 BEAT LOOP/EXIT": ControlGeometry(0.0980, 0.0686, 0.0650, 0.0403, "rect", "#d9954a"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync
        # families. y re-measured (issue #118, "layout" session): QUANTIZE/
        # SLIP sat a whole button-height below the real buttons, and SLIP
        # REVERSE two button-heights below (landing past "REVERSE"'s own
        # label, into blank space near the jog wheel edge) -- found by
        # cropping the whole IN/OUT/4 BEAT LOOP/QUANTIZE/SLIP/SLIP REVERSE
        # row together rather than one control at a time.
        "QUANTIZE": ControlGeometry(0.2050, 0.0484, 0.0370, 0.0403, "rect", "#4ab8a0"),
        # Muted neutral: DDJ-1000's SLIP/SLIP REVERSE aren't a modifier key
        # like SHIFT, but a distinct playback-state toggle family of their own.
        "SLIP": ControlGeometry(0.2500, 0.0484, 0.0370, 0.0403, "rect", "#8f6fae"),
        "SLIP REVERSE": ControlGeometry(0.0100, 0.1230, 0.0480, 0.0262, "rect", "#8f6fae"),
        # Salmon-pink: matches the pad grid accent used on the other
        # controllers. Re-measured in v0.47.86 (issue #103): the fractions
        # below (v0.47.57) turned out imprecise -- a tight crop of the
        # shipped "Pad 1" entry comfortably spanned into "Pad 2" -- found
        # while measuring the right grid and re-verified against this
        # left grid with the same clean-crop technique (four columns +
        # both rows individually corner-checked, not eyeballed from a
        # cluttered wide shot). cols x = 0.081/0.127/0.172/0.217 (w
        # 0.038-0.040), rows y = 0.741/0.820 (h 0.070).
        "Pad 1": ControlGeometry(0.0808, 0.7469, 0.0399, 0.0703, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.1265, 0.7469, 0.0390, 0.0703, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.1719, 0.7469, 0.0383, 0.0703, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2166, 0.7469, 0.0383, 0.0703, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.0808, 0.8271, 0.0399, 0.0704, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.1265, 0.8271, 0.0390, 0.0704, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.1719, 0.8271, 0.0383, 0.0704, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2166, 0.8271, 0.0383, 0.0704, "rect", "#e0708f"),
        # Right deck (deck 2/4) -- issue #103: every entry above only ever
        # had its left-deck (deck 1/3) copy recorded, so a deck 2/4 hit had
        # no marker of its own on the real-position overlay at all (worse
        # than the DDJ-XP2/XDJ-XZ "right pad grid" gap the module docstring
        # already covers -- there, only the pad grid was missing; here nothing
        # on the right deck was modeled). Measured independently, control by
        # control, NOT by mirroring the left deck's fractions around a single
        # axis: an automated symmetry-axis detector found one that fit the
        # jog wheel well (it's huge and forgiving) but was off by several
        # percent for CUE/PLAY-PAUSE and the loop cluster once checked with a
        # tight crop -- this image's two decks are not a rigid mirror of each
        # other, so each entry below was independently cropped and confirmed
        # against controllers/hardware/pioneer/DDJ-1000/reference.png, same discipline as the
        # left deck. Live-hit flash resolution for these is also a known
        # follow-up: resolve_geometry_label only picks the " (R)" variant by
        # deck number for *pad*-numbered hits (_RIGHT_GRID_DECKS) -- DDJ-1000
        # non-pad ControlInfo names (e.g. "PLAY/PAUSE") carry no "Deck N"
        # prefix to key off at all, so a deck 2/4 press of these still
        # flashes the left marker. These entries are reachable today only via
        # the static "Show real layout" overlay, which draws every entry
        # unconditionally regardless of deck -- the specific gap issue #103
        # reported.
        "Jog wheel (R)": ControlGeometry(0.6332, 0.1029, 0.2550, 0.5315, "circle", "#586b82"),
        "PLAY/PAUSE (R)": ControlGeometry(0.6400, 0.8018, 0.0530, 0.1009, "circle", "#3ea86b"),
        "CUE (R)": ControlGeometry(0.6400, 0.6858, 0.0530, 0.1009, "circle", "#e0954a"),
        "MASTER TEMPO (R)": ControlGeometry(0.8870, 0.6888, 0.0340, 0.0303, "rect", "#4ab8a0"),
        "BEAT SYNC (R)": ControlGeometry(0.9234, 0.5255, 0.0260, 0.0444, "circle", "#4a90d9"),
        "KEY SYNC (R)": ControlGeometry(0.8870, 0.7786, 0.0340, 0.0282, "rect", "#7a8aa0"),
        "KEY RESET (R)": ControlGeometry(0.8870, 0.8290, 0.0340, 0.0303, "rect", "#7a8aa0"),
        "LOOP IN (R)": ControlGeometry(0.6332, 0.0464, 0.0340, 0.0696, "circle", "#d9954a"),
        "LOOP OUT (R)": ControlGeometry(0.6632, 0.0464, 0.0340, 0.0696, "circle", "#d9954a"),
        "4 BEAT LOOP/EXIT (R)": ControlGeometry(0.6903, 0.0686, 0.0650, 0.0403, "rect", "#d9954a"),
        # y re-measured alongside the left copy above -- same row-below bug.
        "QUANTIZE (R)": ControlGeometry(0.8258, 0.0484, 0.0370, 0.0403, "rect", "#4ab8a0"),
        "SLIP (R)": ControlGeometry(0.8530, 0.0484, 0.0370, 0.0403, "rect", "#8f6fae"),
        "SLIP REVERSE (R)": ControlGeometry(0.6165, 0.1230, 0.0570, 0.0303, "rect", "#8f6fae"),
        # Right pad grid -- v0.47.86 (issue #103), same clean-crop technique
        # as the left grid's re-measurement above, not a mirror of it (the
        # right grid's own columns measure ~0.033 wide vs the left's
        # ~0.038-0.040 -- close, but a mirror would have been off). cols x =
        # 0.710/0.753/0.795/0.838 (w 0.033), rows y = 0.741/0.820 (h 0.070,
        # same rows as the left grid).
        "Pad 1 (R)": ControlGeometry(0.7104, 0.7469, 0.0329, 0.0703, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.7529, 0.7469, 0.0326, 0.0703, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.7951, 0.7469, 0.0326, 0.0703, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.8377, 0.7469, 0.0326, 0.0703, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.7104, 0.8271, 0.0329, 0.0704, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.7529, 0.8271, 0.0326, 0.0704, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.7951, 0.8271, 0.0326, 0.0704, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.8377, 0.8271, 0.0326, 0.0704, "rect", "#e0708f"),
    },
    "DDJ-FLX10": {
        # Re-measured against the clean render controllers/hardware/pioneer/DDJ-FLX10/reference.png
        # (1792x1316) in v0.47.58 -- the earlier fractions were for the
        # callout-annotated ddj-flx10-midi.png, a different crop/aspect. Left
        # deck (deck 1/3).
        # Display-only continuous control (see the note above): the left jog
        # platter. Blue-grey, matching XDJ-XZ/DDJ-1000's "Jog wheel". Turned
        # by ControllerLayoutView.spin_jog from live relative jog MIDI
        # (v0.47.65, gui/jog.py) -- decorative, no catalog entry.
        "Jog wheel": ControlGeometry(0.0246, 0.1108, 0.2829, 0.6062, "circle", "#586b82"),
        # Green: matches PLAY/PAUSE's accent color on the other controllers.
        "PLAY/PAUSE": ControlGeometry(0.0213, 0.8598, 0.0710, 0.1232, "circle", "#3ea86b"),
        # Amber: matches CUE's accent color on the other controllers.
        "CUE": ControlGeometry(0.0213, 0.7352, 0.0710, 0.1232, "circle", "#e0954a"),
        # Blue: matches XDJ-XZ/DDJ-XP2's SYNC/BEAT SYNC accent color.
        "BEAT SYNC": ControlGeometry(0.2859, 0.7044, 0.0366, 0.0560, "rect", "#4a90d9"),
        # Teal: matches DDJ-XP2's MASTER TEMPO-adjacent utility accent.
        "TEMPO RESET": ControlGeometry(0.2870, 0.7940, 0.0280, 0.0448, "circle", "#4ab8a0"),
        # Gray-blue: utility accent, matches PAD MODE-style buttons elsewhere.
        "KEY SYNC": ControlGeometry(0.2859, 0.9060, 0.0366, 0.0532, "rect", "#7a8aa0"),
        # Purple: rekordbox stem control -- a distinct function family from
        # the loop/effect/sync accents used elsewhere.
        "ACTIVE PART DRUMS": ControlGeometry(0.0246, 0.0842, 0.0430, 0.0210, "rect", "#9b6fd9"),
        "ACTIVE PART VOCAL": ControlGeometry(0.0784, 0.0842, 0.0430, 0.0210, "rect", "#9b6fd9"),
        "ACTIVE PART INST": ControlGeometry(0.1321, 0.0842, 0.0430, 0.0210, "rect", "#9b6fd9"),
        # Muted neutral: browse/navigation-style buttons, not a function family.
        "CUE/LOOP CALL <": ControlGeometry(0.2010, 0.0800, 0.0183, 0.0322, "circle", "#5f6b7a"),
        "CUE/LOOP CALL >": ControlGeometry(0.2343, 0.0800, 0.0183, 0.0322, "circle", "#5f6b7a"),
        # Amber: loop cluster, matches DDJ-XP2/DDJ-1000's loop accent family.
        "LOOP IN / 1/2X": ControlGeometry(0.0289, 0.1444, 0.0409, 0.0672, "circle", "#d9954a"),
        "LOOP OUT / 2X": ControlGeometry(0.0859, 0.1444, 0.0409, 0.0672, "circle", "#d9954a"),
        "4 BEAT/EXIT": ControlGeometry(0.1418, 0.1444, 0.0409, 0.0672, "circle", "#d9954a"),
        # Muted neutral: mix-point navigation, not a function family.
        "MIX POINT SELECT <": ControlGeometry(0.2010, 0.1444, 0.0183, 0.0322, "circle", "#5f6b7a"),
        "MIX POINT SELECT >": ControlGeometry(0.2343, 0.1444, 0.0183, 0.0322, "circle", "#5f6b7a"),
        "MIX POINT LINK": ControlGeometry(0.2494, 0.1402, 0.0237, 0.0392, "circle", "#5f6b7a"),
        # Muted neutral: a distinct playback-state toggle family, matching
        # DDJ-1000's SLIP/SLIP REVERSE coloring.
        "SLIP REVERSE": ControlGeometry(0.0213, 0.2088, 0.0473, 0.0280, "rect", "#8f6fae"),
        "SLIP": ControlGeometry(0.3279, 0.2088, 0.0258, 0.0280, "rect", "#8f6fae"),
        # Teal: a distinct utility accent, separate from the loop/effect/sync families.
        "QUANTIZE": ControlGeometry(0.2978, 0.2088, 0.0258, 0.0280, "rect", "#4ab8a0"),
        # Muted neutral: browse/navigation-style buttons, not a function family.
        "4 BEAT JUMP <": ControlGeometry(0.0256, 0.6932, 0.0344, 0.0476, "rect", "#5f6b7a"),
        "4 BEAT JUMP >": ControlGeometry(0.0665, 0.6932, 0.0344, 0.0476, "rect", "#5f6b7a"),
        # Muted neutral: a modifier key, not a function.
        "SHIFT": ControlGeometry(0.0203, 0.6176, 0.0269, 0.0420, "rect", "#5f6b7a"),
        # Salmon-pink: matches the pad grid accent used on the other
        # controllers. Re-measured in v0.47.87 (issue #103) alongside the
        # right grid, with the clean-uncluttered-crop-per-grid technique
        # established for DDJ-1000's re-measurement -- the values below
        # (v0.47.58) checked out close but not identical under a tight
        # crop, refined slightly rather than left approximate now that a
        # precise right grid needs a precise left one to sit next to.
        # Height re-measured again in the issue-#118 ("layout") pass: 0.053
        # ran noticeably taller than the real pad (0.038), reaching past its
        # bottom edge toward the next row.
        # cols x = 0.122/0.164/0.204/0.245 (w 0.036), rows y = 0.723/0.774
        # (h 0.038).
        "Pad 1": ControlGeometry(0.0937, 0.8122, 0.0390, 0.0532, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.1383, 0.8122, 0.0384, 0.0532, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.1820, 0.8122, 0.0385, 0.0532, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.2259, 0.8122, 0.0385, 0.0532, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.0937, 0.8836, 0.0390, 0.0532, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.1383, 0.8836, 0.0384, 0.0532, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.1820, 0.8836, 0.0385, 0.0532, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.2259, 0.8836, 0.0385, 0.0532, "rect", "#e0708f"),
        # Right pad grid -- v0.47.87 (issue #103), same clean-crop technique,
        # measured independently, not mirrored (its columns land a hair
        # narrower than the left grid's, ~0.035 vs ~0.036, consistent with
        # what DDJ-1000's independent left/right measurements also showed).
        # Height re-measured with the left grid in the issue-#118 pass, same
        # over-tall bug. cols x = 0.743/0.784/0.825/0.865 (w 0.035), rows
        # y = 0.723/0.774 (h 0.038, same rows as the left grid).
        "Pad 1 (R)": ControlGeometry(0.7417, 0.8122, 0.0384, 0.0532, "rect", "#e0708f"),
        "Pad 2 (R)": ControlGeometry(0.7861, 0.8122, 0.0379, 0.0532, "rect", "#e0708f"),
        "Pad 3 (R)": ControlGeometry(0.8300, 0.8122, 0.0379, 0.0532, "rect", "#e0708f"),
        "Pad 4 (R)": ControlGeometry(0.8739, 0.8122, 0.0379, 0.0532, "rect", "#e0708f"),
        "Pad 5 (R)": ControlGeometry(0.7417, 0.8836, 0.0384, 0.0532, "rect", "#e0708f"),
        "Pad 6 (R)": ControlGeometry(0.7861, 0.8836, 0.0379, 0.0532, "rect", "#e0708f"),
        "Pad 7 (R)": ControlGeometry(0.8300, 0.8836, 0.0379, 0.0532, "rect", "#e0708f"),
        "Pad 8 (R)": ControlGeometry(0.8739, 0.8836, 0.0379, 0.0532, "rect", "#e0708f"),
        # Right deck (deck 2/4) -- issue #103, same treatment as DDJ-1000
        # (v0.47.83) and DDJ-REV1 (v0.47.84): every entry above only ever
        # had its left-deck (deck 1/3) copy recorded. Every entry below was
        # independently measured and crop-verified against
        # controllers/hardware/pioneer/DDJ-FLX10/reference.png, not derived from a
        # symmetry-axis mirror -- same lesson carried over from DDJ-1000.
        # The pad grid's right-deck copy is a known-remaining gap, same
        # category as DDJ-REV1's (the shipped left "Pad 1" here checked out
        # fine under a tight crop, but the right grid's own bounds weren't
        # attempted this round given the size of this controller's non-pad
        # set alone) -- left for a follow-up (issue #103). Live-hit flash
        # resolution stays left-deck-only for these, same reason as
        # DDJ-1000/DDJ-REV1: resolve_geometry_label only keys off deck
        # number for pad-numbered hits, and DDJ-FLX10's non-pad ControlInfo
        # names carry no "Deck N" prefix to resolve a deck from.
        "Jog wheel (R)": ControlGeometry(0.7022, 0.1108, 0.2829, 0.6062, "circle", "#586b82"),
        "PLAY/PAUSE (R)": ControlGeometry(0.6579, 0.8598, 0.0710, 0.1232, "circle", "#3ea86b"),
        "CUE (R)": ControlGeometry(0.6579, 0.7352, 0.0710, 0.1232, "circle", "#e0954a"),
        "BEAT SYNC (R)": ControlGeometry(0.9036, 0.7044, 0.0366, 0.0560, "rect", "#4a90d9"),
        "TEMPO RESET (R)": ControlGeometry(0.9078, 0.7940, 0.0280, 0.0448, "circle", "#4ab8a0"),
        "KEY SYNC (R)": ControlGeometry(0.9041, 0.8850, 0.0366, 0.0420, "rect", "#7a8aa0"),
        # x re-measured (issue #118, "layout" session): VOCAL/INST sat far
        # enough left of the real buttons to overlap DRUMS -- reported by
        # the maintainer as messy overlapping boxes here.
        "ACTIVE PART DRUMS (R)": ControlGeometry(0.6635, 0.0747, 0.0366, 0.0216, "rect", "#9b6fd9"),
        "ACTIVE PART VOCAL (R)": ControlGeometry(0.7065, 0.0747, 0.0344, 0.0216, "rect", "#9b6fd9"),
        "ACTIVE PART INST (R)": ControlGeometry(0.7474, 0.0747, 0.0366, 0.0216, "rect", "#9b6fd9"),
        "CUE/LOOP CALL < (R)": ControlGeometry(0.8286, 0.0563, 0.0183, 0.0322, "circle", "#5f6b7a"),
        "CUE/LOOP CALL > (R)": ControlGeometry(0.9251, 0.0563, 0.0183, 0.0322, "circle", "#5f6b7a"),
        "LOOP IN / 1/2X (R)": ControlGeometry(0.6639, 0.1182, 0.0271, 0.0469, "circle", "#d9954a"),
        "LOOP OUT / 2X (R)": ControlGeometry(0.7018, 0.1182, 0.0265, 0.0469, "circle", "#d9954a"),
        "4 BEAT/EXIT (R)": ControlGeometry(0.7402, 0.1182, 0.0271, 0.0469, "circle", "#d9954a"),
        "MIX POINT SELECT < (R)": ControlGeometry(0.8224, 0.1333, 0.0183, 0.0322, "circle", "#5f6b7a"),
        "MIX POINT SELECT > (R)": ControlGeometry(0.8739, 0.1333, 0.0183, 0.0322, "circle", "#5f6b7a"),
        "MIX POINT LINK (R)": ControlGeometry(0.9035, 0.1298, 0.0237, 0.0392, "circle", "#5f6b7a"),
        "SLIP REVERSE (R)": ControlGeometry(0.6511, 0.2032, 0.0473, 0.0280, "rect", "#8f6fae"),
        "SLIP (R)": ControlGeometry(0.9688, 0.2088, 0.0258, 0.0280, "rect", "#8f6fae"),
        "QUANTIZE (R)": ControlGeometry(0.9219, 0.2088, 0.0258, 0.0280, "rect", "#4ab8a0"),
        "4 BEAT JUMP < (R)": ControlGeometry(0.6603, 0.6932, 0.0344, 0.0476, "rect", "#5f6b7a"),
        "4 BEAT JUMP > (R)": ControlGeometry(0.6934, 0.6932, 0.0344, 0.0476, "rect", "#5f6b7a"),
        "SHIFT (R)": ControlGeometry(0.6592, 0.6316, 0.0269, 0.0420, "rect", "#5f6b7a"),
    },
    "Korg nanoPAD2": {
        # Measured against controllers/hardware/korg/nanoPAD2/reference.png
        # (1200x800): the pads are unlit, so each one's thin black outline
        # was located on luminance profiles through every pad row and column
        # (exact pixel bounds). The catalog models the 4 scenes as pad modes
        # ("Pad N (SCENE S)"), so these 16 markers resolve a live hit from
        # any scene through the usual pad-number path. Pink: the pad color
        # every other controller's pad grid uses.
        "Pad 1": ControlGeometry(0.2818, 0.2697, 0.0733, 0.2762, "rect", "#e0708f"),
        "Pad 2": ControlGeometry(0.3685, 0.2697, 0.0723, 0.2762, "rect", "#e0708f"),
        "Pad 3": ControlGeometry(0.4542, 0.2697, 0.0733, 0.2762, "rect", "#e0708f"),
        "Pad 4": ControlGeometry(0.5410, 0.2697, 0.0723, 0.2762, "rect", "#e0708f"),
        "Pad 5": ControlGeometry(0.6360, 0.2697, 0.0723, 0.2762, "rect", "#e0708f"),
        "Pad 6": ControlGeometry(0.7217, 0.2697, 0.0723, 0.2762, "rect", "#e0708f"),
        "Pad 7": ControlGeometry(0.8084, 0.2697, 0.0723, 0.2762, "rect", "#e0708f"),
        "Pad 8": ControlGeometry(0.8931, 0.2697, 0.0723, 0.2762, "rect", "#e0708f"),
        "Pad 9": ControlGeometry(0.2818, 0.5980, 0.0733, 0.2736, "rect", "#e0708f"),
        "Pad 10": ControlGeometry(0.3685, 0.5980, 0.0723, 0.2736, "rect", "#e0708f"),
        "Pad 11": ControlGeometry(0.4542, 0.5980, 0.0733, 0.2736, "rect", "#e0708f"),
        "Pad 12": ControlGeometry(0.5410, 0.5980, 0.0723, 0.2736, "rect", "#e0708f"),
        "Pad 13": ControlGeometry(0.6360, 0.5980, 0.0723, 0.2736, "rect", "#e0708f"),
        "Pad 14": ControlGeometry(0.7217, 0.5980, 0.0723, 0.2736, "rect", "#e0708f"),
        "Pad 15": ControlGeometry(0.8084, 0.5980, 0.0723, 0.2736, "rect", "#e0708f"),
        "Pad 16": ControlGeometry(0.8931, 0.5980, 0.0723, 0.2736, "rect", "#e0708f"),
    },
    "Behringer CMD Micro": {
        # Measured against controllers/hardware/behringer/CMD-micro/reference.png
        # (974x267, flat top-down render): every button's lit outline was
        # located as a connected component of saturated pixels, so these are
        # the outline's own pixel bounds, not eyeballed. Labels are the
        # catalog names themselves, which already carry their deck ("Deck A
        # SYNC", "LOAD B"), so live hits resolve on both decks without any
        # _RIGHT_GRID_DECKS entry. Colors follow the hardware LEDs: green
        # PLAY, blue CUE, amber for the rest; the browse arrows are neutral.
        "Deck A 1": ControlGeometry(0.2820, 0.0756, 0.0440, 0.1021, "rect", "#e0954a"),
        "Deck A 2": ControlGeometry(0.2820, 0.2647, 0.0470, 0.1021, "rect", "#e0954a"),
        "Deck A SYNC": ControlGeometry(0.2820, 0.4579, 0.0440, 0.1780, "rect", "#e0954a"),
        "Deck A PLAY/PAUSE": ControlGeometry(0.2170, 0.7350, 0.0440, 0.1628, "rect", "#3ea86b"),
        "Deck A CUE": ControlGeometry(0.2820, 0.7350, 0.0440, 0.1628, "rect", "#4a90d9"),
        "Deck A PITCHBEND -": ControlGeometry(0.0620, 0.7876, 0.0450, 0.0870, "rect", "#e0954a"),
        "Deck A PITCHBEND +": ControlGeometry(0.1270, 0.7876, 0.0450, 0.0910, "rect", "#e0954a"),
        "LOAD A": ControlGeometry(0.3490, 0.0756, 0.0470, 0.1133, "rect", "#e0954a"),
        "CUE A": ControlGeometry(0.3490, 0.7957, 0.0460, 0.0981, "rect", "#e0954a"),
        "LEFT": ControlGeometry(0.4200, 0.3254, 0.0440, 0.1021, "rect", "#7a8aa0"),
        "RIGHT": ControlGeometry(0.5380, 0.3254, 0.0440, 0.1021, "rect", "#7a8aa0"),
        "LOAD B": ControlGeometry(0.6090, 0.0716, 0.0480, 0.1062, "rect", "#e0954a"),
        "CUE B": ControlGeometry(0.6090, 0.7957, 0.0440, 0.0981, "rect", "#e0954a"),
        "Deck B 1": ControlGeometry(0.6740, 0.0756, 0.0460, 0.1021, "rect", "#e0954a"),
        "Deck B 2": ControlGeometry(0.6740, 0.2647, 0.0460, 0.1102, "rect", "#e0954a"),
        "Deck B SYNC": ControlGeometry(0.6760, 0.4579, 0.0440, 0.1780, "rect", "#e0954a"),
        "Deck B PLAY/PAUSE": ControlGeometry(0.6760, 0.7350, 0.0440, 0.1628, "rect", "#3ea86b"),
        "Deck B CUE": ControlGeometry(0.7410, 0.7350, 0.0440, 0.1628, "rect", "#4a90d9"),
        "Deck B PITCHBEND -": ControlGeometry(0.8300, 0.7917, 0.0450, 0.0870, "rect", "#e0954a"),
        "Deck B PITCHBEND +": ControlGeometry(0.8950, 0.7917, 0.0450, 0.0870, "rect", "#e0954a"),
    },
    "Behringer CMD LC-1": {
        # Measured against controllers/hardware/behringer/CMD-LC-1/reference.png
        # after scripts/process_controller_images.py (2000x4027): every one of
        # the 52 buttons is lit in the photo, so each outline is a connected
        # component of saturated pixels (exact pixel bounds), 13 rows of 4.
        # Labels are the catalog names. Amber: the numbered and MUTE/SOLO/
        # RECORD buttons; pink: the 8x4 clip grid, like every pad grid.
        "Button 1": ControlGeometry(0.1420, 0.2754, 0.1345, 0.0340, "rect", "#e0954a"),
        "Button 2": ControlGeometry(0.3415, 0.2754, 0.1340, 0.0340, "rect", "#e0954a"),
        "Button 3": ControlGeometry(0.5420, 0.2754, 0.1340, 0.0340, "rect", "#e0954a"),
        "Button 4": ControlGeometry(0.7410, 0.2754, 0.1350, 0.0343, "rect", "#e0954a"),
        "Button 5": ControlGeometry(0.1420, 0.3206, 0.1350, 0.0345, "rect", "#e0954a"),
        "Button 6": ControlGeometry(0.3415, 0.3208, 0.1340, 0.0340, "rect", "#e0954a"),
        "Button 7": ControlGeometry(0.5420, 0.3206, 0.1340, 0.0345, "rect", "#e0954a"),
        "Button 8": ControlGeometry(0.7410, 0.3206, 0.1345, 0.0343, "rect", "#e0954a"),
        "Row 1 Button 1": ControlGeometry(0.1380, 0.3673, 0.1425, 0.0444, "rect", "#e0708f"),
        "Row 1 Button 2": ControlGeometry(0.3385, 0.3675, 0.1410, 0.0440, "rect", "#e0708f"),
        "Row 1 Button 3": ControlGeometry(0.5380, 0.3673, 0.1415, 0.0444, "rect", "#e0708f"),
        "Row 1 Button 4": ControlGeometry(0.7375, 0.3675, 0.1420, 0.0440, "rect", "#e0708f"),
        "Row 2 Button 1": ControlGeometry(0.1385, 0.4254, 0.1415, 0.0440, "rect", "#e0708f"),
        "Row 2 Button 2": ControlGeometry(0.3370, 0.4251, 0.1420, 0.0442, "rect", "#e0708f"),
        "Row 2 Button 3": ControlGeometry(0.5380, 0.4251, 0.1415, 0.0442, "rect", "#e0708f"),
        "Row 2 Button 4": ControlGeometry(0.7380, 0.4254, 0.1415, 0.0440, "rect", "#e0708f"),
        "Row 3 Button 1": ControlGeometry(0.1385, 0.4837, 0.1415, 0.0437, "rect", "#e0708f"),
        "Row 3 Button 2": ControlGeometry(0.3385, 0.4835, 0.1410, 0.0442, "rect", "#e0708f"),
        "Row 3 Button 3": ControlGeometry(0.5385, 0.4837, 0.1405, 0.0437, "rect", "#e0708f"),
        "Row 3 Button 4": ControlGeometry(0.7375, 0.4835, 0.1420, 0.0442, "rect", "#e0708f"),
        "Row 4 Button 1": ControlGeometry(0.1380, 0.5413, 0.1425, 0.0447, "rect", "#e0708f"),
        "Row 4 Button 2": ControlGeometry(0.3370, 0.5416, 0.1420, 0.0444, "rect", "#e0708f"),
        "Row 4 Button 3": ControlGeometry(0.5385, 0.5416, 0.1405, 0.0444, "rect", "#e0708f"),
        "Row 4 Button 4": ControlGeometry(0.7380, 0.5416, 0.1410, 0.0444, "rect", "#e0708f"),
        "Row 5 Button 1": ControlGeometry(0.1385, 0.5990, 0.1415, 0.0447, "rect", "#e0708f"),
        "Row 5 Button 2": ControlGeometry(0.3380, 0.5990, 0.1415, 0.0447, "rect", "#e0708f"),
        "Row 5 Button 3": ControlGeometry(0.5380, 0.5990, 0.1415, 0.0449, "rect", "#e0708f"),
        "Row 5 Button 4": ControlGeometry(0.7380, 0.5990, 0.1415, 0.0447, "rect", "#e0708f"),
        "Row 6 Button 1": ControlGeometry(0.1385, 0.6573, 0.1415, 0.0437, "rect", "#e0708f"),
        "Row 6 Button 2": ControlGeometry(0.3370, 0.6573, 0.1420, 0.0440, "rect", "#e0708f"),
        "Row 6 Button 3": ControlGeometry(0.5385, 0.6573, 0.1410, 0.0440, "rect", "#e0708f"),
        "Row 6 Button 4": ControlGeometry(0.7380, 0.6576, 0.1410, 0.0437, "rect", "#e0708f"),
        "Row 7 Button 1": ControlGeometry(0.1385, 0.7144, 0.1420, 0.0449, "rect", "#e0708f"),
        "Row 7 Button 2": ControlGeometry(0.3385, 0.7144, 0.1410, 0.0447, "rect", "#e0708f"),
        "Row 7 Button 3": ControlGeometry(0.5385, 0.7144, 0.1410, 0.0449, "rect", "#e0708f"),
        "Row 7 Button 4": ControlGeometry(0.7375, 0.7144, 0.1420, 0.0449, "rect", "#e0708f"),
        "Row 8 Button 1": ControlGeometry(0.1385, 0.7720, 0.1420, 0.0449, "rect", "#e0708f"),
        "Row 8 Button 2": ControlGeometry(0.3370, 0.7720, 0.1420, 0.0454, "rect", "#e0708f"),
        "Row 8 Button 3": ControlGeometry(0.5380, 0.7718, 0.1415, 0.0457, "rect", "#e0708f"),
        "Row 8 Button 4": ControlGeometry(0.7375, 0.7720, 0.1420, 0.0452, "rect", "#e0708f"),
        "MUTE 1": ControlGeometry(0.1420, 0.8351, 0.1345, 0.0345, "rect", "#e0954a"),
        "MUTE 2": ControlGeometry(0.3420, 0.8349, 0.1335, 0.0348, "rect", "#e0954a"),
        "MUTE 3": ControlGeometry(0.5420, 0.8351, 0.1340, 0.0345, "rect", "#e0954a"),
        "MUTE 4": ControlGeometry(0.7415, 0.8349, 0.1340, 0.0348, "rect", "#e0954a"),
        "SOLO 1": ControlGeometry(0.1425, 0.8845, 0.1340, 0.0345, "rect", "#e0954a"),
        "SOLO 2": ControlGeometry(0.3415, 0.8845, 0.1340, 0.0345, "rect", "#e0954a"),
        "SOLO 3": ControlGeometry(0.5425, 0.8845, 0.1335, 0.0345, "rect", "#e0954a"),
        "SOLO 4": ControlGeometry(0.7415, 0.8845, 0.1340, 0.0345, "rect", "#e0954a"),
        "RECORD 1": ControlGeometry(0.1420, 0.9342, 0.1345, 0.0345, "rect", "#e0954a"),
        "RECORD 2": ControlGeometry(0.3420, 0.9342, 0.1335, 0.0348, "rect", "#e0954a"),
        "RECORD 3": ControlGeometry(0.5420, 0.9342, 0.1345, 0.0345, "rect", "#e0954a"),
        "RECORD 4": ControlGeometry(0.7415, 0.9342, 0.1340, 0.0348, "rect", "#e0954a"),
    },
    "Behringer CMD Studio 4a": {
        # Measured against controllers/hardware/behringer/CMD-studio-4a/reference.png
        # (971x615, flat top-down render) the same way as the CMD Micro: each
        # lit button outline's exact pixel bounds. Labels are the catalog
        # names; each side's names cover both of its deck layers ("(A/C)",
        # "(B/D)"), so a live hit resolves on either layer. The right LOOP
        # arrows are placed by their printed arrow, matching the catalog's
        # reversed notes (55 = ">", 56 = "<").
        "<": ControlGeometry(0.0230, 0.1190, 0.0380, 0.0310, "rect", "#7a8aa0"),
        ">": ControlGeometry(0.0700, 0.1190, 0.0380, 0.0310, "rect", "#7a8aa0"),
        "ENTER": ControlGeometry(0.0460, 0.1670, 0.0380, 0.0310, "rect", "#7a8aa0"),
        "DECK A": ControlGeometry(0.0460, 0.2340, 0.0380, 0.0520, "rect", "#4a90d9"),
        "DECK C": ControlGeometry(0.0460, 0.3120, 0.0380, 0.0520, "rect", "#e0954a"),
        "DECK B": ControlGeometry(0.9130, 0.2340, 0.0390, 0.0520, "rect", "#4a90d9"),
        "DECK D": ControlGeometry(0.9130, 0.3120, 0.0390, 0.0520, "rect", "#e0954a"),
        "FX 1 1 (A/C)": ControlGeometry(0.1460, 0.1190, 0.0380, 0.0310, "rect", "#e0954a"),
        "FX 1 2 (A/C)": ControlGeometry(0.2060, 0.1190, 0.0380, 0.0310, "rect", "#e0954a"),
        "FX 1 3 (A/C)": ControlGeometry(0.2660, 0.1190, 0.0380, 0.0310, "rect", "#e0954a"),
        "FX 1 4 (A/C)": ControlGeometry(0.3250, 0.1190, 0.0380, 0.0310, "rect", "#e0954a"),
        "LOOP < (A/C)": ControlGeometry(0.2060, 0.1850, 0.0380, 0.0310, "rect", "#e0954a"),
        "LOOP > (A/C)": ControlGeometry(0.2660, 0.1850, 0.0380, 0.0310, "rect", "#e0954a"),
        "LOOP ON/OFF (A/C)": ControlGeometry(0.3250, 0.1870, 0.0380, 0.0520, "rect", "#e0954a"),
        "SCRATCH (A/C)": ControlGeometry(0.1160, 0.2390, 0.0280, 0.0420, "circle", "#e0954a"),
        "LOCK (A/C)": ControlGeometry(0.0490, 0.4230, 0.0330, 0.0280, "rect", "#e0954a"),
        "PITCH BEND - (A/C)": ControlGeometry(0.0290, 0.8850, 0.0330, 0.0280, "rect", "#e0954a"),
        "PITCH BEND + (A/C)": ControlGeometry(0.0700, 0.8850, 0.0320, 0.0280, "rect", "#e0954a"),
        "CUE (A/C)": ControlGeometry(0.1570, 0.8680, 0.0460, 0.0600, "rect", "#e0708f"),
        "PLAY/PAUSE (A/C)": ControlGeometry(0.2320, 0.8680, 0.0460, 0.0600, "rect", "#3ea86b"),
        "SYNC (A/C)": ControlGeometry(0.3070, 0.8680, 0.0460, 0.0600, "rect", "#e0954a"),
        "HOT CUE 1 (A/C)": ControlGeometry(0.1570, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 2 (A/C)": ControlGeometry(0.1980, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 3 (A/C)": ControlGeometry(0.2390, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 4 (A/C)": ControlGeometry(0.2800, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE DEL (A/C)": ControlGeometry(0.3210, 0.7740, 0.0320, 0.0260, "rect", "#e0954a"),
        "HOT CUE 5 (A/C)": ControlGeometry(0.1570, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 6 (A/C)": ControlGeometry(0.1980, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 7 (A/C)": ControlGeometry(0.2390, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 8 (A/C)": ControlGeometry(0.2800, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "LOAD (A/C)": ControlGeometry(0.4220, 0.0630, 0.0380, 0.0310, "rect", "#e0954a"),
        "FX ASSIGN 1 (A/C)": ControlGeometry(0.4050, 0.1200, 0.0330, 0.0280, "rect", "#e0954a"),
        "FX ASSIGN 2 (A/C)": ControlGeometry(0.4450, 0.1200, 0.0330, 0.0280, "rect", "#e0954a"),
        "PHONES (A/C)": ControlGeometry(0.4240, 0.5300, 0.0340, 0.0260, "rect", "#e0954a"),
        "KILL HIGH (A/C)": ControlGeometry(0.4470, 0.2620, 0.0330, 0.0280, "rect", "#e0954a"),
        "KILL MID (A/C)": ControlGeometry(0.4470, 0.3720, 0.0330, 0.0260, "rect", "#e0954a"),
        "KILL LOW (A/C)": ControlGeometry(0.4470, 0.4830, 0.0330, 0.0260, "rect", "#e0954a"),
        "FX 2 1 (B/D)": ControlGeometry(0.6340, 0.1190, 0.0390, 0.0310, "rect", "#e0954a"),
        "FX 2 2 (B/D)": ControlGeometry(0.6940, 0.1190, 0.0390, 0.0310, "rect", "#e0954a"),
        "FX 2 3 (B/D)": ControlGeometry(0.7540, 0.1190, 0.0390, 0.0310, "rect", "#e0954a"),
        "FX 2 4 (B/D)": ControlGeometry(0.8140, 0.1190, 0.0390, 0.0310, "rect", "#e0954a"),
        "LOOP ON/OFF (B/D)": ControlGeometry(0.6340, 0.1870, 0.0390, 0.0520, "rect", "#e0954a"),
        "LOOP < (B/D)": ControlGeometry(0.6940, 0.1850, 0.0390, 0.0310, "rect", "#e0954a"),
        "LOOP > (B/D)": ControlGeometry(0.7540, 0.1850, 0.0390, 0.0310, "rect", "#e0954a"),
        "SCRATCH (B/D)": ControlGeometry(0.8550, 0.2390, 0.0270, 0.0420, "circle", "#e0954a"),
        "LOCK (B/D)": ControlGeometry(0.9170, 0.4230, 0.0330, 0.0280, "rect", "#e0954a"),
        "PITCH BEND - (B/D)": ControlGeometry(0.8960, 0.8850, 0.0330, 0.0280, "rect", "#e0954a"),
        "PITCH BEND + (B/D)": ControlGeometry(0.9370, 0.8850, 0.0330, 0.0280, "rect", "#e0954a"),
        "CUE (B/D)": ControlGeometry(0.6470, 0.8680, 0.0450, 0.0600, "rect", "#e0708f"),
        "PLAY/PAUSE (B/D)": ControlGeometry(0.7210, 0.8680, 0.0460, 0.0600, "rect", "#3ea86b"),
        "SYNC (B/D)": ControlGeometry(0.7960, 0.8680, 0.0460, 0.0600, "rect", "#e0954a"),
        "HOT CUE DEL (B/D)": ControlGeometry(0.6450, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 1 (B/D)": ControlGeometry(0.6860, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 2 (B/D)": ControlGeometry(0.7270, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 3 (B/D)": ControlGeometry(0.7680, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 4 (B/D)": ControlGeometry(0.8090, 0.7740, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 5 (B/D)": ControlGeometry(0.6860, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 6 (B/D)": ControlGeometry(0.7270, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 7 (B/D)": ControlGeometry(0.7680, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "HOT CUE 8 (B/D)": ControlGeometry(0.8090, 0.8210, 0.0330, 0.0260, "rect", "#e0954a"),
        "LOAD (B/D)": ControlGeometry(0.5380, 0.0630, 0.0390, 0.0310, "rect", "#e0954a"),
        "FX ASSIGN 1 (B/D)": ControlGeometry(0.5210, 0.1200, 0.0330, 0.0280, "rect", "#e0954a"),
        "FX ASSIGN 2 (B/D)": ControlGeometry(0.5600, 0.1200, 0.0340, 0.0280, "rect", "#e0954a"),
        "PHONES (B/D)": ControlGeometry(0.5410, 0.5300, 0.0330, 0.0260, "rect", "#e0954a"),
        "KILL HIGH (B/D)": ControlGeometry(0.5190, 0.2620, 0.0330, 0.0280, "rect", "#e0954a"),
        "KILL MID (B/D)": ControlGeometry(0.5190, 0.3720, 0.0330, 0.0260, "rect", "#e0954a"),
        "KILL LOW (B/D)": ControlGeometry(0.5190, 0.4830, 0.0330, 0.0260, "rect", "#e0954a"),
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
    # v0.47.86 (issue #103): DDJ-1000's pad_lookup() names already carry a
    # "Deck N" prefix (unlike its other DECK entries, which don't -- see
    # this controller's " (R)" comment above), so now that the right pad
    # grid has its own geometry, this existing pad-specific resolution path
    # picks it up for free. Deck 2/4 = right tray, confirmed both by the
    # reference photo's own "DECK SELECT 2/4" label on that side and by
    # catalog/ddj_1000.py's channel-per-deck convention (_DECK_CHANNELS =
    # "1","2","3","4" maps 1:1 to deck number).
    "DDJ-1000": frozenset({2, 4}),
    # v0.47.87: same story as DDJ-1000 -- DDJ-FLX10's _pad_lookup() names
    # already carry a "Deck N" prefix, and _PAD_CHANNELS maps channels
    # 8/9->deck 1, 10/11->deck 2, 12/13->deck 3, 14/15->deck 4, so deck 2/4
    # is the right tray by the same convention.
    "DDJ-FLX10": frozenset({2, 4}),
    # v0.47.89: Numark Mixtrack Pro FX has only two decks (not four), and
    # its _pad_lookup() names already carry a "Deck N" prefix the same way
    # DDJ-1000/DDJ-FLX10's do, so deck 2 (right tray) resolves for free once
    # the right pad grid's geometry exists.
    "Numark Mixtrack Pro FX": frozenset({2}),
    # issue-#118 ("layout") pass: DDJ-REV1's _pad_lookup() names already
    # carry a "Deck N" prefix too, and _PAD_CHANNELS maps channels
    # 8/9->deck 1, 10/11->deck 2, 12/13->deck 3, 14/15->deck 4, same
    # channel-per-deck convention as DDJ-1000/DDJ-FLX10 -- deck 2/4 is the
    # right tray, and now that its pad grid has geometry, resolves for free.
    "DDJ-REV1": frozenset({2, 4}),
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
