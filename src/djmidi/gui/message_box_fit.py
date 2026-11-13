"""Long message boxes stay on screen (the Trash confirmation of the Music
library lists up to 15 copies with their paths: its Yes/No buttons ended up
below the screen).

A ``QMessageBox`` sizes itself to its whole text and cannot scroll. Rather
than touching each of the ~130 calls, an application event filter catches
every message box as it is shown: when its text is taller (or wider) than
fits the screen, the text label moves into a scroll area of a size that
does, so the icon and the buttons always stay visible. Short messages are
left exactly as they are.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QWidget,
)

# Share of the screen the text may take; the rest is for the title bar,
# the informative text and the buttons.
HEIGHT_SHARE = 0.55
WIDTH_SHARE = 0.7
_DONE = "djmidiFitted"


def _screen_size(widget: QWidget) -> tuple[int, int]:
    screen = widget.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return 1024, 768
    area = screen.availableGeometry()
    return area.width(), area.height()


def fit_message_box(box: QMessageBox) -> bool:
    """Put the text of `box` in a scroll area when it doesn't fit the screen.
    Returns True when it did."""
    if box.property(_DONE):
        return False
    label = box.findChild(QLabel, "qt_msgbox_label")
    layout = box.layout()
    if label is None or not isinstance(layout, QGridLayout):
        return False
    screen_w, screen_h = _screen_size(box)
    max_w, max_h = int(screen_w * WIDTH_SHARE), int(screen_h * HEIGHT_SHARE)
    width = min(max(label.sizeHint().width(), 300), max_w)
    height = label.heightForWidth(width) if label.wordWrap() else label.sizeHint().height()
    if height <= max_h and label.sizeHint().width() <= max_w:
        return False
    index = layout.indexOf(label)
    if index < 0:
        return False
    row, column, row_span, column_span = layout.getItemPosition(index)
    layout.removeWidget(label)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    scroll = QScrollArea(box)
    scroll.setObjectName("djmidiMessageScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(label)
    bar = scroll.verticalScrollBar().sizeHint().width()
    scroll.setFixedSize(width + bar + 4, min(height, max_h) + 4)
    layout.addWidget(scroll, row, column, row_span, column_span)
    box.setProperty(_DONE, True)
    _resize(box)
    # QMessageBox sizes itself again from its (now moved) label when shown
    # and on layout requests: size it from the layout once Qt is done.
    QTimer.singleShot(0, box, lambda: _resize(box))
    return True


def _resize(box: QMessageBox) -> None:
    layout = box.layout()
    if layout is not None:
        layout.activate()
        box.setFixedSize(layout.totalSizeHint())


class MessageBoxFitter(QObject):
    """Installed once on the application (``install``)."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QMessageBox):
            if event.type() == QEvent.Type.Show:
                fit_message_box(watched)
            elif event.type() == QEvent.Type.LayoutRequest and watched.property(_DONE):
                QTimer.singleShot(0, watched, lambda: _resize(watched))
        return False


_INSTALLED: list[MessageBoxFitter] = []  # kept alive for the app's lifetime


def install(app: QApplication) -> MessageBoxFitter:
    fitter = MessageBoxFitter(app if isinstance(app, QObject) else None)
    app.installEventFilter(fitter)
    _INSTALLED.append(fitter)
    return fitter


__all__ = ["MessageBoxFitter", "fit_message_box", "install"]
