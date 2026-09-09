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

import math
import sys
from pathlib import Path

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QCheckBox,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
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
from djmidi.gui.jog import DEGREES_PER_TICK as _JOG_DEGREES_PER_TICK
from djmidi.gui.live_send import LiveSendControl

_FLASH_DURATION_MS = 220
_FLASH_COLOR = "#ffffff"
# Persistent "held down" tint, matching layout_view._ACTIVE_BORDER_PEN's
# amber (QColor(255, 196, 60)) -- distinct from the 220ms white press
# pulse. Driven by input-direction Note On/Off (MainWindow._on_live_midi_event):
# lit while the physical control is held, cleared on release.
_ACTIVE_COLOR = "#ffc43c"
_ACTIVE_FILL_ALPHA = 170
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


_MIDI_SUFFIX = "-midi"


def image_variants(reference_image: str | None) -> tuple[Path | None, Path | None]:
    """``(clean_path, annotated_path)`` for a controller's reference image,
    following the ``<slug>.png`` (clean device render) / ``<slug>-midi.png``
    (same view with the MIDI Message List's callouts overlaid) bundling
    convention. Either entry is ``None`` when that file isn't bundled.

    A user-supplied absolute path (a Controller Setup attachment, issue #16)
    has no annotated sibling by convention, so it comes back as
    ``(that path, None)``.

    Which of the two a controller's ``reference_image`` actually names is
    also which one ``gui/geometry.CONTROL_GEOMETRY`` was measured against --
    the "Show real layout" overlay only lines up on that one (see
    ``ControllerImageView._load``)."""
    if not reference_image:
        return None, None
    p = Path(reference_image)
    if p.is_absolute():
        return (p if p.exists() else None), None
    stem = p.stem.removesuffix(_MIDI_SUFFIX)
    clean = ASSETS_DIR / f"{stem}{p.suffix}"
    annotated = ASSETS_DIR / f"{stem}{_MIDI_SUFFIX}{p.suffix}"
    return (clean if clean.exists() else None), (annotated if annotated.exists() else None)


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

        # Off by default: show the clean device render; tick to swap in the
        # "<slug>-midi.png" variant that has the MIDI Message List's callouts
        # printed over it. Disabled (with a tooltip) when a controller only
        # bundles one of the two variants.
        self._midi_checkbox = QCheckBox("MIDI info")
        self._midi_checkbox.toggled.connect(self._on_midi_toggled)
        # None until the user ticks the box themselves; after that it pins
        # their choice across controller switches. While None, each _load()
        # defaults the box to whichever variant `reference_image` names (so
        # the geometry overlay -- measured against that one -- is available
        # out of the box).
        self._midi_override: bool | None = None

        # Off by default (see gui/live_send.py's docstring): this tab is
        # looked at just to see a real photo, so a click must never send
        # real MIDI unless the user has deliberately switched this on --
        # and only makes sense while a clickable overlay is even showing.
        self._live_send = LiveSendControl()

        controls = QHBoxLayout()
        controls.addWidget(self._combo)
        controls.addWidget(reset_button)
        controls.addWidget(self._documentation_button)
        controls.addWidget(self._midi_checkbox)
        controls.addWidget(self._geometry_checkbox)
        controls.addWidget(self._live_send)
        controls.addStretch(1)

        self._scene = QGraphicsScene(self)
        self._view = _ZoomableView(self._scene)
        self._view.markerClicked.connect(self._on_marker_clicked)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._overlay_items: list[QAbstractGraphicsShapeItem] = []
        self._overlay_items_by_label: dict[str, QAbstractGraphicsShapeItem] = {}
        # Labels whose physical control is currently held down (live Note On,
        # cleared on Note Off) -- drawn with a persistent amber tint.
        self._active_labels: set[str] = set()
        # Labels whose LED is lit per output-direction MIDI (Serato -> device
        # feedback on the virtual monitor port). Latched, same amber tint,
        # kept separate so an input-direction release can't clear it.
        self._led_labels: set[str] = set()
        # Accumulated jog-notch angle (degrees, 0..360) per jog geometry
        # label, from live relative jog-turn MIDI (gui/jog.py -> spin_jog).
        # Mirrors ControllerLayoutView._jog_angles; the schematic tabs and
        # the emulator already spin, this brings the decorative overlay in
        # line. _overlay_jog_notches holds the notch line item per label so
        # spin_jog can turn it in place without a full overlay redraw
        # (which would clobber an in-flight flash_key mutation).
        self._jog_angles: dict[str, float] = {}
        self._overlay_jog_notches: dict[str, QGraphicsLineItem] = {}

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

    def _on_midi_toggled(self, checked: bool) -> None:
        # A deliberate user choice -- pin it across controller switches from
        # here on (see self._midi_override).
        self._midi_override = checked
        self._load(self._combo.currentText())

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
        self._active_labels.clear()  # held-state is per-controller
        self._led_labels.clear()  # LED-state is per-controller
        self._jog_angles.clear()  # jog rotation is per-controller
        self._overlay_jog_notches = {}
        self._view.resetTransform()

        reference = image_for_controller(name)
        clean_path, annotated_path = image_variants(reference)
        canonical_path = _resolve_image_path(reference)
        both_variants = clean_path is not None and annotated_path is not None
        self._midi_checkbox.setEnabled(both_variants)
        self._midi_checkbox.setToolTip(
            "" if both_variants else "Only one image variant is bundled for this controller."
        )

        canonical_is_annotated = annotated_path is not None and canonical_path == annotated_path
        want_annotated = self._midi_override if self._midi_override is not None else canonical_is_annotated
        show_annotated = bool(want_annotated) and annotated_path is not None
        self._midi_checkbox.blockSignals(True)
        self._midi_checkbox.setChecked(show_annotated)
        self._midi_checkbox.blockSignals(False)
        path = annotated_path if show_annotated else (clean_path or annotated_path)

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

        # CONTROL_GEOMETRY's fractions were measured against whichever variant
        # `reference_image` names -- they only line up on that one, so the
        # overlay is offered only while it's the one on screen.
        on_canonical_image = (
            canonical_path is not None and path is not None and canonical_path == path
        )
        has_geometry = name in CONTROL_GEOMETRY
        self._geometry_checkbox.setEnabled(has_geometry and on_canonical_image)
        if not has_geometry:
            self._geometry_checkbox.setToolTip(
                "No control geometry modeled yet for this controller (see gui/geometry.py)"
            )
        elif not on_canonical_image:
            self._geometry_checkbox.setToolTip(
                f"The control overlay is only aligned to the {canonical_path.name} image."
            )
        else:
            self._geometry_checkbox.setToolTip("")
        self._draw_geometry_overlay()

    def _draw_geometry_overlay(self) -> None:
        """Colored markers over the real photo at each modeled control's
        true position (gui/geometry.CONTROL_GEOMETRY) -- the DJ layout visual
        fidelity chantier (issue #13). Decorative only, like the rest of this
        tab: no click handling, no binding to loaded config."""
        for item in (*self._overlay_items, *self._overlay_jog_notches.values()):
            self._scene.removeItem(item)
        self._overlay_items = []
        self._overlay_items_by_label = {}
        self._overlay_jog_notches = {}
        # isEnabled() gates out the "checked but the annotated variant is on
        # screen" case -- CONTROL_GEOMETRY only aligns to the canonical image.
        if (
            self._pixmap_item is None
            or not self._geometry_checkbox.isChecked()
            or not self._geometry_checkbox.isEnabled()
        ):
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
            if label in self._active_labels or label in self._led_labels:
                fill = QColor(_ACTIVE_COLOR)
                fill.setAlpha(_ACTIVE_FILL_ALPHA)
                pen = QPen(QColor(_ACTIVE_COLOR))
            else:
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

            # A jog marker gets a rotating notch line (like the schematic
            # layouts' jog glyph), turned by spin_jog from live relative
            # jog-turn MIDI. Kept as its own item so spin_jog can setLine()
            # it in place rather than redraw the whole overlay.
            if layout_mod.visual_kind_for("DISPLAY", label) == "jog":
                notch = QGraphicsLineItem(
                    self._jog_notch_line(rect, self._jog_angles.get(label, 0.0))
                )
                notch_pen = QPen(QColor(_FLASH_COLOR))
                notch_pen.setWidth(3)
                notch.setPen(notch_pen)
                notch.setZValue(shape_item.zValue() + 1)
                notch.setData(_LABEL_ROLE, label)
                self._scene.addItem(notch)
                # Tracked only in _overlay_jog_notches (not _overlay_items,
                # whose consumers assume every entry is a .rect() shape) --
                # the cleanup loop above sweeps this dict's values too.
                self._overlay_jog_notches[label] = notch

    @staticmethod
    def _jog_notch_line(rect: QRectF, angle_deg: float) -> QLineF:
        """A line from the marker centre to its rim at ``angle_deg`` (0 = up,
        clockwise), the jog-rotation indicator over the reference photo."""
        cx, cy = rect.center().x(), rect.center().y()
        radius = min(rect.width(), rect.height()) / 2
        rad = math.radians(angle_deg)
        return QLineF(cx, cy, cx + radius * math.sin(rad), cy - radius * math.cos(rad))

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
        # Fall back to the amber tint, not the resting colour, if the control
        # is still held or its LED still lit when the flash pulse expires.
        if label in self._active_labels or label in self._led_labels:
            fill = QColor(_ACTIVE_COLOR)
            fill.setAlpha(_ACTIVE_FILL_ALPHA)
        else:
            fill = QColor(geom.color)
            fill.setAlpha(110)
        item.setBrush(QBrush(fill))

    def _restyle_label(self, label: str) -> None:
        """Repaint one overlay marker to match its current amber/resting
        state (amber when held or LED-lit, resting colour otherwise)."""
        item = self._overlay_items_by_label.get(label)
        if item is None:
            return
        geom = CONTROL_GEOMETRY.get(self._combo.currentText(), {}).get(label)
        if label in self._active_labels or label in self._led_labels:
            fill = QColor(_ACTIVE_COLOR)
            fill.setAlpha(_ACTIVE_FILL_ALPHA)
            pen = QPen(QColor(_ACTIVE_COLOR))
        elif geom is not None:
            fill = QColor(geom.color)
            fill.setAlpha(110)
            pen = QPen(QColor(geom.color))
        else:
            return
        pen.setWidth(3)
        item.setBrush(QBrush(fill))
        item.setPen(pen)

    def set_active(self, label: str, active: bool) -> None:
        """Persistent "held down" highlight for a modeled control -- called
        by MainWindow._on_live_midi_event on a live Note On (active=True) /
        Note Off (active=False). A no-op if the state doesn't actually
        change or the label isn't currently drawn."""
        if (label in self._active_labels) == active:
            return
        if active:
            self._active_labels.add(label)
        else:
            self._active_labels.discard(label)
        self._restyle_label(label)

    def set_led(self, label: str, active: bool) -> None:
        """Latched LED highlight for a modeled control, driven by
        output-direction MIDI (Serato lighting the control up). Same amber
        look as set_active but a separate set -- see the _led_labels comment."""
        if (label in self._led_labels) == active:
            return
        if active:
            self._led_labels.add(label)
        else:
            self._led_labels.discard(label)
        self._restyle_label(label)

    def spin_jog(self, label: str, delta_ticks: int) -> None:
        """Turn a jog marker's notch by ``delta_ticks`` signed relative MIDI
        ticks, integrated into a running 0..360 angle -- the decorative
        overlay's version of ControllerLayoutView.spin_jog. No-op for a zero
        delta or a label with no notch currently drawn (overlay off, not a
        jog, or a different controller shown)."""
        if not delta_ticks:
            return
        angle = (
            self._jog_angles.get(label, 0.0) + delta_ticks * _JOG_DEGREES_PER_TICK
        ) % 360.0
        self._jog_angles[label] = angle
        notch = self._overlay_jog_notches.get(label)
        rect = self._geometry_rect(label)
        if notch is not None and rect is not None:
            notch.setLine(self._jog_notch_line(rect, angle))

    def _geometry_rect(self, label: str) -> QRectF | None:
        """The scene rect a CONTROL_GEOMETRY entry maps to over the current
        reference image, or None if nothing's drawn / the label is unknown."""
        if self._pixmap_item is None:
            return None
        geom = CONTROL_GEOMETRY.get(self._combo.currentText(), {}).get(label)
        if geom is None:
            return None
        pixmap = self._pixmap_item.pixmap()
        return QRectF(
            geom.x * pixmap.width(),
            geom.y * pixmap.height(),
            geom.w * pixmap.width(),
            geom.h * pixmap.height(),
        )

    def _on_marker_clicked(self, label: str) -> None:
        """Resolves a clicked overlay marker's label back to a raw trigger
        and sends it via the shared LiveSendControl -- a no-op unless live
        send is on and a port is selected. This view has no other click
        behavior to interfere with (unlike ControllerLayoutView's cross-tab
        navigation), so there's nothing to preserve here beyond the
        existing flash-on-live-hit path.

        Passes the *raw* label (e.g. "Pad 3 (R)"), not the merged key
        cell_key_for_geometry_label() would collapse it to, so
        LiveSendControl's layout.resolve_side_aware_variant() can tell a
        right-pad-grid marker's click apart from its left counterpart's --
        otherwise clicking the right grid here would silently resolve/send
        the left grid's deck (1/3) trigger instead of the right's (2/4)."""
        controller = self._combo.currentText()
        merged_key = layout_mod.cell_key_for_geometry_label(controller, label)
        if merged_key is None:
            self._live_send_status.setText(f"{label}: no raw MIDI trigger known for this control.")
            return
        key = (
            (merged_key[0], merged_key[1], label)
            if label.endswith(layout_mod._RIGHT_GRID_SUFFIX)
            else merged_key
        )
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
    "image_variants",
]
