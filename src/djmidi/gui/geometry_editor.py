"""Place a profile's controls on a picture (issue #363).

A profile without built-in geometry -- one installed from the profile
library or made in Controller Setup -- only gets the card grid. This dialog
loads a picture of the controller and lets the user drag a box over each
control (or click for a default-size one), in the order of the layout's
cells. Save writes the picture and the boxes into the installed profile
file (``catalog.profile.save_profile_layout``), and
``geometry.sync_profile_geometry`` hands them to every real-position view,
exactly like a built-in's measured geometry.

Labels are the layout cells' (``layout.build_layout``): one marker per
physical control, a pad's modes and a button's SHIFT layer included, which
is what ``resolve_geometry_label`` and ``cell_key_for_geometry_label``
already resolve live hits and clicks through.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from djmidi import catalog
from djmidi.catalog.profile import save_profile_layout
from djmidi.gui import layout as layout_mod
from djmidi.gui.geometry import sync_profile_geometry
from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import GEOMETRY_EDITOR
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)

# A click (no drag) places a square this wide, as a fraction of the picture.
DEFAULT_MARKER_FRACTION = 0.04
_DRAG_THRESHOLD_PX = 6
_ROUND_KINDS = frozenset({"jog", "knob"})
_KIND_COLORS = {"pad": "#7d6fd9", "jog": "#586b82", "knob": "#586b82"}
_DEFAULT_COLOR = "#4a90d9"
_SELECTED_PEN = QPen(QColor("#ffc43c"), 3)
Marker = tuple[str, float, float, float, float, str, str]


def default_shape(kind: str) -> str:
    return "circle" if kind in _ROUND_KINDS else "rect"


def marker_from_drag(
    label: str, start: QPointF, end: QPointF, width: float, height: float, shape: str, color: str
) -> Marker:
    """A marker from a drag on a `width` x `height` picture, in fractions
    of it; a near-zero drag (a click) places a default-size square."""
    if abs(end.x() - start.x()) < _DRAG_THRESHOLD_PX and abs(end.y() - start.y()) < _DRAG_THRESHOLD_PX:
        side = DEFAULT_MARKER_FRACTION * width
        rect = QRectF(start.x() - side / 2, start.y() - side / 2, side, side)
    else:
        rect = QRectF(start, end).normalized()
    rect = rect.intersected(QRectF(0, 0, width, height))
    w = max(rect.width() / width, 0.001)
    h = max(rect.height() / height, 0.001)
    return (label, rect.x() / width, rect.y() / height, w, h, shape, color)


class _PlacementView(QGraphicsView):
    """Emits the press and release points of a drag, in scene coordinates."""

    dragged = Signal(QPointF, QPointF)

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._start: QPointF | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self.mapToScene(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._start is not None:
            self.dragged.emit(self._start, self.mapToScene(event.position().toPoint()))
            self._start = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.scene() is not None and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class GeometryEditorDialog(QDialog):
    saved = Signal(str)

    def __init__(
        self,
        controller: str,
        profile_path: str | Path,
        parent=None,
        choose_picture: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Place controls — {name}").format(name=controller))
        self._controller = controller
        self._profile_path = Path(profile_path)
        self._choose_picture = choose_picture
        definition = catalog.get_definition(controller)
        self._picture: Path | None = None
        self._pixmap: QPixmap | None = None
        if definition.reference_image and Path(definition.reference_image).is_file():
            self._picture = Path(definition.reference_image)
        self._cells = [cell for cell in layout_mod.build_layout(controller)]
        self._kinds = {cell.label: cell.visual_kind for cell in self._cells}
        self._markers: dict[str, Marker] = {marker[0]: marker for marker in definition.marker_geometry}

        intro = QLabel(
            self.tr(
                "Pick a control in the list, then drag a box over it on the picture (or click it for a "
                "standard-size box). The next control is selected for you. Save stores the picture and "
                "the boxes in the profile."
            )
        )
        intro.setWordWrap(True)

        self.control_list = QListWidget()
        self.control_list.currentRowChanged.connect(self._on_control_selected)
        usable_minimum(self.control_list, 200, 200)
        self.shape_combo = QComboBox()
        self.shape_combo.addItem(self.tr("Rectangle"), "rect")
        self.shape_combo.addItem(self.tr("Circle"), "circle")
        self.shape_combo.currentIndexChanged.connect(self._on_shape_changed)
        self.remove_button = QPushButton(self.tr("Remove box"))
        self.remove_button.clicked.connect(self._remove_current)
        side = QVBoxLayout()
        side.addWidget(self.control_list, 1)
        shape_row = QHBoxLayout()
        shape_row.addWidget(QLabel(self.tr("Shape")))
        shape_row.addWidget(self.shape_combo, 1)
        side.addLayout(shape_row)
        side.addWidget(self.remove_button)

        self._scene = QGraphicsScene(self)
        self.view = _PlacementView(self._scene)
        self.view.dragged.connect(self._on_dragged)
        usable_minimum(self.view, 360, 240)
        self.picture_button = QPushButton(self.tr("Choose picture…"))
        self.picture_button.clicked.connect(self._on_choose_picture)
        self.picture_label = QLabel("")
        self.picture_label.setWordWrap(True)
        center = QVBoxLayout()
        picture_row = QHBoxLayout()
        picture_row.addWidget(self.picture_button)
        picture_row.addWidget(self.picture_label, 1)
        center.addLayout(picture_row)
        center.addWidget(self.view, 1)

        body = QHBoxLayout()
        body.addLayout(side)
        body.addLayout(center, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *GEOMETRY_EDITOR))
        bottom.addWidget(self.status, 1)
        bottom.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(body, 1)
        layout.addLayout(bottom)

        self._fill_list()
        self._load_picture()
        fit_to_screen(self, 1000, 700)
        keep_wrapped_text_visible(self)

    # --- state ------------------------------------------------------------

    @property
    def markers(self) -> list[Marker]:
        """The placed markers, in the layout's cell order."""
        return [self._markers[cell.label] for cell in self._cells if cell.label in self._markers]

    def _current_label(self) -> str | None:
        row = self.control_list.currentRow()
        return self._cells[row].label if 0 <= row < len(self._cells) else None

    def _fill_list(self) -> None:
        current = self.control_list.currentRow()
        self.control_list.blockSignals(True)
        self.control_list.clear()
        for cell in self._cells:
            placed = cell.label in self._markers
            item = QListWidgetItem(f"✓ {cell.label}" if placed else cell.label)
            item.setToolTip(cell.section)
            self.control_list.addItem(item)
        self.control_list.blockSignals(False)
        self.control_list.setCurrentRow(max(current, 0) if self._cells else -1)
        self._update_status()

    def _update_status(self) -> None:
        self.status.setText(
            self.tr("{placed} of {total} controls placed.").format(placed=len(self._markers), total=len(self._cells))
        )
        has_picture = self._picture is not None
        self.view.setEnabled(has_picture)
        self.save_button.setEnabled(has_picture)
        self.remove_button.setEnabled(self._current_label() in self._markers)

    # --- picture ------------------------------------------------------------

    def _load_picture(self) -> None:
        self._scene.clear()
        self._pixmap = None
        if self._picture is not None:
            pixmap = QPixmap(str(self._picture))
            if not pixmap.isNull():
                self._pixmap = pixmap
                self._scene.addItem(QGraphicsPixmapItem(pixmap))
                self._scene.setSceneRect(QRectF(pixmap.rect()))
                self.view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            else:
                self._picture = None
        self.picture_label.setText(
            self._picture.name if self._picture is not None else self.tr("No picture yet: choose one first.")
        )
        self._draw_markers()
        self._update_status()

    def set_picture(self, path: str | Path) -> None:
        self._picture = Path(path)
        self._load_picture()

    def _on_choose_picture(self) -> None:
        if self._choose_picture is not None:
            path = self._choose_picture()
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, self.tr("Controller picture"), "", self.tr("Images (*.png *.jpg *.jpeg *.webp)")
            )
        if path:
            self.set_picture(path)

    # --- markers --------------------------------------------------------------

    def _draw_markers(self) -> None:
        for item in list(self._scene.items()):
            if not isinstance(item, QGraphicsPixmapItem):
                self._scene.removeItem(item)
        if self._pixmap is None:
            return
        width, height = self._pixmap.width(), self._pixmap.height()
        current = self._current_label()
        for label, x, y, w, h, shape, color in self._markers.values():
            rect = QRectF(x * width, y * height, w * width, h * height)
            fill = QColor(color)
            fill.setAlpha(110)
            pen = _SELECTED_PEN if label == current else QPen(QColor(color), 2)
            if shape == "circle":
                item = self._scene.addEllipse(rect, pen, QBrush(fill))
            else:
                item = self._scene.addRect(rect, pen, QBrush(fill))
            item.setToolTip(label)

    def _on_control_selected(self, _row: int) -> None:
        label = self._current_label()
        if label is not None:
            marker = self._markers.get(label)
            shape = marker[5] if marker else default_shape(self._kinds.get(label, ""))
            self.shape_combo.blockSignals(True)
            self.shape_combo.setCurrentIndex(max(self.shape_combo.findData(shape), 0))
            self.shape_combo.blockSignals(False)
        self._draw_markers()
        self._update_status()

    def _on_shape_changed(self, _index: int) -> None:
        label = self._current_label()
        if label in self._markers:
            marker = self._markers[label]
            self._markers[label] = (*marker[:5], self.shape_combo.currentData(), marker[6])
            self._draw_markers()

    def place(self, label: str, start: QPointF, end: QPointF) -> Marker | None:
        """Places `label`'s box from a drag (scene coordinates)."""
        if self._pixmap is None:
            return None
        kind = self._kinds.get(label, "")
        shape = self.shape_combo.currentData() if label == self._current_label() else default_shape(kind)
        marker = marker_from_drag(
            label, start, end, self._pixmap.width(), self._pixmap.height(), shape, _KIND_COLORS.get(kind, _DEFAULT_COLOR)
        )
        self._markers[label] = marker
        return marker

    def _on_dragged(self, start: QPointF, end: QPointF) -> None:
        label = self._current_label()
        if label is None or self.place(label, start, end) is None:
            return
        row = self.control_list.currentRow()
        following = [index for index in range(row + 1, len(self._cells)) if self._cells[index].label not in self._markers]
        self._fill_list()
        if following:
            self.control_list.setCurrentRow(following[0])
        else:
            self.control_list.setCurrentRow(row)
        self._draw_markers()

    def _remove_current(self) -> None:
        label = self._current_label()
        if label in self._markers:
            del self._markers[label]
            self._fill_list()
            self._draw_markers()

    # --- save -----------------------------------------------------------------

    def save(self) -> bool:
        """Stores the picture (copied next to the profile when it lives
        elsewhere) and the markers in the profile; True when saved."""
        if self._picture is None:
            return False
        folder = self._profile_path.parent
        picture = self._picture
        if picture.parent.resolve() != folder.resolve():
            copied = folder / f"{self._profile_path.stem}-picture{picture.suffix.lower()}"
            shutil.copyfile(picture, copied)
            picture = copied
        try:
            save_profile_layout(self._profile_path, str(picture), self.markers)
        except (OSError, ValueError, TypeError) as exc:
            self.status.setText(str(exc))
            return False
        sync_profile_geometry()
        self.saved.emit(self._controller)
        self.accept()
        return True
