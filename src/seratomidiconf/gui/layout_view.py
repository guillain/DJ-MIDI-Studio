from __future__ import annotations

from PySide6.QtCore import QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QPen
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
_CELL_H = 36
_MARGIN = 6
_KEY_ROLE = 0

_UNUSED_BRUSH = QBrush(QColor(235, 235, 235))
_USED_BRUSH = QBrush(QColor(140, 190, 255))
_BORDER_PEN = QPen(QColor(110, 110, 110))


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
    Cells are colored to show which physical controls the loaded config
    actually uses; clicking one asks to jump to the matching tree entries."""

    cellActivated = Signal(tuple)  # CellKey

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = "DDJ-XP2"
        self._used_keys: set[CellKey] = set()

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

    def set_used_keys(self, used_keys: set[CellKey]) -> None:
        self._used_keys = used_keys
        self._rebuild()

    def _rebuild(self) -> None:
        self._scene.clear()
        cells = layout_mod.build_layout(self._controller)
        for cell in cells:
            x = cell.col * (_CELL_W + _MARGIN)
            y = cell.row * (_CELL_H + _MARGIN)

            rect = QGraphicsRectItem(QRectF(0, 0, _CELL_W, _CELL_H))
            rect.setPos(x, y)
            used = cell.key in self._used_keys
            rect.setBrush(_USED_BRUSH if used else _UNUSED_BRUSH)
            rect.setPen(_BORDER_PEN)
            rect.setData(_KEY_ROLE, cell.key)
            rect.setToolTip(f"{cell.section} — {cell.label} ({'used' if used else 'not used'} in this config)")
            self._scene.addItem(rect)

            text = QGraphicsSimpleTextItem(cell.label)
            text.setPos(x + 4, y + 4)
            text.setData(_KEY_ROLE, cell.key)
            self._scene.addItem(text)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))


__all__ = ["ControllerLayoutView"]
