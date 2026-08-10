from __future__ import annotations

from PySide6.QtCore import QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from seratomidiconf.gui import layout as layout_mod
from seratomidiconf.gui.layout import CellKey

_CELL_W = 130
_CELL_H = 46
_MARGIN = 6
_KEY_ROLE = 0

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
    control currently drives in the loaded config; clicking one jumps to a
    matching entry in the tree."""

    cellActivated = Signal(tuple)  # CellKey

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = "DDJ-XP2"
        self._deck_usage: dict[CellKey, set[str]] = {}

        self._combo = QComboBox()
        self._combo.addItems(["DDJ-XP2", "XDJ-XZ"])
        self._combo.currentTextChanged.connect(self._on_controller_changed)

        self._scene = QGraphicsScene(self)
        self._view = _ClickableView(self._scene)
        self._view.cellClicked.connect(self.cellActivated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combo)
        layout.addWidget(self._view)

        self._rebuild()

    def _on_controller_changed(self, text: str) -> None:
        self._controller = text
        self._rebuild()

    def set_deck_usage(self, deck_usage: dict[CellKey, set[str]]) -> None:
        """deck_usage maps a layout cell to the set of Serato deck numbers
        (as strings, e.g. "1"-"4") that a control bound to it targets."""
        self._deck_usage = deck_usage
        self._rebuild()

    def _rebuild(self) -> None:
        self._scene.clear()
        cells = layout_mod.build_layout(self._controller)
        small_font = QFont()
        small_font.setPointSize(7)
        for cell in cells:
            x = cell.col * (_CELL_W + _MARGIN)
            y = cell.row * (_CELL_H + _MARGIN)
            decks = self._deck_usage.get(cell.key, set())

            rect = QGraphicsRectItem(QRectF(0, 0, _CELL_W, _CELL_H))
            rect.setPos(x, y)
            rect.setBrush(_brush_for_decks(decks))
            rect.setPen(_BORDER_PEN)
            rect.setData(_KEY_ROLE, cell.key)
            deck_text = ", ".join(f"Deck {d}" for d in sorted(decks)) if decks else "not used"
            rect.setToolTip(f"{cell.section} — {cell.label} ({deck_text} in this config)")
            self._scene.addItem(rect)

            label = QGraphicsSimpleTextItem(cell.label)
            label.setPos(x + 4, y + 3)
            label.setData(_KEY_ROLE, cell.key)
            self._scene.addItem(label)

            if decks:
                deck_label = QGraphicsSimpleTextItem(", ".join(f"D{d}" for d in sorted(decks)))
                deck_label.setFont(small_font)
                deck_label.setPos(x + 4, y + _CELL_H - 16)
                deck_label.setData(_KEY_ROLE, cell.key)
                self._scene.addItem(deck_label)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))


__all__ = ["ControllerLayoutView"]
