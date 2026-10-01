"""Utility helpers for `QSplitter` column-container management.

The By-Channel / By-Deck / By-Controller tabs all follow the same pattern:
a container holds a single QSplitter whose children are rebuilt on every
reload.  Extracting that pattern avoids triplicated code and lets each
rebuild be a one-liner at the call site.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QSplitter, QWidget


def replace_splitter(container: QWidget, old_splitter: QSplitter) -> QSplitter:
    """Swaps *old_splitter* for a fresh horizontal `QSplitter` inside *container*.

    *container* is either a widget whose layout holds the splitter, or a
    `QScrollArea` whose widget it is (a column row that scrolls sideways
    once its columns no longer fit). The old splitter is detached and
    scheduled for deletion. Returns the new (empty) splitter so the caller
    can start adding widgets.
    """
    new_splitter = QSplitter(Qt.Orientation.Horizontal)
    if isinstance(container, QScrollArea):
        container.takeWidget()
        container.setWidget(new_splitter)
    else:
        container.layout().replaceWidget(old_splitter, new_splitter)
    old_splitter.deleteLater()
    return new_splitter


def scrollable_columns(splitter: QSplitter) -> QScrollArea:
    """A frameless, horizontally-scrolling holder for a row of columns: the
    columns stretch to fill the width until their minimum widths no longer
    fit, then the row scrolls instead of squeezing every column unreadable
    (a real 10-channel Traktor mapping truncated each row to "ch1 N...")."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(splitter)
    return area


__all__ = ["replace_splitter", "scrollable_columns"]

