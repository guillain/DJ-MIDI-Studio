"""A static, zoomable/pannable viewer for the official Pioneer controller
diagrams (cropped from the MIDI Message List PDFs, see assets/controllers/
and README.md "Technical References"). Purely visual reference — no
interaction with the loaded config, unlike the other paired tree+layout tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seratomidiconf import catalog

ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets" / "controllers"
# One entry per controller with a reference image available; a controller with
# no entry here still shows up in the combo (driven by catalog.CONTROLLER_NAMES)
# and falls back to a "not found" placeholder — add an image whenever you have one.
IMAGES = {"DDJ-XP2": "ddj-xp2.png", "XDJ-XZ": "xdj-xz.png"}


class _ZoomableView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(self.renderHints())

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


class ControllerImageView(QWidget):
    """Combo to pick a controller, a zoomable/pannable image of its official
    diagram, and a button to reset the view back to fit-to-window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._combo = QComboBox()
        self._combo.addItems(catalog.CONTROLLER_NAMES)
        self._combo.currentTextChanged.connect(self._load)

        reset_button = QPushButton("Reset zoom")
        reset_button.clicked.connect(lambda: self._load(self._combo.currentText()))

        controls = QHBoxLayout()
        controls.addWidget(self._combo)
        controls.addWidget(reset_button)
        controls.addStretch(1)

        self._scene = QGraphicsScene(self)
        self._view = _ZoomableView(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self._view)

        self._load(self._combo.currentText())

    def _load(self, name: str) -> None:
        self._scene.clear()
        self._pixmap_item = None
        path = ASSETS_DIR / IMAGES.get(name, "")
        pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
        if pixmap.isNull():
            placeholder = QLabel(f"Image not found: {path}")
            self._scene.addWidget(placeholder)
            return
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self._view.resetTransform()
        self._view.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)


__all__ = ["ControllerImageView"]
