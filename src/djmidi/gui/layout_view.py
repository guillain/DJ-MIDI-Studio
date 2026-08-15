from __future__ import annotations

from PySide6.QtCore import QLineF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QComboBox,
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

_CELL_W = 170
_HALF_H = 44
_CELL_H = _HALF_H * 2
_MARGIN = 6
_KEY_ROLE = 0
_ALL_DECKS = "All decks"

# cell key -> Serato deck number -> set of Serato function tags (mapping.tag)
# bound to that cell for that deck.
Usage = dict[CellKey, dict[str, set[str]]]
# cell key -> the other-controller cell key(s) that share at least one real
# (channel, event_type, control) trigger with it in the loaded config.
LinkedCells = dict[CellKey, set[CellKey]]

_UNUSED_BRUSH = QBrush(QColor(235, 235, 235))
_EMPTY_HALF_BRUSH = QBrush(QColor(246, 246, 246))
_MULTI_DECK_BRUSH = QBrush(QColor(120, 200, 190))
_BORDER_PEN = QPen(QColor(110, 110, 110))
_DIVIDER_PEN = QPen(QColor(170, 170, 170))
_SELECTED_PEN = QPen(QColor(220, 30, 30))
_SELECTED_PEN.setWidth(3)
_HISTORY_PEN = QPen(QColor(185, 150, 150))
_HISTORY_PEN.setWidth(2)

# One color per Serato deck number, so a glance at the layout shows which
# deck each physical control currently drives.
_DECK_BRUSHES = {
    "1": QBrush(QColor(140, 190, 255)),
    "2": QBrush(QColor(150, 220, 140)),
    "3": QBrush(QColor(255, 190, 120)),
    "4": QBrush(QColor(230, 150, 220)),
}
_DECK_FALLBACK_BRUSH = QBrush(QColor(190, 190, 190))


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
        self._controller = catalog.CONTROLLER_NAMES[0]
        self._usage: Usage = {}
        self._linked_cells: LinkedCells = {}
        self._selected_keys: set[CellKey] = set()
        self._selection_history: list[set[CellKey]] = []

        self._controller_tabs = QTabBar()
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
            deck_combo.addItem(_ALL_DECKS)
            deck_combo.currentTextChanged.connect(lambda _: self._rebuild())
            controls_layout.addWidget(deck_combo)
            self._deck_combo = deck_combo

        self._scene = QGraphicsScene(self)
        self._view = _ClickableView(self._scene)
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
    ) -> None:
        rect = QGraphicsRectItem(QRectF(0, 0, _CELL_W, _HALF_H))
        rect.setPos(x, y)
        rect.setBrush(_brush_for_decks(decks) if (decks or tags) else _EMPTY_HALF_BRUSH)
        rect.setPen(self._selection_pen(clickable_key))
        rect.setData(_KEY_ROLE, clickable_key)
        deck_text = ", ".join(f"Deck {d}" for d in sorted(decks)) if decks else "not used"
        tag_text = ", ".join(sorted(tags)) if tags else "no function mapped"
        rect.setToolTip(f"{key[0]} — {key[1]} {key[2]}\n{deck_text}\nMapped to: {tag_text}")
        self._scene.addItem(rect)

        label = QGraphicsSimpleTextItem(_elide(header, 24))
        label.setPos(x + 4, y + 2)
        label.setData(_KEY_ROLE, clickable_key)
        self._scene.addItem(label)

        if tags:
            tag_label = QGraphicsSimpleTextItem(_elide(", ".join(sorted(tags)), 26))
            tag_label.setFont(small_font)
            tag_label.setPos(x + 4, y + 18)
            tag_label.setData(_KEY_ROLE, clickable_key)
            self._scene.addItem(tag_label)

        if decks:
            deck_label = QGraphicsSimpleTextItem(", ".join(f"D{d}" for d in sorted(decks)))
            deck_label.setFont(small_font)
            deck_label.setPos(x + 4, y + _HALF_H - 14)
            deck_label.setData(_KEY_ROLE, clickable_key)
            self._scene.addItem(deck_label)

    def _rebuild(self) -> None:
        self._scene.clear()
        cells = layout_mod.build_layout(self._controller)
        deck_filter = self._selected_deck_filter()
        small_font = QFont()
        small_font.setPointSize(7)

        for cell in cells:
            x = cell.col * (_CELL_W + _MARGIN)
            y = cell.row * (_CELL_H + _MARGIN)

            decks, tags = self._cell_decks_and_tags(cell.key, deck_filter)
            self._draw_half(x, y, cell.key, cell.label, decks, tags, small_font, cell.key)

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
                self._draw_half(x, y + _HALF_H, linked_keys[0], header, other_decks, other_tags, small_font, linked_keys[0])
            else:
                empty = QGraphicsRectItem(QRectF(0, 0, _CELL_W, _HALF_H))
                empty.setPos(x, y + _HALF_H)
                empty.setBrush(_EMPTY_HALF_BRUSH)
                empty.setPen(_BORDER_PEN)
                empty.setToolTip("No other controller shares this trigger in this config.")
                self._scene.addItem(empty)
                placeholder = QGraphicsSimpleTextItem("(other controller: n/a)")
                placeholder.setFont(small_font)
                placeholder.setPos(x + 4, y + _HALF_H + 15)
                self._scene.addItem(placeholder)

            divider = QGraphicsLineItem(QLineF(x, y + _HALF_H, x + _CELL_W, y + _HALF_H))
            divider.setPen(_DIVIDER_PEN)
            self._scene.addItem(divider)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))


__all__ = ["ControllerLayoutView"]
