"""Coloured Camelot badges for the track table (UX review).

Each Camelot number gets its own hue around the wheel (1 → 12 = 0° → 330°),
so neighbours on the wheel -- the harmonic mixes -- have neighbouring
colours; the minor keys (A) are deeper, the major keys (B) lighter. A
design choice of this app, not a DJ software's palette. Cells that aren't a
Camelot code (empty, an estimate in brackets…) paint as usual.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

_CODE = re.compile(r"^\s*(1[0-2]|[1-9])([AB])\s*$")


def camelot_colour(code: str) -> QColor | None:
    match = _CODE.match(code or "")
    if match is None:
        return None
    number, letter = int(match.group(1)), match.group(2)
    hue = (number - 1) * 30
    return QColor.fromHsv(hue, 170, 190) if letter == "A" else QColor.fromHsv(hue, 120, 235)


def text_colour_on(background: QColor) -> QColor:
    luminance = 0.299 * background.red() + 0.587 * background.green() + 0.114 * background.blue()
    return QColor("#111111") if luminance > 150 else QColor("#ffffff")


class CamelotBadgeDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        colour = camelot_colour(text)
        if colour is None:
            super().paint(painter, option, index)
            return
        # Selection / hover background first, then the badge on top.
        style_option = QStyleOptionViewItem(option)
        self.initStyleOption(style_option, index)
        style_option.text = ""
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, style_option, painter, widget)
        metrics = option.fontMetrics
        width = metrics.horizontalAdvance(text) + 14
        height = min(option.rect.height() - 4, metrics.height() + 4)
        rect = QRectF(option.rect.x() + 4, option.rect.center().y() - height / 2 + 1, width, height)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(rect, height / 2, height / 2)
        painter.setPen(text_colour_on(colour))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text.strip())
        painter.restore()


__all__ = ["CamelotBadgeDelegate", "camelot_colour", "text_colour_on"]
