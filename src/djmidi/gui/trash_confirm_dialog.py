"""The confirmation before duplicate copies go to the Trash (issue #208).

A message box could only show the first 15 copies, their paths cut, and grew
taller than the screen with 69 of them. This window lists **every** copy with
the copy that stays, in a table that scrolls and resizes, and keeps its
buttons on screen. Cancel is the default button: nothing moves unless the
DJ clicks "Move to Trash".
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

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


class TrashConfirmDialog(QDialog):
    def __init__(self, discards: Sequence[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Move to Trash"))
        box = QVBoxLayout(self)
        question = QLabel(self.tr("Move {count} file(s) to the Trash?").format(count=len(discards)))
        question.setStyleSheet("font-weight: 700; font-size: 15px;")
        question.setWordWrap(True)
        box.addWidget(question)

        self.table = QTreeWidget()
        usable_minimum(self.table, 320, 140)
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setUniformRowHeights(True)
        # Long folders keep their start and end visible.
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setHeaderLabels([self.tr("File"), self.tr("Copy kept instead"), self.tr("Folder")])
        for path, kept in discards:
            # The kept copy by name when it sits in the same folder, else in full.
            same_folder = Path(kept).parent == Path(path).parent
            item = QTreeWidgetItem([Path(path).name, Path(kept).name if same_folder else kept, str(Path(path).parent)])
            for column, tip in ((0, path), (1, kept), (2, path)):
                item.setToolTip(column, tip)
            self.table.addTopLevelItem(item)
        header = self.table.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column in (0, 1):
            self.table.resizeColumnToContents(column)
            header.resizeSection(column, min(header.sectionSize(column) + 12, 360))
        box.addWidget(self.table, 1)

        note = QLabel(
            self.tr("You can put them back from the Trash. They are flagged missing in this app's index.")
        )
        note.setWordWrap(True)
        box.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.move_button = buttons.addButton(self.tr("Move to Trash"), QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setDefault(True)
        cancel.setFocus()
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

        fit_to_screen(self, 1200, 640)
        keep_wrapped_text_visible(self)


def confirm_trash(parent: QWidget | None, discards: Sequence[tuple[str, str]]) -> bool:
    """Ask before moving `discards` ((copy, kept copy) pairs) to the Trash."""
    dialog = TrashConfirmDialog(discards, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted


__all__ = ["TrashConfirmDialog", "confirm_trash"]
