"""Utility widgets for `QScrollArea`-based clipping/overflow protection.

Several docks/tabs wrap part of their content in a `QScrollArea` so a too-
small window shows a scrollbar instead of squeezing that content below its
real minimum size (garbled overlapping text) or, for a dock, letting the
whole dock's geometry silently extend past the window's edge (clipping its
own title bar). See `controller_setup.py`'s `header_scroll` and
`live_monitor.py`'s `top_scroll` for the two shapes this comes up in.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QScrollArea


class AutoSizeScrollArea(QScrollArea):
    """A `widgetResizable` QScrollArea whose sizeHint() actually tracks its
    content, unlike the base class.

    QScrollArea.sizeHint() does not scale with a resizable widget's own
    sizeHint() -- it stays a small, roughly constant value regardless of how
    tall the content actually wants to be. That's invisible when the scroll
    area is the *sole* item in its parent layout (most uses of a scroll-
    wrapped region): a lone child in a QVBoxLayout gets the whole available
    rect regardless of its sizeHint, so the gap never shows. It becomes a
    real bug once the scroll area shares a layout with another stretch>0
    sibling (e.g. a results table below it that should get most of the
    space): the layout honors each item's sizeHint first and only
    distributes leftover space by stretch factor, so an under-reported
    sizeHint starves this widget of room it should get, even on a window
    plenty tall enough for everything to fit without scrolling. Found (and
    this class written) while fixing Controller Setup's "Draft" panel
    overlap: without it, a size that rendered complete before the fix
    regressed, cutting off content that should have stayed visible.
    """

    def sizeHint(self) -> QSize:
        widget = self.widget()
        if widget is not None:
            return widget.sizeHint()
        return super().sizeHint()


__all__ = ["AutoSizeScrollArea"]
