"""Simple mode / Expert mode for widgets anywhere in the app.

A view marks its expert-only widgets with `expert_only(widget)` (or a
callback with `on_change`); `MainWindow.apply_expert_mode` calls `apply`,
which shows or hides them all. Simple mode is the default: testers found
the app good but too complicated (2026-11-20). Nothing is removed, Expert
mode brings it all back.

Only mark widgets whose visibility nothing else manages (a whole section,
a button that is always shown), or `apply(True)` would show something its
view meant to hide.
"""

from __future__ import annotations

from collections.abc import Callable

import shiboken6
from PySide6.QtWidgets import QWidget

_expert = False
_widgets: list[QWidget] = []
_callbacks: list[Callable[[bool], None]] = []


def is_expert() -> bool:
    return _expert


def expert_only(widget: QWidget) -> QWidget:
    """Shown only in Expert mode, from now on."""
    _prune()
    _widgets.append(widget)
    widget.setVisible(_expert)
    return widget


def on_change(callback: Callable[[bool], None]) -> None:
    """Called with the mode now and on every switch (keep the callback's
    owner alive as long as the app: views here live for the session)."""
    _callbacks.append(callback)
    callback(_expert)


def apply(expert: bool) -> None:
    global _expert
    _expert = expert
    _prune()
    for widget in _widgets:
        widget.setVisible(expert)
    for callback in list(_callbacks):
        try:
            callback(expert)
        except RuntimeError:  # its widget was deleted
            _callbacks.remove(callback)


def reset() -> None:
    """Tests: back to simple mode, nothing registered."""
    global _expert
    _expert = False
    _widgets.clear()
    _callbacks.clear()


def _prune() -> None:
    _widgets[:] = [widget for widget in _widgets if shiboken6.isValid(widget)]


__all__ = ["apply", "expert_only", "is_expert", "on_change", "reset"]
