"""A static, zoomable/pannable viewer for the official Pioneer controller
diagrams (cropped from the MIDI Message List PDFs, see assets/controllers/
and README.md "Technical References"). Purely visual reference — no
interaction with the loaded config, unlike the other paired tree+layout tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog

ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets" / "controllers"
# One entry per controller with a reference image available; a controller with
# no entry here still shows up in the combo (driven by catalog.CONTROLLER_NAMES)
# and falls back to a "not found" placeholder — add an image whenever you have one.
IMAGES = {
    "DDJ-XP2": "ddj-xp2.png",
    "XDJ-XZ": "xdj-xz.png",
    "DDJ-1000": "ddj-1000.png",
}


class _ZoomableView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

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

    def refresh_controllers(self) -> None:
        """Repopulates the controller combo from the live registry — call after
        a controller is registered mid-session (see gui/controller_setup.py's
        "Apply now" action), since CONTROLLER_NAMES was only read once at
        __init__ time otherwise."""
        current = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(catalog.CONTROLLER_NAMES)
        restored = self._combo.findText(current)
        self._combo.setCurrentIndex(max(restored, 0))
        self._combo.blockSignals(False)
        self._load(self._combo.currentText())

    def set_controller(self, name: str) -> bool:
        """Selects a controller by name; returns False if not present."""
        index = self._combo.findText(name)
        if index < 0:
            return False
        self._combo.setCurrentIndex(index)
        return True

    def _load(self, name: str) -> None:
        self._scene.clear()
        self._pixmap_item = None
        self._view.resetTransform()
        image_name = IMAGES.get(name)
        path = ASSETS_DIR / image_name if image_name else None
        pixmap = QPixmap(str(path)) if path is not None and path.exists() else QPixmap()
        if pixmap.isNull():
            # Keep the placeholder inside the graphics scene.  Embedding a
            # QWidget here (via addWidget) can leave a deleted QLabel proxy
            # behind when the scene is cleared during a controller switch.
            placeholder = QGraphicsTextItem(f"Image not found: {path if path is not None else name}")
            placeholder.setDefaultTextColor(Qt.GlobalColor.darkGray)
            self._scene.addItem(placeholder)
            self._scene.setSceneRect(self._scene.itemsBoundingRect())
            return
        item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item = item
        self._scene.addItem(item)
        self._scene.setSceneRect(item.boundingRect())
        self._view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)


__all__ = ["ControllerImageView"]
