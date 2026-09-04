from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QScrollArea,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui import layout as layout_mod
from djmidi.gui.layout import CellKey

_KEY_ROLE = 0
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
_FLASH_BRUSH = QBrush(QColor(255, 255, 255))
_FLASH_DURATION_MS = 220

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


class _ClickableView(QGraphicsView):
    cellClicked = Signal(tuple)

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is not None:
            key = item.data(_KEY_ROLE)
            if key is not None:
                self.cellClicked.emit(key)
        super().mousePressEvent(event)


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

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(_SCENE_BRUSH)
        self._view = _ClickableView(self._scene)
        self._view.setStyleSheet(
            "background: #0d1119; border: 1px solid #2b3b53; border-radius: 8px;"
        )
        self._view.cellClicked.connect(self.cellActivated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls_layout)
        layout.addWidget(self._view)

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

    def clear_selection_history(self) -> None:
        """Forget the faded selection trail while keeping the current cell."""
        self._selection_history.clear()
        self._rebuild()

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
        per_deck = self._usage.get(cell_key, {})
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
        rect.setPen(self._selection_pen(clickable_key))
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
        m = self._metrics
        left = x + 8
        top = y + 8
        if visual_kind in ("pad", "button"):
            size = m.pad_glyph if visual_kind == "pad" else m.button_glyph
            shape = QGraphicsRectItem(QRectF(left, top, size, size))
            if key in self._flash_keys:
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
            self._scene.addItem(ring)
            inset = d / 8
            shape = QGraphicsEllipseItem(QRectF(left + inset, top + inset, d - 2 * inset, d - 2 * inset))
            shape.setBrush(_KNOB_BRUSH)
            shape.setPen(_CONTROL_PEN)
            marker = QGraphicsLineItem(QLineF(left + d / 2, top + d / 2, left + d / 2, top + d / 6))
            marker.setPen(_CONTROL_PEN)
            marker.setData(_KEY_ROLE, key)
            self._scene.addItem(marker)
        elif visual_kind == "jog":
            d = m.jog_glyph
            shape = QGraphicsEllipseItem(QRectF(left, top, d, d))
            shape.setBrush(_CONTROL_BRUSH)
            shape.setPen(_CONTROL_PEN)
        else:  # fader
            h = m.fader_glyph_h
            track = QGraphicsLineItem(QLineF(left + 16, top, left + 16, top + h))
            track.setPen(_FADER_PEN)
            track.setData(_KEY_ROLE, key)
            self._scene.addItem(track)
            shape = QGraphicsRectItem(QRectF(left + 7, top + h / 2 - 4, 18, 8))
            shape.setBrush(_CONTROL_BRUSH)
            shape.setPen(_CONTROL_PEN)
        shape.setData(_KEY_ROLE, key)
        shape.setToolTip(f"{key[0]} — {key[1]} {key[2]}")
        self._scene.addItem(shape)

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
            message = QGraphicsSimpleTextItem(
                "No controller catalog is available. Check the bundled controller data."
            )
            message.setBrush(QColor("#c5d0df"))
            message.setPos(16, 16)
            self._scene.addItem(message)
            self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))
            return
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
            self._center_on_pad_zone()

    def _center_on_pad_zone(self) -> None:
        if self._pad_center is None:
            return
        scene_rect = self._scene.sceneRect()
        half_view_width = max(320, self._view.viewport().width() / 2)
        if self._pad_center.x() - half_view_width < scene_rect.left():
            scene_rect.setLeft(self._pad_center.x() - half_view_width - 20)
            self._scene.setSceneRect(scene_rect)
        self._view.centerOn(self._pad_center)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._center_on_pad_zone()


__all__ = ["ControllerLayoutView"]
