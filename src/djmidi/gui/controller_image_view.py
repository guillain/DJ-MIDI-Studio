"""A static, zoomable/pannable viewer for the official Pioneer controller
diagrams (cropped from the MIDI Message List PDFs, see assets/controllers/
and README.md "Technical References"). Purely visual reference — no
interaction with the loaded config, unlike the other paired tree+layout tabs."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QCheckBox,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui.geometry import TRANSPORT_GEOMETRY

if getattr(sys, "frozen", False):
    _RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
else:
    _RESOURCE_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = _RESOURCE_ROOT / "assets" / "controllers"
DOCUMENTS_DIR = _RESOURCE_ROOT / "docs" / "controllers"
DOCUMENTS = {
    "DDJ-XP2": "ddj-xp2-midi-message-list-e1.pdf",
    "XDJ-XZ": "xdj-xz-midi-message-list-e3.pdf",
    "DDJ-1000": "ddj-1000-midi-message-list-e1.pdf",
    "DDJ-REV1": "ddj-rev1-midi-message-list-e1.pdf",
    "DDJ-FLX10": "ddj-flx10-midi-message-list-e1.pdf",
    "Numark Mixtrack Pro FX": "numark-mixtrack-pro-fx-user-guide-v1.2.pdf",
    "Hercules DJControl Inpulse 500": "hercules-djcontrol-inpulse-500-product-sheet-fr.pdf",
}
# Compatibility snapshot for callers that need to enumerate known image assets.
# New plugins provide this metadata through ControllerDefinition.reference_image.
IMAGES = {
    definition.name: definition.reference_image
    for definition in catalog.all_controller_definitions()
    if definition.reference_image
}


def image_for_controller(name: str) -> str | None:
    """Returns the reference image declared by the current controller plugin."""
    return catalog.get_definition(name).reference_image


def _resolve_image_path(reference_image: str | None) -> Path | None:
    """A controller's ``reference_image`` is either a bare filename bundled
    under ``assets/controllers/`` (the built-ins) or an absolute path to a
    user-supplied image attached in Controller Setup (issue #16). Accept both."""
    if not reference_image:
        return None
    candidate = Path(reference_image)
    return candidate if candidate.is_absolute() else ASSETS_DIR / reference_image


def documentation_for_controller(name: str) -> Path | None:
    """Return the bundled local document for a controller, when available."""
    filename = DOCUMENTS.get(name)
    path = DOCUMENTS_DIR / filename if filename else None
    return path if path is not None and path.exists() else None


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
        self._documentation_button = QPushButton("Open documentation")
        self._documentation_button.clicked.connect(self._open_documentation)
        self._transport_checkbox = QCheckBox("Show transport layer")
        self._transport_checkbox.toggled.connect(lambda _checked: self._draw_transport_overlay())

        controls = QHBoxLayout()
        controls.addWidget(self._combo)
        controls.addWidget(reset_button)
        controls.addWidget(self._documentation_button)
        controls.addWidget(self._transport_checkbox)
        controls.addStretch(1)

        self._scene = QGraphicsScene(self)
        self._view = _ZoomableView(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._overlay_items: list[QAbstractGraphicsShapeItem] = []

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
        documentation = documentation_for_controller(name)
        self._documentation_button.setEnabled(documentation is not None)
        self._documentation_button.setToolTip(
            str(documentation) if documentation is not None else "No local controller document bundled"
        )
        self._scene.clear()
        self._pixmap_item = None
        self._overlay_items = []
        self._view.resetTransform()
        path = _resolve_image_path(image_for_controller(name))
        pixmap = QPixmap(str(path)) if path is not None and path.exists() else QPixmap()
        if pixmap.isNull():
            # Keep the placeholder inside the graphics scene.  Embedding a
            # QWidget here (via addWidget) can leave a deleted QLabel proxy
            # behind when the scene is cleared during a controller switch.
            placeholder = QGraphicsTextItem(f"Image not found: {path if path is not None else name}")
            placeholder.setDefaultTextColor(Qt.GlobalColor.darkGray)
            self._scene.addItem(placeholder)
            self._scene.setSceneRect(self._scene.itemsBoundingRect())
            self._transport_checkbox.setEnabled(False)
            return
        item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item = item
        self._scene.addItem(item)
        self._scene.setSceneRect(item.boundingRect())
        self._view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)
        has_transport = name in TRANSPORT_GEOMETRY
        self._transport_checkbox.setEnabled(has_transport)
        self._transport_checkbox.setToolTip(
            ""
            if has_transport
            else "No transport geometry modeled yet for this controller (see gui/geometry.py)"
        )
        self._draw_transport_overlay()

    def _draw_transport_overlay(self) -> None:
        """Colored markers over the real photo at each transport control's
        true position (gui/geometry.TRANSPORT_GEOMETRY) -- start of the DJ
        layout visual fidelity chantier (issue #13). Decorative only, like
        the rest of this tab: no click handling, no binding to loaded config."""
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items = []
        if self._pixmap_item is None or not self._transport_checkbox.isChecked():
            return
        pixmap = self._pixmap_item.pixmap()
        image_w, image_h = pixmap.width(), pixmap.height()
        geometry = TRANSPORT_GEOMETRY.get(self._combo.currentText(), {})
        for label, geom in geometry.items():
            rect = QRectF(
                geom.x * image_w,
                geom.y * image_h,
                geom.w * image_w,
                geom.h * image_h,
            )
            fill = QColor(geom.color)
            fill.setAlpha(110)
            pen = QPen(QColor(geom.color))
            pen.setWidth(3)
            shape_item: QAbstractGraphicsShapeItem = (
                QGraphicsEllipseItem(rect) if geom.shape == "circle" else QGraphicsRectItem(rect)
            )
            shape_item.setBrush(QBrush(fill))
            shape_item.setPen(pen)
            shape_item.setToolTip(label)
            self._scene.addItem(shape_item)
            self._overlay_items.append(shape_item)

    def _open_documentation(self) -> None:
        documentation = documentation_for_controller(self._combo.currentText())
        if documentation is not None:
            QDesktopServices.openUrl(documentation.as_uri())


__all__ = [
    "ASSETS_DIR",
    "DOCUMENTS",
    "DOCUMENTS_DIR",
    "IMAGES",
    "ControllerImageView",
    "documentation_for_controller",
    "image_for_controller",
]
