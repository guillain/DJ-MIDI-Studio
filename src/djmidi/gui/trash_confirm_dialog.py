"""The confirmation before duplicate copies go to the Trash (issue #208):
every copy with the copy kept instead and its folder, in a `ListDialog`
(a message box showed only 15 copies, cut, and outgrew the screen).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QDialog, QWidget

from djmidi.gui.list_dialog import ListDialog


class TrashConfirmDialog(ListDialog):
    def __init__(self, discards: Sequence[tuple[str, str]], parent: QWidget | None = None) -> None:
        rows = []
        for path, kept in discards:
            # The kept copy by name when it sits in the same folder, else in full.
            same_folder = Path(kept).parent == Path(path).parent
            cells = (Path(path).name, Path(kept).name if same_folder else kept, str(Path(path).parent))
            rows.append((cells, (path, kept, path)))
        super().__init__(
            QCoreApplication.translate("TrashConfirmDialog", "Move to Trash"),
            QCoreApplication.translate("TrashConfirmDialog", "Move {count} file(s) to the Trash?").format(
                count=len(discards)
            ),
            [
                QCoreApplication.translate("TrashConfirmDialog", "File"),
                QCoreApplication.translate("TrashConfirmDialog", "Copy kept instead"),
                QCoreApplication.translate("TrashConfirmDialog", "Folder"),
            ],
            rows,
            note=QCoreApplication.translate(
                "TrashConfirmDialog",
                "You can put them back from the Trash. They are flagged missing in this app's index.",
            ),
            accept_text=QCoreApplication.translate("TrashConfirmDialog", "Move to Trash"),
            parent=parent,
        )
        self.move_button = self.accept_button


def confirm_trash(parent: QWidget | None, discards: Sequence[tuple[str, str]]) -> bool:
    """Ask before moving `discards` ((copy, kept copy) pairs) to the Trash."""
    dialog = TrashConfirmDialog(discards, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted


__all__ = ["TrashConfirmDialog", "confirm_trash"]
