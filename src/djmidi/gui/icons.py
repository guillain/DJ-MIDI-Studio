"""The app's own line icons (UX review): drawn here with QPainter, in one
stroke width and one colour, so every button looks alike on every platform
(the system's standard icons differ between macOS, Windows and Linux, and
some are colourful). No image files, nothing third-party.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication

from djmidi.gui import theme

SIZE = 32  # drawn at 32 px, shown at 14-16 px: crisp on Retina screens

Draw = Callable[[QPainter], None]


def _line(p: QPainter, *points: tuple[float, float]) -> None:
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    p.drawPath(path)


def _arc_arrow(p: QPainter, clockwise: bool) -> None:
    rect = QRectF(7, 7, 18, 18)
    path = QPainterPath()
    path.arcMoveTo(rect, 60 if clockwise else 120)
    path.arcTo(rect, 60 if clockwise else 120, -280 if clockwise else 280)
    p.drawPath(path)
    end = path.currentPosition()
    tip = (end.x(), end.y())
    _line(p, (tip[0] - 5, tip[1] - 1), tip, (tip[0] - 1, tip[1] + 5)) if clockwise else _line(
        p, (tip[0] + 5, tip[1] - 1), tip, (tip[0] + 1, tip[1] + 5)
    )


_SHAPES: dict[str, Draw] = {
    "add": lambda p: (_line(p, (16, 7), (16, 25)), _line(p, (7, 16), (25, 16))),
    "auto": lambda p: _arc_arrow(p, True),
    "smart": lambda p: (
        _line(p, (16, 5), (18.5, 13.5), (27, 16), (18.5, 18.5), (16, 27), (13.5, 18.5), (5, 16), (13.5, 13.5), (16, 5))
    ),
    "import": lambda p: (_line(p, (16, 5), (16, 21)), _line(p, (9, 14), (16, 21), (23, 14)), _line(p, (7, 27), (25, 27))),
    "export": lambda p: (_line(p, (16, 21), (16, 5)), _line(p, (9, 12), (16, 5), (23, 12)), _line(p, (7, 27), (25, 27))),
    "compare": lambda p: (
        _line(p, (6, 11), (24, 11)),
        _line(p, (19, 6), (24, 11), (19, 16)),
        _line(p, (26, 21), (8, 21)),
        _line(p, (13, 16), (8, 21), (13, 26)),
    ),
    "edit": lambda p: (_line(p, (8, 24), (9, 19), (21, 7), (25, 11), (13, 23), (8, 24)), _line(p, (18, 10), (22, 14))),
    "save": lambda p: (
        _line(p, (7, 6), (22, 6), (26, 10), (26, 26), (6, 26), (6, 6), (7, 6)),
        _line(p, (11, 6), (11, 12), (20, 12), (20, 6)),
        p.drawRect(QRectF(10, 18, 12, 8)),
    ),
    "revert": lambda p: _arc_arrow(p, False),
    "undo": lambda p: (_line(p, (12, 9), (6, 15), (12, 21)), _line(p, (6, 15), (20, 15)), p.drawArc(QRectF(14, 15, 12, 12), 90 * 16, -180 * 16)),
    "redo": lambda p: (_line(p, (20, 9), (26, 15), (20, 21)), _line(p, (26, 15), (12, 15)), p.drawArc(QRectF(6, 15, 12, 12), 90 * 16, 180 * 16)),
    "confirm": lambda p: _line(p, (7, 17), (13, 23), (25, 9)),
    "files": lambda p: _line(p, (5, 9), (12, 9), (15, 12), (27, 12), (27, 25), (5, 25), (5, 9)),
    "clean": lambda p: (_line(p, (20, 5), (14, 17)), _line(p, (9, 16), (21, 21), (18, 27), (6, 27), (9, 16))),
    "delete": lambda p: (
        _line(p, (6, 9), (26, 9)),
        _line(p, (13, 9), (13, 6), (19, 6), (19, 9)),
        _line(p, (9, 9), (10, 27), (22, 27), (23, 9)),
        _line(p, (14, 13), (14, 23)),
        _line(p, (18, 13), (18, 23)),
    ),
    "play": lambda p: _line(p, (10, 6), (25, 16), (10, 26), (10, 6)),
    "stop": lambda p: p.drawRoundedRect(QRectF(8, 8, 16, 16), 2, 2),
    "image": lambda p: (
        p.drawRoundedRect(QRectF(5, 7, 22, 18), 2, 2),
        _line(p, (7, 23), (13, 16), (18, 21), (21, 18), (26, 23)),
        p.drawEllipse(QPointF(20, 12), 2, 2),
    ),
    "list": lambda p: (_line(p, (11, 9), (26, 9)), _line(p, (11, 16), (26, 16)), _line(p, (11, 23), (26, 23)),
                       _line(p, (6, 9), (6.5, 9)), _line(p, (6, 16), (6.5, 16)), _line(p, (6, 23), (6.5, 23))),
    "help": lambda p: (
        p.drawArc(QRectF(10, 5, 12, 12), 180 * 16, -270 * 16),
        _line(p, (16, 17), (16, 20)),
        _line(p, (16, 25), (16, 25.5)),
    ),
    "up": lambda p: (_line(p, (16, 26), (16, 7)), _line(p, (9, 14), (16, 7), (23, 14))),
    "down": lambda p: (_line(p, (16, 6), (16, 25)), _line(p, (9, 18), (16, 25), (23, 18))),
}
ROLES = tuple(_SHAPES)


# Icons drawn in a theme's icon colour, by QIcon.cacheKey() (shared by every
# copy, so also by the one a button holds): `recolour_buttons` redraws them in
# the new theme's colour, so no icon stays dark-theme cyan on a light theme.
_THEMED: dict[int, str] = {}


def _theme_icon_colours() -> set[str]:
    return {theme.colors(mode)["icon"].lower() for mode in ("light", "dark")}


def line_icon(role: str, colour: QColor | str) -> QIcon:
    """The role's icon, stroked in `colour` (an empty icon for an unknown role)."""
    icon = _draw(role, colour)
    if not icon.isNull() and QColor(colour).name().lower() in _theme_icon_colours():
        _THEMED[icon.cacheKey()] = role
    return icon


def recolour_buttons(*_args: object) -> int:
    """Redraw every themed line icon on a button in the current theme's icon
    colour (connected to ``theme.signals.themeChanged``). Returns how many."""
    app = QApplication.instance()
    if app is None:
        return 0
    colour = theme.colors()["icon"]
    count = 0
    for widget in QApplication.allWidgets():
        if not isinstance(widget, QAbstractButton):
            continue
        role = _THEMED.get(widget.icon().cacheKey())
        if role is not None:
            widget.setIcon(line_icon(role, colour))
            count += 1
    return count


theme.signals.themeChanged.connect(recolour_buttons)


def _draw(role: str, colour: QColor | str) -> QIcon:
    draw = _SHAPES.get(role)
    if draw is None:
        return QIcon()
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    draw(painter)
    painter.end()
    return QIcon(pixmap)


__all__ = ["ROLES", "line_icon", "recolour_buttons"]
