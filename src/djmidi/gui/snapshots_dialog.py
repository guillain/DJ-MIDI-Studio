"""File → Snapshots…: the named versions of the open mapping, with Compare
(the mapping diff), Restore and Delete."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.snapshots import Snapshot, delete_snapshot


class SnapshotsDialog(QDialog):
    compareRequested = Signal(object)  # Snapshot
    restoreRequested = Signal(object)  # Snapshot

    def __init__(
        self,
        mapping_name: str,
        load: Callable[[], list[Snapshot]],
        can_restore: bool = True,
        parent: QWidget | None = None,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Snapshots — {name}").format(name=mapping_name))
        self._load = load
        self._confirm = confirm or self._ask
        self.snapshots: list[Snapshot] = []

        intro = QLabel(
            self.tr(
                "Named versions of this mapping, newest first. Compare lists what changed since a snapshot; "
                "Restore brings its mappings back (Edit → Undo takes it back)."
            )
        )
        intro.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([self.tr("Name"), self.tr("Saved")])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemDoubleClicked.connect(
            lambda _item: self._emit(self.compareRequested)
        )
        usable_minimum(self.table, 320, 120)

        self.compare_button = QPushButton(self.tr("Compare"))
        self.compare_button.clicked.connect(lambda: self._emit(self.compareRequested))
        self.restore_button = QPushButton(self.tr("Restore"))
        self.restore_button.clicked.connect(lambda: self._emit(self.restoreRequested))
        self._can_restore = can_restore
        if not can_restore:
            self.restore_button.setToolTip(
                self.tr("Restoring works on Serato mappings; compare instead.")
            )
        self.delete_button = QPushButton(self.tr("Delete"))
        self.delete_button.clicked.connect(self.delete_selected)
        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(help_button(self, *help_texts.SNAPSHOTS))
        for button in (self.compare_button, self.restore_button, self.delete_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        self.empty_label = QLabel(
            self.tr(
                "No snapshot yet: File → Save Snapshot… keeps the mapping as it is now."
            )
        )
        self.empty_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty_label)
        layout.addLayout(buttons)
        self.refresh()
        fit_to_screen(self, 560, 380)
        keep_wrapped_text_visible(self)

    def refresh(self) -> None:
        self.snapshots = self._load()
        self.table.setRowCount(0)
        for row, snapshot in enumerate(self.snapshots):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(snapshot.name))
            try:
                saved = datetime.fromisoformat(snapshot.created).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except ValueError:
                saved = snapshot.created
            self.table.setItem(row, 1, QTableWidgetItem(saved))
        if self.snapshots:
            self.table.selectRow(0)
        self.empty_label.setVisible(not self.snapshots)
        self._update_buttons()

    def selected(self) -> Snapshot | None:
        row = self.table.currentRow()
        return self.snapshots[row] if 0 <= row < len(self.snapshots) else None

    def _update_buttons(self) -> None:
        chosen = self.selected() is not None
        self.compare_button.setEnabled(chosen)
        self.restore_button.setEnabled(chosen and self._can_restore)
        self.delete_button.setEnabled(chosen)

    def _emit(self, signal) -> None:
        snapshot = self.selected()
        if snapshot is not None:
            signal.emit(snapshot)

    def _ask(self, name: str) -> bool:
        answer = QMessageBox.question(
            self,
            self.tr("Delete snapshot"),
            self.tr("Delete the snapshot “{name}”?").format(name=name),
        )
        return answer == QMessageBox.StandardButton.Yes

    def delete_selected(self) -> bool:
        snapshot = self.selected()
        if snapshot is None or not self._confirm(snapshot.name):
            return False
        delete_snapshot(snapshot)
        self.refresh()
        return True


__all__ = ["SnapshotsDialog"]
