from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui import controller_image_view
from djmidi.gui import geometry as geometry_mod
from djmidi.gui import jog as jog_mod
from djmidi.gui import layout as layout_mod
from djmidi.gui.layout import CellKey
from djmidi.gui.live_send import LiveSendControl

_KEY_ROLE = 0
# The VisualKind ("knob"/"fader"/"jog"/"button"/"pad") a glyph item was
# drawn as, set by draw_control_glyph() on every sub-item alongside
# _KEY_ROLE -- lets a caller (the Controller Emulator's drag-to-set
# gesture, phase 3) tell a continuous control apart from a discrete one
# without re-deriving visual_kind_for()/_DISPLAY_CONTROLS itself.
_KIND_ROLE = 1
_ALL_DECKS = "All decks"


@dataclass(frozen=True)
class LayoutMetrics:
    """Per-controller schematic proportions.

    Still a schematic, not a scaled replica — but a DDJ-XP2 (a compact,
    pad-dominant battle controller) and an XDJ-XZ (a wide 2-deck standalone
    with a big central mixer) should not render as the same uniform grid of
    identical boxes. Only the pixel geometry changes here; the (row, col)
    grid from ``layout.build_layout`` is untouched.
    """

    cell_w: int = 170
    half_h: int = 44
    margin: int = 6
    pad_glyph: int = 30
    button_glyph: int = 28
    knob_glyph: int = 32
    jog_glyph: int = 32
    fader_glyph_h: int = 32
    label_x: int = 42

    @property
    def cell_h(self) -> int:
        return self.half_h * 2


_DEFAULT_METRICS = LayoutMetrics()
_METRICS: dict[str, LayoutMetrics] = {
    # Compact and pad-forward: narrower cells, tighter gaps, chunky battle pads.
    "DDJ-XP2": LayoutMetrics(
        cell_w=158,
        half_h=42,
        margin=5,
        pad_glyph=34,
        button_glyph=26,
        knob_glyph=30,
        jog_glyph=30,
        fader_glyph_h=30,
        label_x=46,
    ),
    # Wide, airy 2-deck standalone: roomy cells, taller mixer faders and jogs,
    # slimmer performance pads.
    "XDJ-XZ": LayoutMetrics(
        cell_w=198,
        half_h=46,
        margin=9,
        pad_glyph=26,
        button_glyph=28,
        knob_glyph=34,
        jog_glyph=36,
        fader_glyph_h=40,
        label_x=44,
    ),
}


def metrics_for(controller: str) -> LayoutMetrics:
    return _METRICS.get(controller, _DEFAULT_METRICS)


# Reuse controller_image_view's own ASSETS_DIR (it already handles the
# PyInstaller-frozen-app case via sys._MEIPASS) rather than recomputing the
# same path resolution here -- a second, independent implementation of
# "find the repo/bundle root" is exactly the kind of thing that quietly
# drifts out of sync (an earlier version of this code did, using the wrong
# number of .parents[] hops and always falling back to _DEFAULT_CANVAS).
_DEFAULT_CANVAS = (1200, 800)
_REFERENCE_SIZE_CACHE: dict[str, tuple[int, int]] = {}
_REFERENCE_PIXMAP_CACHE: dict[str, QPixmap | None] = {}


def reference_pixmap(controller: str) -> QPixmap | None:
    """The controller's real reference photo (the same asset the Controller
    Images tab shows) as a QPixmap, or None when the controller declares no
    image or the file is missing. Cached; the one pixmap backs both
    _reference_canvas_size() below and the optional photo backdrop
    ControllerLayoutView / EmulatorLayoutView draw behind their
    real-position markers. Needs a QApplication, like any QPixmap."""
    if controller in _REFERENCE_PIXMAP_CACHE:
        return _REFERENCE_PIXMAP_CACHE[controller]
    pixmap: QPixmap | None = None
    reference_image = catalog.get_definition(controller).reference_image
    if reference_image:
        path = Path(reference_image)
        if not path.is_absolute():
            path = controller_image_view.ASSETS_DIR / reference_image
        if path.exists():
            loaded = QPixmap(str(path))
            if not loaded.isNull():
                pixmap = loaded
    _REFERENCE_PIXMAP_CACHE[controller] = pixmap
    return pixmap


def _reference_canvas_size(controller: str) -> tuple[int, int]:
    """The real photo's pixel dimensions for `controller`, used as the
    coordinate space for CONTROL_GEOMETRY's x/y/w/h fractions in the
    real-position layout mode -- matching controller_image_view.py's own
    fraction -> pixel math so a schematic marker lands where the photo
    overlay's marker would. Falls back to a fixed canvas if the reference
    image is missing (still renders something rather than crashing)."""
    cached = _REFERENCE_SIZE_CACHE.get(controller)
    if cached is not None:
        return cached
    pixmap = reference_pixmap(controller)
    size = (pixmap.width(), pixmap.height()) if pixmap is not None else _DEFAULT_CANVAS
    _REFERENCE_SIZE_CACHE[controller] = size
    return size


# Z-value for the real-photo backdrop -- well below every marker/glyph
# (which sit at the scene's default 0, some nudged to +1) so the schematic
# always draws on top of the photo, never behind it.
_PHOTO_Z = -100.0


def draw_reference_photo(scene: QGraphicsScene, controller: str) -> bool:
    """Add the controller's real reference photo as a backdrop behind a
    real-position schematic's markers, returning whether one was drawn
    (False when the controller declares no bundled/attached image). The
    marker rects real_position_markers() produces are already in this
    photo's own pixel space, so it drops in at (0, 0) with no scaling and
    the caller's existing setSceneRect(0, 0, canvas_w, canvas_h) still
    frames it exactly."""
    pixmap = reference_pixmap(controller)
    if pixmap is None:
        return False
    item = QGraphicsPixmapItem(pixmap)
    item.setZValue(_PHOTO_Z)
    scene.addItem(item)
    return True

# Real-position mode's *own* supplementary geometry for a controller's
# right-side mirrored cluster (SLIDE FX2, the second LOOP/QUANTIZE/KEY
# bank, and the right PAD MODE buttons on DDJ-XP2), measured the same way
# as everything in gui/geometry.py (crop + scaled gridline overlay, read by
# eye) but kept *out* of geometry.CONTROL_GEOMETRY on purpose: unlike pads,
# these controls' raw catalog names (e.g. "BEAT SYNC") don't carry a deck
# number at all, so geometry.resolve_geometry_label (used by Controller
# Images' live-flash overlay) has no way to route a live hit to the correct
# side the way it does for pads via _RIGHT_GRID_DECKS -- adding a same-named
# "BEAT SYNC (R)" marker there would silently steal that key's slot in
# geometry._reverse_index and break the left marker's live flash. This
# table is consumed only by _rebuild_real_position below, entirely
# independent of Controller Images. Reported by the maintainer as buttons
# "missing" and the layout "not symmetric" after phase R1's first pass only
# carried the pad grids' right side over.
_RIGHT_MIRROR_GEOMETRY: dict[str, dict[str, geometry_mod.ControlGeometry]] = {
    "DDJ-XP2": {
        # Re-measured against the clean render assets/controllers/ddj-xp2.png
        # in v0.47.54 (mirrors the CONTROL_GEOMETRY["DDJ-XP2"] re-measure) --
        # the right-tray copy of the DECK/PAD MODE/EFFECT clusters.
        "QUANTIZE": geometry_mod.ControlGeometry(0.678, 0.092, 0.044, 0.049, "circle", "#4ab8a0"),
        "4 BEAT LOOP": geometry_mod.ControlGeometry(0.733, 0.097, 0.094, 0.044, "rect", "#d9954a"),
        "1/2X": geometry_mod.ControlGeometry(0.734, 0.189, 0.050, 0.051, "rect", "#d9954a"),
        "2X": geometry_mod.ControlGeometry(0.791, 0.189, 0.050, 0.051, "rect", "#d9954a"),
        "BEAT SYNC": geometry_mod.ControlGeometry(0.648, 0.191, 0.054, 0.052, "rect", "#4a90d9"),
        "SILENT CUE": geometry_mod.ControlGeometry(0.788, 0.274, 0.054, 0.062, "rect", "#e0954a"),
        "KEY -": geometry_mod.ControlGeometry(0.585, 0.282, 0.043, 0.053, "rect", "#7a8aa0"),
        "KEY +": geometry_mod.ControlGeometry(0.652, 0.282, 0.043, 0.053, "rect", "#7a8aa0"),
        "PAD MODE 1": geometry_mod.ControlGeometry(0.513, 0.362, 0.091, 0.043, "rect", "#7a8aa0"),
        "PAD MODE 2": geometry_mod.ControlGeometry(0.622, 0.362, 0.091, 0.043, "rect", "#7a8aa0"),
        "PAD MODE 3": geometry_mod.ControlGeometry(0.730, 0.362, 0.091, 0.043, "rect", "#7a8aa0"),
        "PAD MODE 4": geometry_mod.ControlGeometry(0.840, 0.362, 0.088, 0.043, "rect", "#7a8aa0"),
        "EFFECT 1": geometry_mod.ControlGeometry(0.885, 0.109, 0.058, 0.040, "circle", "#9b6fd9"),
        "EFFECT 2": geometry_mod.ControlGeometry(0.885, 0.187, 0.058, 0.040, "circle", "#9b6fd9"),
        "EFFECT 3": geometry_mod.ControlGeometry(0.885, 0.284, 0.058, 0.040, "circle", "#9b6fd9"),
        "TOUCH STRIP HOLD": geometry_mod.ControlGeometry(0.882, 0.853, 0.063, 0.048, "rect", "#8fa0b3"),
        # "FX LEVEL" (geometry.py's label for the left slider) is aliased to
        # the schematic's "Slide FX 1" cell (see layout._LABEL_ALIASES); the
        # right slider maps directly to the schematic's own "Slide FX 2"
        # cell instead, so it's keyed by that name here directly rather
        # than needing a second alias.
        "Slide FX 2": geometry_mod.ControlGeometry(0.885, 0.435, 0.045, 0.377, "rect", "#6fa8c9"),
    },
    "XDJ-XZ": {
        # The right tray's transport cluster + PAD MODE buttons -- CONTROL_GEOMETRY
        # only ever records the left tray (deck 1/3); "Pad N (R)" (deck 2/4)
        # is already there via the pad-grid geometry, but PLAY/PAUSE, CUE,
        # SYNC, the jog wheel/tempo display markers, and the 4 PAD MODE
        # buttons need their own right-tray copy here.
        #
        # Re-measured against the clean render assets/controllers/xdj-xz.png
        # in v0.47.55 (mirrors the CONTROL_GEOMETRY["XDJ-XZ"] re-measure).
        # Each side is measured independently, not mirrored -- the wide
        # central mixer means the right jog wheel isn't a constant offset
        # from the left one.
        "PLAY/PAUSE": geometry_mod.ControlGeometry(0.674, 0.882, 0.052, 0.096, "circle", "#3ea86b"),
        "CUE": geometry_mod.ControlGeometry(0.674, 0.783, 0.052, 0.095, "circle", "#e0954a"),
        "SYNC": geometry_mod.ControlGeometry(0.917, 0.472, 0.026, 0.037, "circle", "#4a90d9"),
        "Jog wheel": geometry_mod.ControlGeometry(0.718, 0.310, 0.216, 0.378, "circle", "#586b82"),
        "Tempo": geometry_mod.ControlGeometry(0.945, 0.700, 0.028, 0.250, "rect", "#6fa8c9"),
        "HOT CUE": geometry_mod.ControlGeometry(0.735, 0.800, 0.055, 0.018, "rect", "#7a8aa0"),
        "BEAT LOOP": geometry_mod.ControlGeometry(0.795, 0.800, 0.055, 0.018, "rect", "#7a8aa0"),
        "SLIP LOOP": geometry_mod.ControlGeometry(0.853, 0.800, 0.055, 0.018, "rect", "#7a8aa0"),
        "BEAT JUMP": geometry_mod.ControlGeometry(0.912, 0.800, 0.053, 0.018, "rect", "#7a8aa0"),
    },
}


@dataclass(frozen=True)
class RealPositionMarker:
    """One real-position marker: a resolved CellKey, its true rect in the
    reference photo's own pixel space, and enough presentation data (shape,
    resting color, glyph kind) to draw it -- the single source of truth
    shared by ControllerLayoutView's real-position mode (this module) and
    the Controller Emulator's EmulatorLayoutView (gui/controller_emulator.py),
    so a controller's schematic reads identically in both places rather
    than two independently-drifting layouts (the maintainer explicitly
    asked for this parity after the two initially diverged)."""

    key: CellKey
    label: str
    rect: QRectF
    shape: geometry_mod.Shape
    color: str
    visual_kind: layout_mod.VisualKind


def real_position_markers(controller: str) -> list[RealPositionMarker]:
    """Every real-position marker for `controller` -- empty for a controller
    with no gui/geometry.CONTROL_GEOMETRY entries, which is exactly the
    signal callers use to fall back to the classic uniform card grid
    instead. Combines CONTROL_GEOMETRY with this module's own
    _RIGHT_MIRROR_GEOMETRY (see its docstring for why that table exists
    separately) and resolves each label to a schematic CellKey via
    layout.cell_key_for_geometry_label().

    A _RIGHT_MIRROR_GEOMETRY entry whose resolved cell falls in a section
    layout._RIGHT_SIDE_CHANNELS lists for this controller (DECK/PAD MODE --
    DDJ-XP2's second physical DECK+PAD MODE cluster, XDJ-XZ's right-tray
    transport; DDJ-XP2's EFFECT -- its second Slide FX chain's EFFECT
    1/2/3 + TOUCH STRIP HOLD buttons) gets its *displayed* label suffixed
    " (R)", even though its resolved `key` stays the same merged CellKey as
    the left cluster's. This mirrors exactly how a right-pad-grid label
    already carries the suffix directly in CONTROL_GEOMETRY (e.g. "Pad 3
    (R)"): callers that split click/flash identity on that suffix
    (gui/controller_emulator.py, gui/controller_image_view.py) and
    layout.resolve_side_aware_variant() (which narrows such an entry's
    multi-channel `channels` down to one side) then treat the two physical
    clusters independently for free, without this function needing to know
    anything about resolution itself.

    A mirror entry with NO resolved cell at all (a continuous, display-only
    control with no catalog entry, e.g. XDJ-XZ's right-tray "Tempo"/"Jog
    wheel") gets a *fully* distinct key too, not just a distinct label --
    unlike DECK/PAD MODE/EFFECT, there is no real shared trigger for the
    two sides to keep routing back to, so nothing is lost by giving each
    side its own independent `("DISPLAY", ...)` key; the alternative (both
    sides sharing one key) would make dragging the right Tempo fader also
    move the left one's glyph in EmulatorLayoutView, and vice versa -- the
    same class of bug as the click-through cases, just for a drag instead
    of a click. Any other EFFECT/MIXER-section mirror entry (e.g. XDJ-XZ
    has none; a future controller's Slide FX-style fader would be
    display-only too) is left unsuffixed -- it already resolves to its own
    distinct cell (e.g. "Slide FX 2" is a real cell in its own right, not a
    merged duplicate of "Slide FX 1"), so there is nothing to disambiguate."""
    geometry_entries = geometry_mod.CONTROL_GEOMETRY.get(controller)
    if not geometry_entries:
        return []
    canvas_w, canvas_h = _reference_canvas_size(controller)
    cells_by_key = {cell.key: cell for cell in layout_mod.build_layout(controller)}
    markers: list[RealPositionMarker] = []
    all_entries = itertools.chain(
        ((label, geom, False) for label, geom in geometry_entries.items()),
        ((label, geom, True) for label, geom in _RIGHT_MIRROR_GEOMETRY.get(controller, {}).items()),
    )
    for label, geom, is_mirror in all_entries:
        key = layout_mod.cell_key_for_geometry_label(controller, label)
        display_label = label
        if key is None:
            # No real trigger to share -- give a mirror entry its own fully
            # independent DISPLAY key (see the docstring above).
            display_label = f"{label}{layout_mod._RIGHT_GRID_SUFFIX}" if is_mirror else label
            key = (controller, "DISPLAY", display_label)
        elif is_mirror and key[1] in layout_mod._RIGHT_SIDE_CHANNELS.get(controller, {}):
            display_label = f"{label}{layout_mod._RIGHT_GRID_SUFFIX}"
        rect = QRectF(geom.x * canvas_w, geom.y * canvas_h, geom.w * canvas_w, geom.h * canvas_h)
        # A MIXER/display cell's kind comes from _DISPLAY_CONTROLS (e.g.
        # "Slide FX 2" is explicitly a fader), not the generic name-based
        # heuristic visual_kind_for() falls back to -- that heuristic
        # doesn't recognize "Slide FX 2" as a fader at all (no "fader"/
        # "level"/... substring), so it must come from the real LayoutCell
        # when one exists.
        resolved_cell = cells_by_key.get(key)
        visual_kind = (
            resolved_cell.visual_kind
            if resolved_cell is not None
            else layout_mod.visual_kind_for(key[1], key[2])
        )
        markers.append(RealPositionMarker(key, display_label, rect, geom.shape, geom.color, visual_kind))
    return markers


def glyph_size_for(metrics: LayoutMetrics, visual_kind: layout_mod.VisualKind) -> int:
    """The fixed glyph pixel size draw_control_glyph() will actually draw
    for `visual_kind`, so a caller centering that glyph inside a real
    geometry box (which is often a different size/aspect than the glyph
    itself) knows how big a footprint to center."""
    return {
        "pad": metrics.pad_glyph,
        "button": metrics.button_glyph,
        "knob": metrics.knob_glyph,
        "jog": metrics.jog_glyph,
        "fader": metrics.fader_glyph_h,
    }[visual_kind]


# cell key -> Serato deck number -> set of Serato function tags (mapping.tag)
# bound to that cell for that deck.
Usage = dict[CellKey, dict[str, set[str]]]
# cell key -> the other-controller cell key(s) that share at least one real
# (channel, event_type, control) trigger with it in the loaded config.
LinkedCells = dict[CellKey, set[CellKey]]

_SCENE_BRUSH = QBrush(QColor(13, 17, 25))
_ZONE_FILL_BRUSH = QBrush(QColor(17, 23, 34))
_ZONE_BORDER_PEN = QPen(QColor(44, 58, 80))
_ZONE_TITLE_COLOR = QColor("#6fe7d0")
_UNUSED_BRUSH = QBrush(QColor(29, 36, 49))
_EMPTY_HALF_BRUSH = QBrush(QColor(20, 26, 37))
_MULTI_DECK_BRUSH = QBrush(QColor(20, 91, 99))
_BORDER_PEN = QPen(QColor(65, 78, 98))
_DIVIDER_PEN = QPen(QColor(70, 83, 104))
_SELECTED_PEN = QPen(QColor(255, 61, 103))
_SELECTED_PEN.setWidth(3)
_HISTORY_PEN = QPen(QColor(142, 82, 98))
_HISTORY_PEN.setWidth(2)
_CONTROL_PEN = QPen(QColor(55, 65, 80))
_CONTROL_BRUSH = QBrush(QColor(215, 225, 238))
_PAD_BRUSH = QBrush(QColor(95, 125, 170))
_KNOB_BRUSH = QBrush(QColor(235, 190, 90))
_KNOB_RING_BRUSH = QBrush(QColor(47, 57, 73))
_FADER_PEN = QPen(QColor(55, 65, 80))
_FADER_PEN.setWidth(3)
_KNOB_MARKER_PEN = QPen(QColor(35, 38, 46))
_KNOB_MARKER_PEN.setWidth(2)
_FLASH_BRUSH = QBrush(QColor(255, 255, 255))
_FLASH_DURATION_MS = 220
# Persistent "toggled on" highlight for the Controller Emulator's phase 5
# toggle-state tracking (gui/output_state.py) -- distinct from both the
# transient white _FLASH_BRUSH (a 220ms press pulse) and _SELECTED_PEN
# (unrelated cross-tab selection, not used by the emulator at all): a warm
# amber border, evoking a lit hardware LED, that stays until the tracked
# state flips off again.
_ACTIVE_BORDER_PEN = QPen(QColor(255, 196, 60))
_ACTIVE_BORDER_PEN.setWidth(3)
_ACTIVE_FILL_ALPHA = 200
_MIDI_MAX = 127
_MIDI_DEFAULT = _MIDI_MAX // 2
_KNOB_MIN_ANGLE_DEG = -135.0
_KNOB_MAX_ANGLE_DEG = 135.0
# Degrees the jog notch turns per relative MIDI tick. Defined in gui/jog.py
# (a Qt-free module both this and controller_image_view import without a
# cycle); re-exported here under the name existing call sites already use.
_JOG_DEGREES_PER_TICK = jog_mod.DEGREES_PER_TICK


def _knob_angle_rad(value: int) -> float:
    """Angle (radians, clockwise from straight up) of a knob's marker for a
    7-bit MIDI value, sweeping a typical 270-degree rotary pot range."""
    clamped = max(0, min(_MIDI_MAX, value))
    angle_deg = _KNOB_MIN_ANGLE_DEG + (clamped / _MIDI_MAX) * (_KNOB_MAX_ANGLE_DEG - _KNOB_MIN_ANGLE_DEG)
    return math.radians(angle_deg)


def _fader_thumb_top(value: int, track_top: float, track_height: float, thumb_height: float) -> float:
    """Vertical position of a fader's thumb for a 7-bit MIDI value -- 0 at
    the bottom of the track, 127 at the top."""
    clamped = max(0, min(_MIDI_MAX, value))
    return track_top + (1 - clamped / _MIDI_MAX) * (track_height - thumb_height)

# One color per Serato deck number, so a glance at the layout shows which
# deck each physical control currently drives.
_DECK_BRUSHES = {
    "1": QBrush(QColor(35, 83, 132)),
    "2": QBrush(QColor(35, 102, 70)),
    "3": QBrush(QColor(126, 76, 30)),
    "4": QBrush(QColor(105, 58, 108)),
}
_DECK_FALLBACK_BRUSH = QBrush(QColor(70, 80, 98))


def _brush_for_decks(decks: set[str]) -> QBrush:
    if not decks:
        return _UNUSED_BRUSH
    if len(decks) > 1:
        return _MULTI_DECK_BRUSH
    (deck,) = decks
    return _DECK_BRUSHES.get(deck, _DECK_FALLBACK_BRUSH)


def _deck_sort_key(value: str) -> tuple[bool, int, str]:
    return (not value.isdigit(), int(value) if value.isdigit() else 0, value)


def _elide(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _button_brush(label: str) -> QBrush:
    lowered = label.casefold()
    if "play" in lowered:
        return QBrush(QColor(53, 166, 113))
    if "cue" in lowered:
        return QBrush(QColor(207, 72, 91))
    if "sync" in lowered:
        return QBrush(QColor(51, 173, 190))
    if "shift" in lowered:
        return QBrush(QColor(132, 87, 196))
    if "effect" in lowered or "fx" in lowered:
        return QBrush(QColor(181, 77, 176))
    return _CONTROL_BRUSH


def draw_control_glyph(
    scene: QGraphicsScene,
    metrics: LayoutMetrics,
    x: float,
    y: float,
    visual_kind: layout_mod.VisualKind,
    key: CellKey,
    value: int | None,
    flashed: bool,
    jog_angle_deg: float | None = None,
) -> None:
    """Draw a compact DJ control glyph at (x, y) inside a layout half, sized
    by the given LayoutMetrics. Shared by ControllerLayoutView (the
    read-only By Channel/Deck/Controller schematic, via _draw_control_shape)
    and the interactive controller emulator (gui/controller_emulator.py), so
    both draw identical glyphs from one place.

    ``jog_angle_deg`` (jog glyphs only): an absolute notch angle in degrees,
    accumulated from live relative jog-turn MIDI (see ControllerLayoutView.
    spin_jog / gui/jog.py). When given, it drives the notch instead of the
    bounded ``value``->pot-sweep mapping the emulator's drag gesture uses."""
    m = metrics
    left = x + 8
    top = y + 8
    resolved_value = _MIDI_DEFAULT if value is None else value
    if visual_kind in ("pad", "button"):
        size = m.pad_glyph if visual_kind == "pad" else m.button_glyph
        shape = QGraphicsRectItem(QRectF(left, top, size, size))
        if flashed:
            shape.setBrush(_FLASH_BRUSH)
        else:
            shape.setBrush(_PAD_BRUSH if visual_kind == "pad" else _button_brush(key[2]))
        shape.setPen(_CONTROL_PEN)
    elif visual_kind == "knob":
        d = m.knob_glyph
        ring = QGraphicsEllipseItem(QRectF(left, top, d, d))
        ring.setBrush(_KNOB_RING_BRUSH)
        ring.setPen(_CONTROL_PEN)
        ring.setData(_KEY_ROLE, key)
        ring.setData(_KIND_ROLE, visual_kind)
        scene.addItem(ring)
        inset = d / 8
        shape = QGraphicsEllipseItem(QRectF(left + inset, top + inset, d - 2 * inset, d - 2 * inset))
        shape.setBrush(_KNOB_BRUSH)
        shape.setPen(_CONTROL_PEN)
        center_x, center_y = left + d / 2, top + d / 2
        radius = d / 2 - d / 6
        angle = _knob_angle_rad(resolved_value)
        tip_x = center_x + radius * math.sin(angle)
        tip_y = center_y - radius * math.cos(angle)
        marker = QGraphicsLineItem(QLineF(center_x, center_y, tip_x, tip_y))
        marker.setPen(_KNOB_MARKER_PEN)
        marker.setZValue(1)  # above the dial ellipse (`shape`, added after this in scene order)
        marker.setData(_KEY_ROLE, key)
        marker.setData(_KIND_ROLE, visual_kind)
        scene.addItem(marker)
    elif visual_kind == "jog":
        d = m.jog_glyph
        shape = QGraphicsEllipseItem(QRectF(left, top, d, d))
        shape.setBrush(_CONTROL_BRUSH)
        shape.setPen(_CONTROL_PEN)
        # A position notch, reusing the knob's own angle math -- real jog
        # wheels spin continuously with no absolute position, but the
        # Controller Emulator's drag-to-spin gesture (phase 3) still needs
        # *some* visible feedback that a drag did something, so `value`
        # here is read as "wherever the wheel was last left", the same
        # convention set_value() already uses for knobs/faders elsewhere.
        center_x, center_y = left + d / 2, top + d / 2
        radius = d / 2 - d / 10
        angle = (
            math.radians(jog_angle_deg)
            if jog_angle_deg is not None
            else _knob_angle_rad(resolved_value)
        )
        tip_x = center_x + radius * math.sin(angle)
        tip_y = center_y - radius * math.cos(angle)
        notch = QGraphicsLineItem(QLineF(center_x, center_y, tip_x, tip_y))
        notch.setPen(_KNOB_MARKER_PEN)
        notch.setZValue(1)
        notch.setData(_KEY_ROLE, key)
        notch.setData(_KIND_ROLE, visual_kind)
        scene.addItem(notch)
    else:  # fader
        h = m.fader_glyph_h
        track = QGraphicsLineItem(QLineF(left + 16, top, left + 16, top + h))
        track.setPen(_FADER_PEN)
        track.setData(_KEY_ROLE, key)
        track.setData(_KIND_ROLE, visual_kind)
        scene.addItem(track)
        thumb_top = _fader_thumb_top(resolved_value, top, h, 8)
        shape = QGraphicsRectItem(QRectF(left + 7, thumb_top, 18, 8))
        shape.setBrush(_CONTROL_BRUSH)
        shape.setPen(_CONTROL_PEN)
    shape.setData(_KEY_ROLE, key)
    shape.setData(_KIND_ROLE, visual_kind)
    shape.setToolTip(f"{key[0]} — {key[1]} {key[2]}")
    scene.addItem(shape)


class _ClickableView(QGraphicsView):
    cellClicked = Signal(tuple)
    viewportResized = Signal()

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is not None:
            key = item.data(_KEY_ROLE)
            if key is not None:
                self.cellClicked.emit(key)
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # The outer ControllerLayoutView's own resizeEvent isn't a reliable
        # signal that *this* viewport's size actually changed -- a parent
        # QSplitter/layout pass can resize this QGraphicsView without the
        # outer widget's own size changing, and (seen in an offscreen
        # test/screenshot script) the reverse: the outer widget's resize()
        # can run before this viewport's layout has caught up. Fitting from
        # here instead reacts to the actual viewport size whenever it
        # settles, however that happened.
        self.viewportResized.emit()


class ControllerLayoutView(QWidget):
    """Schematic, clickable layout of a controller's physical buttons/pads.
    Each cell is split in two: the top half is this controller's own view
    (physical name, Serato function(s), deck(s)); the bottom half shows the
    same real MIDI trigger(s) as interpreted by the *other* controller, since
    a merged config doesn't record which physical device actually sent a
    given channel/note — DDJ-XP2 and XDJ-XZ can disagree on what a trigger
    means. An optional deck filter narrows both halves to a single deck."""

    cellActivated = Signal(tuple)  # CellKey

    def __init__(self, show_deck_filter: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Built-in catalog modules are discovered dynamically.  A frozen
        # application can briefly start with an empty registry if discovery
        # failed or a future plugin package is unavailable; the layout must
        # remain usable instead of crashing during window construction.
        controller_names = catalog.CONTROLLER_NAMES
        self._controller = controller_names[0] if controller_names else ""
        self._metrics = metrics_for(self._controller)
        self._usage: Usage = {}
        self._linked_cells: LinkedCells = {}
        self._selected_keys: set[CellKey] = set()
        self._selection_history: list[set[CellKey]] = []
        self._pad_center: QPointF | None = None
        # Discrete pad/button glyphs briefly flash white when a live MIDI hit
        # resolves to them (MainWindow._on_live_midi_event), independent of
        # the (persistent, until the next selection) red selection border --
        # this mimics a real pad lighting up on hit. Continuous controls
        # (knob/fader/jog) don't react yet; animating an actual value is a
        # separate follow-up (#13 part 2 continued).
        self._flash_keys: set[CellKey] = set()
        # Keys whose physical control is currently held down (live Note On,
        # cleared on Note Off -- MainWindow._on_live_midi_event). Unlike the
        # 220ms _flash_keys pulse this persists until the button is released,
        # drawn as a steady amber border/tint (_ACTIVE_BORDER_PEN, the same
        # look the Controller Emulator's phase-5 toggle state uses).
        self._active_keys: set[CellKey] = set()
        # Keys whose LED is currently lit according to *output-direction* MIDI
        # (Serato -> controller feedback, seen on the virtual monitor port).
        # Latched: set on a Note On with velocity > 0, cleared on Note Off /
        # velocity 0. Rendered with the same amber look as _active_keys and
        # OR'd with it, but kept in a separate set so an input-direction
        # release can't clear an LED the software is still driving (and vice
        # versa). See MainWindow._on_live_midi_event's direction == "out" path.
        self._led_keys: set[CellKey] = set()
        # Last known 7-bit MIDI value per key, from a live event -- drives the
        # knob marker angle and fader thumb position (#13 part 2 continued).
        # Unlike a flash, this is a level, not a pulse: it persists (like a
        # real knob staying wherever it was left) until the next event for
        # that key. Pads/buttons ignore it; no VU glyph exists yet.
        self._values: dict[CellKey, int] = {}
        # Accumulated jog-notch angle (degrees, 0..360) per jog CellKey, from
        # live *relative* jog-turn MIDI (gui/jog.py -> spin_jog). Separate
        # from _values: a jog turn has no absolute position, only a running
        # delta, so this integrates ticks rather than storing a level. When
        # present it overrides the emulator drag gesture's value->notch
        # mapping for that key (draw_control_glyph's jog_angle_deg).
        self._jog_angles: dict[CellKey, float] = {}
        # Set by set_zoom() (performance mode's manual "shrink everything"
        # toggle) -- resizeEvent's auto-fit-to-window (real-position mode)
        # is skipped whenever this isn't 1.0, so performance mode's own
        # tested zoom behavior is completely undisturbed by it.
        self._manual_zoom_factor = 1.0

        self._controller_tabs = QTabBar()
        self._controller_tabs.setStyleSheet(
            """
            QTabBar::tab {
                background: #182437;
                color: #aebed1;
                border: 1px solid #30445f;
                border-bottom: 2px solid #30445f;
                padding: 7px 14px;
                margin-right: 3px;
            }
            QTabBar::tab:selected {
                background: #d33c72;
                color: #ffffff;
                border-color: #f26395;
                border-bottom-color: #f26395;
            }
            QTabBar::tab:hover:!selected {
                background: #29415f;
                color: #ffffff;
            }
            """
        )
        self._controller_tabs.setExpanding(False)
        self._controller_tabs.setUsesScrollButtons(False)
        for name in catalog.CONTROLLER_NAMES:
            self._controller_tabs.addTab(name)

        self._controller_scroll = QScrollArea()
        self._controller_scroll.setWidgetResizable(False)
        self._controller_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._controller_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._controller_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._controller_scroll.setWidget(self._controller_tabs)
        self._resize_controller_selector()
        self._controller_tabs.currentChanged.connect(self._on_controller_tab_changed)

        self._deck_combo: QComboBox | None = None
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self._controller_scroll, 1)
        if show_deck_filter:
            deck_combo = QComboBox()
            deck_combo.setStyleSheet(
                """
                QComboBox {
                    background: #182437;
                    color: #e8eef7;
                    border: 1px solid #3d5875;
                    border-radius: 6px;
                    padding: 6px 10px;
                }
                QComboBox QAbstractItemView {
                    background: #0e1724;
                    color: #e8eef7;
                    selection-background-color: #d33c72;
                    selection-color: #ffffff;
                }
                """
            )
            deck_combo.addItem(_ALL_DECKS)
            deck_combo.currentTextChanged.connect(lambda _: self._rebuild())
            controls_layout.addWidget(deck_combo)
            self._deck_combo = deck_combo

        # Off by default (see gui/live_send.py's docstring for why): this
        # tab is browsed constantly while just auditing a mapping, so a
        # click must never send real MIDI unless the user has deliberately
        # switched this on.
        self._live_send = LiveSendControl()
        controls_layout.addWidget(self._live_send)

        # On by default: draw the real controller photo behind the
        # real-position markers (only has any effect for a controller with
        # gui/geometry.CONTROL_GEOMETRY -- the classic card grid ignores it).
        # The checkbox stays so it can be turned off. `setChecked(True)`
        # before wiring `toggled` keeps the state consistent without an
        # extra _rebuild() -- the one at the end of __init__ renders it.
        self._show_reference_photo = True
        self._photo_checkbox = QCheckBox("Controller photo")
        self._photo_checkbox.setToolTip(
            "Draw the real controller photo behind the real-position markers."
        )
        self._photo_checkbox.setChecked(True)
        self._photo_checkbox.toggled.connect(self._on_photo_toggled)
        controls_layout.addWidget(self._photo_checkbox)

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(_SCENE_BRUSH)
        self._view = _ClickableView(self._scene)
        self._view.setStyleSheet(
            "background: #0d1119; border: 1px solid #2b3b53; border-radius: 8px;"
        )
        self._view.cellClicked.connect(self.cellActivated)
        self._view.cellClicked.connect(self._on_cell_clicked_for_detail)
        self._view.cellClicked.connect(self._on_cell_clicked_for_live_send)
        self._view.viewportResized.connect(self._apply_fit)

        # Real-position mode (see _rebuild_real_position) draws compact,
        # unlabelled glyphs -- there's no room left in a marker for the name
        # or the "what does the other controller think this means" text the
        # classic card mode shows inline, so it moves here instead, updated
        # on click. Hidden/empty in classic card mode, which already shows
        # that information inline on every cell.
        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet(
            "QLabel { color: #c5d0df; padding: 4px 2px; }"
        )
        self._detail_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls_layout)
        layout.addWidget(self._view)
        layout.addWidget(self._detail_label)

        self._rebuild()

    def _on_controller_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        self._controller = self._controller_tabs.tabText(index)
        self._rebuild()

    def refresh_controllers(self) -> None:
        """Repopulates the controller tabs from the live registry — call after
        a controller is registered mid-session (see gui/controller_setup.py's
        "Apply now" action), since CONTROLLER_NAMES was only read once at
        __init__ time otherwise."""
        current = self._controller
        self._controller_tabs.blockSignals(True)
        while self._controller_tabs.count() > 0:
            self._controller_tabs.removeTab(0)
        restored = -1
        for name in catalog.CONTROLLER_NAMES:
            index = self._controller_tabs.addTab(name)
            if name == current:
                restored = index
        self._controller_tabs.setCurrentIndex(max(restored, 0))
        self._controller_tabs.blockSignals(False)
        self._resize_controller_selector()
        current_index = self._controller_tabs.currentIndex()
        self._controller = self._controller_tabs.tabText(current_index)
        self._rebuild()

    def _resize_controller_selector(self) -> None:
        """Keep the tab strip wide while letting its container scroll.

        The tab bar is the scroll area's content, not a constraint on the
        layout view itself. Keeping its minimum width on the tab bar made
        every parent splitter inherit the width of all controller tabs and
        prevented the main or floating window from being reduced.
        """
        self._controller_tabs.adjustSize()
        self._controller_tabs.setMinimumWidth(0)
        self._controller_scroll.setFixedHeight(self._controller_tabs.sizeHint().height() + 2)

    def set_controller(self, name: str) -> bool:
        """Selects a controller tab by name; returns False if unknown."""
        for index in range(self._controller_tabs.count()):
            if self._controller_tabs.tabText(index) == name:
                self._controller_tabs.setCurrentIndex(index)
                return True
        return False

    def set_usage(self, usage: Usage, linked_cells: LinkedCells | None = None) -> None:
        """usage maps a layout cell to {deck_id: {Serato function tags mapped
        on that deck}}. linked_cells maps a cell to the other controller's
        cell(s) sharing the same real trigger, for the split-cell view."""
        self._usage = usage
        self._linked_cells = linked_cells or {}
        if self._deck_combo is not None:
            all_decks = sorted({d for per_deck in usage.values() for d in per_deck}, key=_deck_sort_key)
            current = self._deck_combo.currentText()
            self._deck_combo.blockSignals(True)
            self._deck_combo.clear()
            self._deck_combo.addItem(_ALL_DECKS)
            self._deck_combo.addItems([f"Deck {d}" for d in all_decks])
            restored = self._deck_combo.findText(current)
            self._deck_combo.setCurrentIndex(max(restored, 0))
            self._deck_combo.blockSignals(False)
        self._rebuild()

    def set_selected_keys(self, keys: set[CellKey]) -> None:
        """Highlights the cell(s) currently selected in a paired tree (or clicked
        here), so the same selection is visible across tree <-> layout."""
        if keys == self._selected_keys:
            return
        if self._selected_keys:
            self._selection_history.insert(0, set(self._selected_keys))
            self._selection_history = self._selection_history[:5]
        self._selected_keys = keys
        self._rebuild()

    def flash_key(self, key: CellKey) -> None:
        """Briefly highlight a pad/button glyph in response to a live MIDI hit."""
        self._flash_keys.add(key)
        self._rebuild()
        QTimer.singleShot(_FLASH_DURATION_MS, lambda k=key: self._clear_flash(k))

    def _clear_flash(self, key: CellKey) -> None:
        self._flash_keys.discard(key)
        self._rebuild()

    def set_value(self, key: CellKey, value: int) -> None:
        """Record a live 7-bit MIDI value for a knob/fader glyph."""
        if self._values.get(key) == value:
            return
        self._values[key] = value
        self._rebuild()

    def set_active(self, key: CellKey, active: bool) -> None:
        """Persistent "held down" highlight for a pad/button, from a live
        Note On (active=True) / Note Off (active=False) -- see the
        _active_keys comment. A no-op rebuild is skipped when the state
        doesn't actually change, same discipline as set_value()."""
        if (key in self._active_keys) == active:
            return
        if active:
            self._active_keys.add(key)
        else:
            self._active_keys.discard(key)
        self._rebuild()

    def set_led(self, key: CellKey, active: bool) -> None:
        """Latched LED highlight for a pad/button, driven by output-direction
        MIDI (Serato lighting the control up). Same amber look as set_active
        but a separate set -- see the _led_keys comment."""
        if (key in self._led_keys) == active:
            return
        if active:
            self._led_keys.add(key)
        else:
            self._led_keys.discard(key)
        self._rebuild()

    def spin_jog(self, key: CellKey, delta_ticks: int) -> None:
        """Turn a jog glyph's notch by ``delta_ticks`` relative MIDI ticks
        (signed: positive = forward/clockwise). Integrates into a running
        0..360 angle -- a jog wheel has no absolute position -- and is a
        no-op for a zero delta. See gui/jog.py for how a live jog CC becomes
        a (key, delta) pair."""
        if not delta_ticks:
            return
        current = self._jog_angles.get(key, 0.0)
        self._jog_angles[key] = (current + delta_ticks * _JOG_DEGREES_PER_TICK) % 360.0
        self._rebuild()

    def clear_selection_history(self) -> None:
        """Forget the faded selection trail while keeping the current cell."""
        self._selection_history.clear()

    def _on_photo_toggled(self, checked: bool) -> None:
        self._show_reference_photo = checked
        self._rebuild()

    def set_show_reference_photo(self, enabled: bool) -> None:
        """Toggle the real-photo backdrop from code (keeps the checkbox in
        sync so the UI still reflects the state)."""
        self._photo_checkbox.setChecked(enabled)

    def set_zoom(self, factor: float) -> None:
        """Scale the whole schematic uniformly (performance mode's larger glyphs)."""
        self._manual_zoom_factor = factor
        self._view.resetTransform()
        if factor != 1.0:
            self._view.scale(factor, factor)
        self._rebuild()

    def _on_cell_clicked_for_detail(self, key: CellKey) -> None:
        # No isVisible() guard: that reflects the whole window's visibility,
        # not just this label's own show()/hide() call (isVisible() is
        # False for a widget that's never been shown at all, e.g. in a
        # test, or briefly during construction) -- updating text on a
        # hidden label is harmless, so just always do it.
        if self._detail_label.isHidden():
            return
        self._detail_label.setText(self._detail_text_for(key))

    def _on_cell_clicked_for_live_send(self, key: CellKey) -> None:
        """No-ops unless the embedded LiveSendControl is switched on (default
        off) -- see gui/live_send.py's docstring. Never interferes with the
        existing cellActivated/cross-tab-navigation click behavior, which
        keeps firing exactly as before regardless of this toggle's state."""
        sent = self._live_send.resolve_and_send(self._controller, key)
        if sent is not None and not self._detail_label.isHidden():
            channel = sent.channels[0] if sent.channels else "?"
            current = self._detail_label.text()
            self._detail_label.setText(f"{current}\n[LIVE SENT: ch{channel} {sent.note_or_cc} {sent.data1}]")

    def _detail_text_for(self, key: CellKey) -> str:
        """The per-cell text real-position mode can't fit inline (name, this
        controller's deck(s)/function(s), and what the *other* controller
        thinks the same real trigger means) -- the classic card mode already
        shows all of this inline via _draw_half, this is its equivalent for
        the compact glyph mode."""
        deck_filter = self._selected_deck_filter()
        decks, tags = self._cell_decks_and_tags(key, deck_filter)
        deck_text = ", ".join(f"Deck {d}" for d in sorted(decks)) if decks else "not used"
        tag_text = ", ".join(sorted(tags)) if tags else "no function mapped"
        lines = [f"{key[1]} {key[2]} — {deck_text} — {tag_text}"]
        linked_keys = sorted(self._linked_cells.get(key, set()))
        if linked_keys:
            other_controller = linked_keys[0][0]
            other_labels = ", ".join(k[2] for k in linked_keys)
            other_decks: set[str] = set()
            other_tags: set[str] = set()
            for linked_key in linked_keys:
                d, t = self._cell_decks_and_tags(linked_key, deck_filter)
                other_decks |= d
                other_tags |= t
            other_deck_text = ", ".join(f"Deck {d}" for d in sorted(other_decks)) if other_decks else "not used"
            other_tag_text = ", ".join(sorted(other_tags)) if other_tags else "no function mapped"
            lines.append(f"{other_controller}: {other_labels} — {other_deck_text} — {other_tag_text}")
        return "\n".join(lines)

    def _selection_pen(self, key: CellKey) -> QPen:
        if key in self._selected_keys:
            return _SELECTED_PEN
        if any(key in previous for previous in self._selection_history):
            return _HISTORY_PEN
        return _BORDER_PEN

    def _selected_deck_filter(self) -> str | None:
        if self._deck_combo is None:
            return None
        text = self._deck_combo.currentText()
        if text == _ALL_DECKS or not text:
            return None
        return text.removeprefix("Deck ")

    def _cell_decks_and_tags(self, cell_key: CellKey, deck_filter: str | None) -> tuple[set[str], set[str]]:
        """`cell_key` may be a side-aware *presentation* key (a real-position
        marker's " (R)" suffix) even though `self._usage` (built by
        MainWindow._refresh_layout_usage) stays keyed by the merged
        schematic key throughout -- deliberately: the "By Controller" text
        tree (gui/controller_tree.py) and the classic card grid both read
        the *same* usage dict and have no per-side concept at all, so
        splitting it at the source would silently under-report their
        aggregate deck/tag counts. Side-awareness lives here instead: look
        up the merged key, then narrow the per-deck dict down to the
        requested physical side's deck_ids for any section that's actually
        split (layout_mod.is_side_split_section) -- a plain key for a
        non-split section is returned unfiltered, exactly as before."""
        controller_name, section, label = cell_key
        right_side = label.endswith(layout_mod._RIGHT_GRID_SUFFIX)
        base_label = label.removesuffix(layout_mod._RIGHT_GRID_SUFFIX) if right_side else label
        per_deck = self._usage.get((controller_name, section, base_label), {})
        if layout_mod.is_side_split_section(controller_name, section):
            right_deck_ids = layout_mod.right_side_usage_deck_ids(controller_name)
            if right_deck_ids is not None:
                per_deck = {
                    deck_id: tags for deck_id, tags in per_deck.items() if (deck_id in right_deck_ids) == right_side
                }
        if deck_filter is not None:
            if deck_filter not in per_deck:
                return set(), set()
            return {deck_filter}, set(per_deck[deck_filter])
        decks = set(per_deck.keys())
        tags: set[str] = set()
        for deck_tags in per_deck.values():
            tags |= deck_tags
        return decks, tags

    def _draw_half(
        self,
        x: float,
        y: float,
        key: CellKey,
        header: str,
        decks: set[str],
        tags: set[str],
        small_font: QFont,
        clickable_key: CellKey,
        visual_kind: layout_mod.VisualKind = "button",
    ) -> None:
        m = self._metrics
        rect = QGraphicsRectItem(QRectF(0, 0, m.cell_w, m.half_h))
        rect.setPos(x, y)
        rect.setBrush(_brush_for_decks(decks) if (decks or tags) else _EMPTY_HALF_BRUSH)
        pen = self._selection_pen(clickable_key)
        is_amber = clickable_key in self._active_keys or clickable_key in self._led_keys
        if is_amber and clickable_key not in self._flash_keys:
            amber = QColor(_ACTIVE_BORDER_PEN.color())
            amber.setAlpha(_ACTIVE_FILL_ALPHA)
            rect.setBrush(QBrush(amber))
            if pen in (_BORDER_PEN, _HISTORY_PEN):
                pen = _ACTIVE_BORDER_PEN
        rect.setPen(pen)
        rect.setData(_KEY_ROLE, clickable_key)
        deck_text = ", ".join(f"Deck {d}" for d in sorted(decks)) if decks else "not used"
        tag_text = ", ".join(sorted(tags)) if tags else "no function mapped"
        rect.setToolTip(f"{key[0]} — {key[1]} {key[2]}\n{deck_text}\nMapped to: {tag_text}")
        self._scene.addItem(rect)
        self._draw_control_shape(x, y, visual_kind, clickable_key)

        text_x = x + m.label_x
        label = QGraphicsSimpleTextItem(_elide(header, 24))
        label.setPos(text_x, y + 2)
        label.setBrush(QColor("#f3f6fb"))
        label.setData(_KEY_ROLE, clickable_key)
        self._scene.addItem(label)

        if tags:
            tag_label = QGraphicsSimpleTextItem(_elide(", ".join(sorted(tags)), 26))
            tag_label.setFont(small_font)
            tag_label.setPos(text_x, y + 18)
            tag_label.setBrush(QColor("#c5d0df"))
            tag_label.setData(_KEY_ROLE, clickable_key)
            self._scene.addItem(tag_label)

        if decks:
            deck_label = QGraphicsSimpleTextItem(", ".join(f"D{d}" for d in sorted(decks)))
            deck_label.setFont(small_font)
            deck_label.setPos(text_x, y + m.half_h - 14)
            deck_label.setBrush(QColor("#91e8d2"))
            deck_label.setData(_KEY_ROLE, clickable_key)
            self._scene.addItem(deck_label)

    def _draw_control_shape(
        self, x: float, y: float, visual_kind: layout_mod.VisualKind, key: CellKey
    ) -> None:
        """Draw a compact DJ control glyph inside a layout half, sized by the
        current controller's LayoutMetrics."""
        draw_control_glyph(
            self._scene, self._metrics, x, y, visual_kind, key,
            self._values.get(key), key in self._flash_keys,
            self._jog_angles.get(key),
        )

    _ZONE_HEADER_H = 20

    def _draw_zone_frames(
        self, cells: list[layout_mod.LayoutCell], col_step: float, row_step: float
    ) -> None:
        """One rounded, labelled panel per section, sized to its cells' grid
        bounds. Purely decorative — no key data, never intercepts a click."""
        m = self._metrics
        bounds: dict[str, list[int]] = {}
        for cell in cells:
            b = bounds.get(cell.section)
            if b is None:
                bounds[cell.section] = [cell.col, cell.row, cell.col, cell.row]
            else:
                b[0], b[1] = min(b[0], cell.col), min(b[1], cell.row)
                b[2], b[3] = max(b[2], cell.col), max(b[3], cell.row)

        # Horizontal padding stays under half the inter-column gap so the
        # frames of two side-by-side zones only touch, never overlap; vertical
        # padding is generous because zones are anchored rows apart.
        hpad = max(1, (m.margin - 2) // 2)
        vpad = 9
        for section, (min_c, min_r, max_c, max_r) in bounds.items():
            x0 = min_c * col_step - hpad
            y0 = min_r * row_step - self._ZONE_HEADER_H
            w = (max_c - min_c + 1) * col_step - m.margin + 2 * hpad
            h = (max_r - min_r + 1) * row_step - m.margin + self._ZONE_HEADER_H + vpad
            frame = QGraphicsRectItem(QRectF(x0, y0, w, h))
            frame.setBrush(_ZONE_FILL_BRUSH)
            frame.setPen(_ZONE_BORDER_PEN)
            self._scene.addItem(frame)
            title = QGraphicsSimpleTextItem(section.replace("_", " ").upper())
            title.setFont(QFont("Helvetica Neue", 8, QFont.Weight.Bold))
            title.setBrush(_ZONE_TITLE_COLOR)
            title.setPos(x0 + 10, y0 + 4)
            self._scene.addItem(title)

    def _rebuild(self) -> None:
        self._scene.clear()
        self._pad_center = None
        self._scene.setBackgroundBrush(_SCENE_BRUSH)
        if not self._controller:
            self._detail_label.hide()
            message = QGraphicsSimpleTextItem(
                "No controller catalog is available. Check the bundled controller data."
            )
            message.setBrush(QColor("#c5d0df"))
            message.setPos(16, 16)
            self._scene.addItem(message)
            self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))
            return
        markers = real_position_markers(self._controller)
        if markers:
            self._detail_label.show()
            self._rebuild_real_position(markers)
            return
        self._detail_label.hide()
        self._metrics = metrics_for(self._controller)
        m = self._metrics
        col_step = m.cell_w + m.margin
        row_step = m.cell_h + m.margin
        cells = layout_mod.build_layout(self._controller)
        deck_filter = self._selected_deck_filter()
        small_font = QFont()
        small_font.setPointSize(7)

        # Frame each physical zone (PAD, DECK, EFFECT, MIXER, …) as a labelled
        # panel behind its cells, so the schematic reads as grouped hardware
        # areas instead of a flat field of boxes. Drawn first => cells on top.
        self._draw_zone_frames(cells, col_step, row_step)

        for cell in cells:
            x = cell.col * col_step
            y = cell.row * row_step

            decks, tags = self._cell_decks_and_tags(cell.key, deck_filter)
            self._draw_half(
                x,
                y,
                cell.key,
                cell.label,
                decks,
                tags,
                small_font,
                cell.key,
                cell.visual_kind,
            )

            linked_keys = sorted(self._linked_cells.get(cell.key, set()))
            if linked_keys:
                other_controller = linked_keys[0][0]
                other_labels = ", ".join(k[2] for k in linked_keys)
                other_decks: set[str] = set()
                other_tags: set[str] = set()
                for linked_key in linked_keys:
                    d, t = self._cell_decks_and_tags(linked_key, deck_filter)
                    other_decks |= d
                    other_tags |= t
                header = f"{other_controller}: {other_labels}"
                # Clicking the bottom half jumps using the *first* linked cell's key.
                linked_key = linked_keys[0]
                self._draw_half(
                    x,
                    y + m.half_h,
                    linked_key,
                    header,
                    other_decks,
                    other_tags,
                    small_font,
                    linked_key,
                    layout_mod.visual_kind_for(linked_key[1], linked_key[2]),
                )
            else:
                empty = QGraphicsRectItem(QRectF(0, 0, m.cell_w, m.half_h))
                empty.setPos(x, y + m.half_h)
                empty.setBrush(_EMPTY_HALF_BRUSH)
                empty.setPen(_BORDER_PEN)
                empty.setToolTip("No other controller shares this trigger in this config.")
                self._scene.addItem(empty)
                placeholder = QGraphicsSimpleTextItem("(other controller: n/a)")
                placeholder.setFont(small_font)
                placeholder.setPos(x + 4, y + m.half_h + 15)
                placeholder.setBrush(QColor("#78869b"))
                self._scene.addItem(placeholder)

            divider = QGraphicsLineItem(QLineF(x, y + m.half_h, x + m.cell_w, y + m.half_h))
            divider.setPen(_DIVIDER_PEN)
            self._scene.addItem(divider)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))
        pad_cells = [cell for cell in cells if cell.section == "PAD"]
        if pad_cells:
            self._pad_center = QPointF(
                sum(cell.col * col_step + m.cell_w / 2 for cell in pad_cells) / len(pad_cells),
                sum(cell.row * row_step + m.cell_h / 2 for cell in pad_cells) / len(pad_cells),
            )
        if not self._fit_card_view():
            self._center_on_pad_zone()

    def _rebuild_real_position(self, markers: list[RealPositionMarker]) -> None:
        """Real-position mode: one compact marker per real_position_markers()
        entry, placed at its true photographed coordinate -- the "By ..."
        tabs' equivalent of the Controller Images real-photo overlay (and,
        via that same shared function, identical to what the Controller
        Emulator draws for the same controller). With the "Controller photo"
        checkbox on, the real reference photo is drawn behind the markers
        (draw_reference_photo) so this reads exactly like Controller Images'
        "Show real layout"; off, the markers sit on the plain dark canvas.
        A marker whose key has no
        real catalog trigger (a continuous/display-only geometry entry,
        e.g. "FX LEVEL") still renders (decorative, harmless to click --
        MainWindow._on_layout_cell_activated already tolerates a key with no
        matching control). Diff-view content that doesn't fit inline a
        compact marker moves to self._detail_label (see
        _on_cell_clicked_for_detail), updated on click."""
        canvas_w, canvas_h = _reference_canvas_size(self._controller)
        photo_shown = self._show_reference_photo and draw_reference_photo(self._scene, self._controller)
        deck_filter = self._selected_deck_filter()
        for marker in markers:
            # A right-side marker ("Pad 3 (R)", "BEAT SYNC (R)", ...) shares
            # its *schematic* CellKey with its left counterpart by design
            # (see real_position_markers()'s docstring) -- using that same
            # key here would show/select/click both physical
            # grids/clusters together, exactly the "pressing a button on
            # one deck also activates the second deck" class of bug fixed
            # for the Controller Emulator (gui/controller_emulator.py,
            # gui/layout.py's resolve_side_aware_variant()). This tab has
            # cross-tab navigation to preserve (MainWindow.node_to_item and
            # the tree views), unlike the emulator, so the fix threads all
            # the way through: layout.find_controls_for_cell(),
            # layout.presentation_key_for_hit(), and this same presentation
            # key are all what MainWindow now uses to keep the two sides
            # independent end to end -- see main_window.py's
            # _on_layout_cell_activated/_select_deck_group/
            # _update_layout_selection/_on_live_midi_event.
            key = (
                (marker.key[0], marker.key[1], marker.label)
                if marker.label.endswith(layout_mod._RIGHT_GRID_SUFFIX)
                else marker.key
            )
            rect = marker.rect
            decks, tags = self._cell_decks_and_tags(key, deck_filter)

            # A background box the real geometry box's true size -- carries
            # the deck-usage color, the selection border, and the bigger
            # click target a small glyph alone wouldn't give. Drawn first so
            # the glyph on top of it stays visible.
            bg_item: QGraphicsRectItem | QGraphicsEllipseItem = (
                QGraphicsEllipseItem(rect) if marker.shape == "circle" else QGraphicsRectItem(rect)
            )
            if decks or tags:
                bg_item.setBrush(_brush_for_decks(decks))
            else:
                resting = QColor(marker.color)
                # Thinner wash over a photo so the real control stays legible
                # under the marker; the opaque-ish fill is only needed when
                # there's a blank canvas behind it.
                resting.setAlpha(30 if photo_shown else 90)
                bg_item.setBrush(QBrush(resting))
            pen = self._selection_pen(key)
            # Held-down state: steady amber fill + border, but a live
            # selection (red) still wins the border so cross-tab navigation
            # stays legible; the amber fill keeps "lit" visible underneath.
            if (
                key in self._active_keys or key in self._led_keys
            ) and key not in self._flash_keys:
                amber = QColor(_ACTIVE_BORDER_PEN.color())
                amber.setAlpha(_ACTIVE_FILL_ALPHA)
                bg_item.setBrush(QBrush(amber))
                if pen in (_BORDER_PEN, _HISTORY_PEN):
                    pen = _ACTIVE_BORDER_PEN
            bg_item.setPen(pen)
            bg_item.setData(_KEY_ROLE, key)
            deck_text = ", ".join(f"Deck {d}" for d in sorted(decks)) if decks else "not used"
            tag_text = ", ".join(sorted(tags)) if tags else "no function mapped"
            bg_item.setToolTip(f"{self._controller} — {marker.label}\n{deck_text}\nMapped to: {tag_text}")
            self._scene.addItem(bg_item)

            # The glyph itself -- reused verbatim from the classic card mode
            # (draw_control_glyph) so a knob still rotates and a fader thumb
            # still moves from a live MIDI value here too, not just in card
            # mode. Centered on the geometry box rather than draw_control_glyph's
            # own "+8, +8 from top-left" convention (built for a much bigger
            # uniform card, not a real, often-smaller photographed control).
            glyph_size = glyph_size_for(self._metrics, marker.visual_kind)
            glyph_x = rect.center().x() - glyph_size / 2 - 8
            glyph_y = rect.center().y() - glyph_size / 2 - 8
            draw_control_glyph(
                self._scene, self._metrics, glyph_x, glyph_y, marker.visual_kind, key,
                self._values.get(key), key in self._flash_keys,
                self._jog_angles.get(key),
            )
        self._scene.setSceneRect(0, 0, canvas_w, canvas_h)
        self._fit_real_position_view()

    def _fit_real_position_view(self) -> None:
        if self._manual_zoom_factor != 1.0:
            return
        self._view.resetTransform()
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _fit_card_view(self) -> bool:
        """Shrinks (never enlarges) the classic card schematic to fit the
        viewport when it's larger than available space, so a controller
        with many sections doesn't need scrolling to see in full -- the
        classic-mode half of "maximize space", alongside real-position
        mode's own auto-fit. Returns whether a shrink was applied; when it
        wasn't (content already fits, or performance mode's own manual zoom
        is active), the caller falls back to the existing
        center-on-pad-zone behavior, unchanged."""
        if self._manual_zoom_factor != 1.0:
            return False
        scene_rect = self._scene.itemsBoundingRect()
        viewport = self._view.viewport().size()
        if scene_rect.width() <= 0 or scene_rect.height() <= 0:
            return False
        if viewport.width() <= 0 or viewport.height() <= 0:
            return False
        scale = min(1.0, viewport.width() / scene_rect.width(), viewport.height() / scene_rect.height())
        self._view.resetTransform()
        if scale < 1.0:
            self._view.scale(scale, scale)
            return True
        return False

    def _center_on_pad_zone(self) -> None:
        if self._pad_center is None:
            return
        scene_rect = self._scene.sceneRect()
        half_view_width = max(320, self._view.viewport().width() / 2)
        if self._pad_center.x() - half_view_width < scene_rect.left():
            scene_rect.setLeft(self._pad_center.x() - half_view_width - 20)
            self._scene.setSceneRect(scene_rect)
        self._view.centerOn(self._pad_center)

    def _apply_fit(self) -> None:
        """Re-applies the current mode's "maximize space" fit against the
        *actual* current viewport size. Triggered both by this widget's own
        resizeEvent and by the inner QGraphicsView's viewportResized signal
        (see _ClickableView.resizeEvent) -- a parent splitter/layout pass
        can resize the inner viewport without this outer widget's own size
        changing, so relying on only one of the two misses real cases."""
        if geometry_mod.CONTROL_GEOMETRY.get(self._controller):
            self._fit_real_position_view()
        elif not self._fit_card_view():
            self._center_on_pad_zone()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_fit()


__all__ = [
    "ControllerLayoutView",
    "LayoutMetrics",
    "RealPositionMarker",
    "draw_control_glyph",
    "draw_reference_photo",
    "glyph_size_for",
    "metrics_for",
    "real_position_markers",
    "reference_pixmap",
]
