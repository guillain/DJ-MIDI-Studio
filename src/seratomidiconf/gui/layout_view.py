from __future__ import annotations

from PySide6.QtCore import QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from seratomidiconf.gui import layout as layout_mod
from seratomidiconf.gui.layout import CellKey

_CELL_W = 150
_CELL_H = 58
_MARGIN = 6
_KEY_ROLE = 0
_ALL_DECKS = "All decks"

# cell key -> Serato deck number -> set of Serato function tags (mapping.tag)
# bound to that cell for that deck.
Usage = dict[CellKey, dict[str, set[str]]]

_UNUSED_BRUSH = QBrush(QColor(235, 235, 235))
_MULTI_DECK_BRUSH = QBrush(QColor(120, 200, 190))
_BORDER_PEN = QPen(QColor(110, 110, 110))

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
    Cells are colored per Serato deck to show which deck each physical
    control currently drives, and labeled with the Serato function(s) it is
    mapped to; clicking one jumps to a matching entry in the tree. An
    optional deck filter narrows both the coloring and the shown functions
    to a single deck, for a deck-centric view of the same data."""

    cellActivated = Signal(tuple)  # CellKey

    def __init__(self, show_deck_filter: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = "DDJ-XP2"
        self._usage: Usage = {}

        self._controller_combo = QComboBox()
        self._controller_combo.addItems(["DDJ-XP2", "XDJ-XZ"])
        self._controller_combo.currentTextChanged.connect(self._on_controller_changed)

        self._deck_combo: QComboBox | None = None
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self._controller_combo)
        if show_deck_filter:
            self._deck_combo = QComboBox()
            self._deck_combo.addItem(_ALL_DECKS)
            self._deck_combo.currentTextChanged.connect(lambda _: self._rebuild())
            controls_layout.addWidget(self._deck_combo)

        self._scene = QGraphicsScene(self)
        self._view = _ClickableView(self._scene)
        self._view.cellClicked.connect(self.cellActivated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls_layout)
        layout.addWidget(self._view)

        self._rebuild()

    def _on_controller_changed(self, text: str) -> None:
        self._controller = text
        self._rebuild()

    def set_usage(self, usage: Usage) -> None:
        """usage maps a layout cell to {deck_id: {Serato function tags mapped
        on that deck}}, so the layout can show both which deck(s) use a
        physical control and which Serato function it currently triggers."""
        self._usage = usage
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

            rect = QGraphicsRectItem(QRectF(0, 0, _CELL_W, _CELL_H))
            rect.setPos(x, y)
            rect.setBrush(_brush_for_decks(decks))
            rect.setPen(_BORDER_PEN)
            rect.setData(_KEY_ROLE, cell.key)
            deck_text = ", ".join(f"Deck {d}" for d in sorted(decks)) if decks else "not used"
            tag_text = ", ".join(sorted(tags)) if tags else "no function mapped"
            rect.setToolTip(f"{cell.section} — {cell.label}\n{deck_text}\nMapped to: {tag_text}")
            self._scene.addItem(rect)

            label = QGraphicsSimpleTextItem(cell.label)
            label.setPos(x + 4, y + 2)
            label.setData(_KEY_ROLE, cell.key)
            self._scene.addItem(label)

            if tags:
                tag_label = QGraphicsSimpleTextItem(_elide(", ".join(sorted(tags)), 22))
                tag_label.setFont(small_font)
                tag_label.setPos(x + 4, y + 20)
                tag_label.setData(_KEY_ROLE, cell.key)
                self._scene.addItem(tag_label)

            if decks:
                deck_label = QGraphicsSimpleTextItem(", ".join(f"D{d}" for d in sorted(decks)))
                deck_label.setFont(small_font)
                deck_label.setPos(x + 4, y + _CELL_H - 16)
                deck_label.setData(_KEY_ROLE, cell.key)
                self._scene.addItem(deck_label)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))


__all__ = ["ControllerLayoutView"]
