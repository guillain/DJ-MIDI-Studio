"""Utility helpers for `QSplitter` column-container management.

The By-Channel / By-Deck / By-Controller tabs all follow the same pattern:
a container holds a single QSplitter whose children are rebuilt on every
reload.  Extracting that pattern avoids triplicated code and lets each
rebuild be a one-liner at the call site.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QWidget


def replace_splitter(container: QWidget, old_splitter: QSplitter) -> QSplitter:
    """Swaps *old_splitter* for a fresh horizontal `QSplitter` inside *container*.

    The old splitter is detached from the layout and scheduled for deletion.
    Returns the new (empty) splitter so the caller can start adding widgets.
    """
    new_splitter = QSplitter(Qt.Orientation.Horizontal)
    layout = container.layout()
    layout.replaceWidget(old_splitter, new_splitter)
    old_splitter.deleteLater()
    return new_splitter


__all__ = ["replace_splitter"]

