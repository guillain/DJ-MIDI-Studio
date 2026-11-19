"""A segmented LED level meter, as on a mixer: green, then amber, then red, with a
peak that holds for a moment. A drop-in for a vertical QProgressBar (0-100)."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

SEGMENTS = 15
_AMBER_FROM = 10  # segment index (0 = bottom)
_RED_FROM = 13
PEAK_HOLD_S = 1.0


class LedMeter(QWidget):
    def __init__(self, parent: QWidget | None = None, *, segments: int = SEGMENTS) -> None:
        super().__init__(parent)
        self._segments = segments
        self._value = 0
        self._peak = 0
        self._peak_at = 0.0
        self.setFixedWidth(12)
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(12, 140)

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        now = time.monotonic()
        if value >= self._peak or now - self._peak_at > PEAK_HOLD_S:
            self._peak, self._peak_at = value, now
        if value != self._value:
            self._value = value
            self.update()

    def lit(self) -> int:
        """How many segments are lit."""
        return round(self._value * self._segments / 100)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gap = 2.0
        height = (self.height() - gap * (self._segments - 1)) / self._segments
        lit = self.lit()
        peak = min(self._segments - 1, round(self._peak * self._segments / 100) - 1)
        for index in range(self._segments):
            colour = QColor("#e5484d") if index >= _RED_FROM else QColor("#f5a524") if index >= _AMBER_FROM else QColor("#30a46c")
            if index >= lit and index != peak:
                colour.setAlpha(45)  # an unlit LED still shows
            y = self.height() - (index + 1) * height - index * gap
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawRoundedRect(QRectF(1, y, self.width() - 2, height), 1.5, 1.5)
        painter.end()


__all__ = ["LedMeter"]
