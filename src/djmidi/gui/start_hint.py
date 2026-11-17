"""A centred "nothing here yet" panel with one primary button (golden rule:
the next step is always visible). Unlike `empty_state.EmptyState`, which
overlays an item view, this is an ordinary widget to put where content
will appear later (a splitter before a mapping is open). It reuses the
empty-state object names, so the theme styles both alike."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class StartHint(QWidget):
    def __init__(
        self,
        glyph: str,
        title: str,
        hint: str,
        action: tuple[str, Callable[[], None]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("emptyState", True)
        box = QVBoxLayout(self)
        box.addStretch(1)
        for text, name in ((glyph, "emptyGlyph"), (title, "emptyTitle"), (hint, "emptyHint")):
            label = QLabel(text)
            label.setObjectName(name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            box.addWidget(label)
        self.title_label = self.findChild(QLabel, "emptyTitle")
        self.button: QPushButton | None = None
        if action is not None:
            text, callback = action
            self.button = QPushButton(text)
            self.button.setDefault(True)
            self.button.clicked.connect(callback)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(self.button)
            row.addStretch(1)
            box.addLayout(row)
        box.addStretch(2)


__all__ = ["StartHint"]
