"""Logs, at DEBUG, every mouse press / release / double-click on a list,
tree or table, with the widget's path and the item under the pointer.

Why: a native Qt crash during a click (an item view whose item was deleted
while it was being clicked) kills the process inside Qt's own
``mouseReleaseEvent``, after the Python handler has returned -- so neither
the macOS crash report nor faulthandler's Python stack names the widget.
Log writes are synchronous, so the last "click:" line before such a crash
does. Only item views are logged, and only when DEBUG is on.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractItemView, QWidget

_LOGGER = logging.getLogger(__name__)
_EVENTS = {
    QEvent.Type.MouseButtonPress: "press",
    QEvent.Type.MouseButtonRelease: "release",
    QEvent.Type.MouseButtonDblClick: "double-click",
}
_MAX_TEXT = 40
_PATH_DEPTH = 4


def widget_path(widget: QWidget) -> str:
    """``QListWidget#name < QGroupBox < ControllerSetupView`` -- object names
    where set, class names otherwise, innermost first."""
    parts: list[str] = []
    node: QWidget | None = widget
    while node is not None and len(parts) < _PATH_DEPTH:
        name = type(node).__name__
        if node.objectName() and not node.objectName().startswith("qt_"):
            name += f"#{node.objectName()}"
        parts.append(name)
        node = node.parentWidget()
    return " < ".join(parts)


def describe_click(view: QAbstractItemView, kind: str, position) -> str:
    index = view.indexAt(position)
    if index.isValid():
        text = str(index.data() or "").replace("\n", " ")[:_MAX_TEXT]
        where = f"row {index.row()} col {index.column()} {text!r}"
    else:
        where = "no item"
    return f"click: {kind} on {widget_path(view)} at {where}"


class ClickTrail(QObject):
    """Application-wide event filter; install with `install_click_trail`."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = _EVENTS.get(event.type())
        if kind is not None and _LOGGER.isEnabledFor(logging.DEBUG):
            view = watched.parent() if isinstance(watched, QWidget) else None
            if isinstance(view, QAbstractItemView) and watched is view.viewport():
                try:
                    _LOGGER.debug(describe_click(view, kind, event.position().toPoint()))
                except Exception:  # never let diagnostics break a click
                    _LOGGER.debug("click: %s (not describable)", kind, exc_info=True)
        return False


def install_click_trail(app) -> ClickTrail:
    """Installs the filter; the caller keeps the returned object alive (no
    Qt parent, so it also works with the stand-in app objects tests use)."""
    trail = ClickTrail()
    app.installEventFilter(trail)
    return trail


__all__ = ["ClickTrail", "describe_click", "install_click_trail", "widget_path"]
