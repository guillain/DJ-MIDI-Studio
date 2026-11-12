"""Compact, grouped action buttons (UX review): a titled section per
category whose buttons flow onto as many lines as the width needs, all with
the same look -- an icon, the ``chip`` style of theme.py, a tooltip.

`FlowLayout` is Qt's flow layout example, trimmed: it reports a height for
its width, so a section wraps instead of widening the panel.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QLabel,
    QLayout,
    QLayoutItem,
    QStyle,
    QVBoxLayout,
    QWidget,
)

# Role -> the platform's standard icon, so every button of one kind looks alike.
ICONS = {
    "add": QStyle.StandardPixmap.SP_FileDialogNewFolder,
    "auto": QStyle.StandardPixmap.SP_BrowserReload,
    "smart": QStyle.StandardPixmap.SP_FileDialogContentsView,
    "import": QStyle.StandardPixmap.SP_ArrowDown,
    "export": QStyle.StandardPixmap.SP_ArrowUp,
    "compare": QStyle.StandardPixmap.SP_FileDialogDetailedView,
    "edit": QStyle.StandardPixmap.SP_FileDialogInfoView,
    "save": QStyle.StandardPixmap.SP_DialogSaveButton,
    "revert": QStyle.StandardPixmap.SP_DialogResetButton,
    "undo": QStyle.StandardPixmap.SP_ArrowBack,
    "redo": QStyle.StandardPixmap.SP_ArrowForward,
    "confirm": QStyle.StandardPixmap.SP_DialogApplyButton,
    "files": QStyle.StandardPixmap.SP_DirIcon,
    "clean": QStyle.StandardPixmap.SP_DialogDiscardButton,
    "delete": QStyle.StandardPixmap.SP_TrashIcon,
    "up": QStyle.StandardPixmap.SP_ArrowUp,
    "down": QStyle.StandardPixmap.SP_ArrowDown,
}


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line = area.x(), area.y(), 0
        for item in self._items:
            if item.widget() is not None and item.widget().isHidden():
                continue
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and line > 0:
                x, y, line = area.x(), y + line + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            line = max(line, hint.height())
        return y + line - rect.y() + margins.bottom()


def chip(button: QAbstractButton, role: str | None = None) -> QAbstractButton:
    """The shared compact look: the ``chip`` style and the role's icon."""
    button.setProperty("chip", True)
    if role in ICONS:
        button.setIcon(button.style().standardIcon(ICONS[role]))
        button.setIconSize(QSize(14, 14))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def action_section(title: str, buttons: Sequence[tuple[QAbstractButton, str | None]]) -> QWidget:
    """A small uppercase title over the section's buttons, flowing."""
    section = QWidget()
    section.setProperty("actionArea", True)
    box = QVBoxLayout(section)
    box.setContentsMargins(0, 6, 0, 2)
    box.setSpacing(4)
    label = QLabel(title.upper())
    label.setProperty("sectionTitle", True)
    box.addWidget(label)
    flow = FlowLayout()
    for button, role in buttons:
        flow.addWidget(chip(button, role))
    box.addLayout(flow)
    return section


__all__ = ["ICONS", "FlowLayout", "action_section", "chip"]
