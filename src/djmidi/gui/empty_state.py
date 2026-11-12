"""A friendly empty state over a list or table (UX review): a large glyph, a
title, a hint and, when there is an obvious next step, one button -- shown
while the view has no rows, instead of a blank area.

It sits on the view's viewport and follows its size; `refresh()` shows or
hides it from the model's row count (called on the model's row signals).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class EmptyState(QWidget):
    def __init__(
        self,
        view: QAbstractItemView,
        glyph: str,
        title: str,
        hint: str,
        action: tuple[str, Callable[[], None]] | None = None,
        is_empty: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(view.viewport())
        self.setProperty("emptyState", True)
        self._view = view
        self._is_empty = is_empty
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
            self.button = QPushButton(action[0])
            self.button.clicked.connect(action[1])
            box.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        box.addStretch(1)
        view.viewport().installEventFilter(self)
        model = view.model()
        if model is not None:
            for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset, model.layoutChanged):
                signal.connect(self.refresh)
        self.refresh()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(self._view.viewport().rect())
        return False

    def refresh(self, *_args) -> None:
        if self._is_empty is not None:
            empty = self._is_empty()
        else:
            model = self._view.model()
            empty = model is None or model.rowCount() == 0
        self.setGeometry(self._view.viewport().rect())
        self.setVisible(empty)


__all__ = ["EmptyState"]
