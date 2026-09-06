"""A zoomable/pannable viewer for the official Pioneer controller diagrams
(cropped from the MIDI Message List PDFs, see assets/controllers/ and
README.md "Technical References"). No *automatic* interaction with the
loaded config beyond a modeled control's marker (gui/geometry.CONTROL_GEOMETRY,
"Show real layout") flashing on a live MIDI hit, mirroring
ControllerLayoutView.flash_key on the schematic tabs (see
MainWindow._on_live_midi_event) -- but clicking a marker, while "Show real
layout" is on, can additionally send a real MIDI message when the embedded
LiveSendControl (gui/live_send.py) is switched on (default off); see that
module's docstring for why this and ControllerLayoutView share one
widget/default rather than each growing its own toggle."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
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
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui import layout as layout_mod
from djmidi.gui.geometry import CONTROL_GEOMETRY
from djmidi.gui.live_send import LiveSendControl

_FLASH_DURATION_MS = 220
_FLASH_COLOR = "#ffffff"
_LABEL_ROLE = 0
_CLICK_DRAG_TOLERANCE_PX = 4

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
    """Pannable (ScrollHandDrag) and zoomable (mouse wheel); also emits
    markerClicked(label) for a genuine click -- press and release close
    enough together to not be a pan gesture -- on a marker carrying
    _LABEL_ROLE data, so a caller can wire real-MIDI-send to it without
    this view knowing anything about MIDI itself."""

    markerClicked = Signal(str)

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._press_pos: QPointF | None = None

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        self._press_pos = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        press_pos, self._press_pos = self._press_pos, None
        if press_pos is None:
            return
        moved = (event.position() - press_pos).manhattanLength()
        if moved > _CLICK_DRAG_TOLERANCE_PX:
            return  # a pan gesture, not a click
        item = self.itemAt(event.position().toPoint())
        if item is None:
            return
        label = item.data(_LABEL_ROLE)
        if label is not None:
            self.markerClicked.emit(label)


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
        self._geometry_checkbox = QCheckBox("Show real layout")
        self._geometry_checkbox.toggled.connect(lambda _checked: self._draw_geometry_overlay())

        # Off by default (see gui/live_send.py's docstring): this tab is
        # looked at just to see a real photo, so a click must never send
        # real MIDI unless the user has deliberately switched this on --
        # and only makes sense while a clickable overlay is even showing.
        self._live_send = LiveSendControl()

        controls = QHBoxLayout()
        controls.addWidget(self._combo)
        controls.addWidget(reset_button)
        controls.addWidget(self._documentation_button)
        controls.addWidget(self._geometry_checkbox)
        controls.addWidget(self._live_send)
        controls.addStretch(1)

        self._scene = QGraphicsScene(self)
        self._view = _ZoomableView(self._scene)
        self._view.markerClicked.connect(self._on_marker_clicked)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._overlay_items: list[QAbstractGraphicsShapeItem] = []
        self._overlay_items_by_label: dict[str, QAbstractGraphicsShapeItem] = {}

        self._live_send_status = QLabel("")
        self._live_send_status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self._view)
        layout.addWidget(self._live_send_status)

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

    def current_controller_name(self) -> str:
        return self._combo.currentText()

    def _load(self, name: str) -> None:
        documentation = documentation_for_controller(name)
        self._documentation_button.setEnabled(documentation is not None)
        self._documentation_button.setToolTip(
            str(documentation) if documentation is not None else "No local controller document bundled"
        )
        self._scene.clear()
        self._pixmap_item = None
        self._overlay_items = []
        self._overlay_items_by_label = {}
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
            self._geometry_checkbox.setEnabled(False)
            return
        item = QGraphicsPixmapItem(pixmap)
        self._pixmap_item = item
        self._scene.addItem(item)
        self._scene.setSceneRect(item.boundingRect())
        self._view.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)
        has_geometry = name in CONTROL_GEOMETRY
        self._geometry_checkbox.setEnabled(has_geometry)
        self._geometry_checkbox.setToolTip(
            ""
            if has_geometry
            else "No control geometry modeled yet for this controller (see gui/geometry.py)"
        )
        self._draw_geometry_overlay()

    def _draw_geometry_overlay(self) -> None:
        """Colored markers over the real photo at each modeled control's
        true position (gui/geometry.CONTROL_GEOMETRY) -- the DJ layout visual
        fidelity chantier (issue #13). Decorative only, like the rest of this
        tab: no click handling, no binding to loaded config."""
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items = []
        self._overlay_items_by_label = {}
        if self._pixmap_item is None or not self._geometry_checkbox.isChecked():
            return
        pixmap = self._pixmap_item.pixmap()
        image_w, image_h = pixmap.width(), pixmap.height()
        geometry = CONTROL_GEOMETRY.get(self._combo.currentText(), {})
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
            shape_item.setData(_LABEL_ROLE, label)
            self._scene.addItem(shape_item)
            self._overlay_items.append(shape_item)
            self._overlay_items_by_label[label] = shape_item

    def flash_key(self, label: str) -> None:
        """Briefly (220ms) turns a modeled control's marker white on a live
        MIDI hit, mirroring ControllerLayoutView.flash_key on the schematic
        tabs. A no-op if that label isn't currently drawn -- the overlay is
        off, the control isn't modeled, or a different controller is shown."""
        item = self._overlay_items_by_label.get(label)
        if item is None:
            return
        flash_fill = QColor(_FLASH_COLOR)
        flash_fill.setAlpha(200)
        item.setBrush(QBrush(flash_fill))
        controller = self._combo.currentText()
        QTimer.singleShot(_FLASH_DURATION_MS, lambda: self._clear_flash(controller, label))

    def _clear_flash(self, controller: str, label: str) -> None:
        # The controller/overlay may have changed since the flash was
        # scheduled; only restore the marker if it's still the same one.
        if self._combo.currentText() != controller:
            return
        item = self._overlay_items_by_label.get(label)
        geom = CONTROL_GEOMETRY.get(controller, {}).get(label)
        if item is None or geom is None:
            return
        fill = QColor(geom.color)
        fill.setAlpha(110)
        item.setBrush(QBrush(fill))

    def _on_marker_clicked(self, label: str) -> None:
        """Resolves a clicked overlay marker's label back to a raw trigger
        the same way ControllerLayoutView's real-position mode does
        (layout.cell_key_for_geometry_label -> layout.reverse_lookup ->
        layout.pick_default_variant) and sends it via the shared
        LiveSendControl -- a no-op unless live send is on and a port is
        selected. This view has no other click behavior to interfere with
        (unlike ControllerLayoutView's cross-tab navigation), so there's
        nothing to preserve here beyond the existing flash-on-live-hit path."""
        controller = self._combo.currentText()
        key = layout_mod.cell_key_for_geometry_label(controller, label)
        if key is None:
            self._live_send_status.setText(f"{label}: no raw MIDI trigger known for this control.")
            return
        sent = self._live_send.resolve_and_send(controller, key)
        if sent is None:
            self._live_send_status.setText("")
            return
        channel = sent.channels[0] if sent.channels else "?"
        self._live_send_status.setText(f"LIVE SENT — {label}: ch{channel} {sent.note_or_cc} {sent.data1}")

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
