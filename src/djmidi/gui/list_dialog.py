"""A question or a report over a long list, shown in full.

A message box could only show the first 15 items of a list, cut long lines,
and grew taller than the screen with many of them (the Trash confirmation
listed 69 copies). This window shows **every** row in a table that scrolls
and resizes, with the question above and a note below, and keeps its
buttons on screen. As a confirmation, Cancel is the default button: nothing
happens unless the DJ clicks the action. As a report, it only closes.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)

# A row: the visible cells, or (cells, tooltips) to show full texts on hover.
Row = Sequence[str] | tuple[Sequence[str], Sequence[str]]

# The first columns are sized to their content up to this width; the last
# one takes the rest.
_MAX_COLUMN_WIDTH = 360


class ListDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        headers: Sequence[str],
        rows: Sequence[Row],
        note: str = "",
        accept_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        box = QVBoxLayout(self)
        question = QLabel(message)
        question.setStyleSheet("font-weight: 700; font-size: 15px;")
        question.setWordWrap(True)
        box.addWidget(question)

        self.table = QTreeWidget()
        usable_minimum(self.table, 320, 140)
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setUniformRowHeights(True)
        # Long paths keep their start and end visible.
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setHeaderLabels(list(headers))
        self.table.setHeaderHidden(len(headers) == 1)
        for row in rows:
            cells, tips = row if _has_tooltips(row) else (row, row)
            item = QTreeWidgetItem([str(cell) for cell in cells])
            for column, tip in enumerate(tips):
                item.setToolTip(column, str(tip))
            self.table.addTopLevelItem(item)
        header = self.table.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column in range(len(headers) - 1):
            self.table.resizeColumnToContents(column)
            header.resizeSection(column, min(header.sectionSize(column) + 12, _MAX_COLUMN_WIDTH))
        box.addWidget(self.table, 1)

        if note:
            note_label = QLabel(note)
            note_label.setWordWrap(True)
            box.addWidget(note_label)

        if accept_text is None:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            self.accept_button = None
        else:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
            self.accept_button = buttons.addButton(accept_text, QDialogButtonBox.ButtonRole.AcceptRole)
            cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
            cancel.setDefault(True)
            cancel.setFocus()
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

        fit_to_screen(self, 1200, 640)
        keep_wrapped_text_visible(self)


def _has_tooltips(row: Row) -> bool:
    return (
        isinstance(row, tuple)
        and len(row) == 2
        and not isinstance(row[0], str)
        and not isinstance(row[1], str)
    )


def confirm_list(
    parent: QWidget | None,
    title: str,
    message: str,
    headers: Sequence[str],
    rows: Sequence[Row],
    note: str = "",
    accept_text: str = "OK",
) -> bool:
    """Ask `message` over every row; True only when the action is clicked."""
    dialog = ListDialog(title, message, headers, rows, note, accept_text, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted


def show_list(
    parent: QWidget | None,
    title: str,
    message: str,
    headers: Sequence[str],
    rows: Sequence[Row],
    note: str = "",
) -> None:
    """Report `message` with every row (e.g. the files that failed)."""
    dialog = ListDialog(title, message, headers, rows, note, None, parent)
    dialog.exec()
    dialog.deleteLater()


__all__ = ["ListDialog", "confirm_list", "show_list"]
