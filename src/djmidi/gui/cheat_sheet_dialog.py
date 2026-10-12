"""The controller picker shown by File -> Export -> Cheat Sheet (PDF)
(issue #182): which controllers' pages to print.

A mapping file doesn't say which controller it was made for -- the same
pad triggers resolve on several Pioneer models (see gui/cheat_sheet.py's
module docstring) -- so the user ticks them, starting from a pre-selection
the main window guesses (connected controllers, the one Controller Images
shows)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.geometry import CONTROL_GEOMETRY


class CheatSheetExportDialog(QDialog):
    def __init__(
        self,
        candidates: list[tuple[str, int]],
        preselected: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Cheat Sheet (PDF)")
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Choose the controllers to print. Each one gets a page with its photo "
            "and the function on every mapped control (one page per pad bank in use); "
            "a controller without a measured layout gets a table instead."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self._list = QListWidget()
        for name, count in candidates:
            kind = "photo" if CONTROL_GEOMETRY.get(name) else "table"
            item = QListWidgetItem(f"{name} — {count} mapped trigger(s), {kind}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if name in preselected
                else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
        layout.addWidget(self._list)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export…")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._list.itemChanged.connect(self._update_ok)
        self._update_ok()
        self.resize(460, 360)

    def selected_controllers(self) -> list[str]:
        return [
            self._list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self._list.count())
            if self._list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def _update_ok(self, *_args) -> None:
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            bool(self.selected_controllers())
        )


__all__ = ["CheatSheetExportDialog"]
