"""A controller's reference photo with one control framed (issue #451).

The guided check shows where the asked control is instead of only naming
it: a DJ needs no MIDI knowledge to find it. The frame uses the measured
markers of ``gui/geometry`` (built-ins and installed profiles alike), drawn
on the picture they were measured on; a control without a marker is simply
not framed (the prompt still names it).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from djmidi.gui.controller_image_view import (
    _load_pixmap,
    _resolve_image_path,
    image_for_controller,
)
from djmidi.gui.geometry import CONTROL_GEOMETRY, resolve_geometry_label

ASKED, GOOD, BAD = "#f2b705", "#2e9e4f", "#d03838"


class ControlPhoto(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.controller = ""
        self.pixmap: QPixmap | None = None
        self.marker = None  # a ControlGeometry, or None
        self.colour = QColor(ASKED)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 130)

    def set_controller(self, controller: str) -> None:
        if controller == self.controller:
            return
        self.controller = controller
        try:
            self.pixmap = _load_pixmap(_resolve_image_path(image_for_controller(controller)))
        except KeyError:
            self.pixmap = None
        self.marker = None
        self.update()

    def frame(self, names, colour: str = ASKED) -> bool:
        """Frames the first of ``names`` (catalog names) that has a marker;
        False when none has one."""
        markers = CONTROL_GEOMETRY.get(self.controller, {})
        self.marker = None
        for name in names:
            for candidate in (resolve_geometry_label(self.controller, name), name):
                if candidate and candidate in markers:
                    self.marker = markers[candidate]
                    break
            if self.marker is not None:
                break
        self.colour = QColor(colour)
        self.update()
        return self.marker is not None

    def recolour(self, colour: str) -> None:
        self.colour = QColor(colour)
        self.update()

    def clear(self) -> None:
        self.marker = None
        self.update()

    def paintEvent(self, _event) -> None:
        if self.pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scaled = self.pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        left = (self.width() - scaled.width()) / 2
        top = (self.height() - scaled.height()) / 2
        painter.drawPixmap(int(left), int(top), scaled)
        marker = self.marker
        if marker is not None:
            rect = QRectF(
                left + marker.x * scaled.width(),
                top + marker.y * scaled.height(),
                marker.w * scaled.width(),
                marker.h * scaled.height(),
            ).adjusted(-5, -5, 5, 5)
            painter.setPen(QPen(self.colour, 4))
            painter.drawRect(rect)
        painter.end()
