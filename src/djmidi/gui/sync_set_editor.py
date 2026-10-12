"""Preferences → Controller sync → "Edit messages…": list one sync set's
messages, edit/delete/reorder them, and optionally send one as a test.

Thin by design: validation lives in ``controller_sync.messages_from_rows``
and reordering in ``controller_sync.move_message``. Nothing is saved here --
OK hands the edited set back to the Preferences dialog, whose own Save
persists it like the port edits.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from djmidi.controller_sync import (
    ControllerSyncSet,
    SyncMessage,
    messages_from_rows,
    move_message,
    resolve_output_port,
)

_EVENT_TYPES = ("Note On", "Note Off", "Control Change")


class SyncSetEditorDialog(QDialog):
    def __init__(
        self,
        sync_set: ControllerSyncSet,
        available_ports: Sequence[str] = (),
        sender: Callable[..., None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sync set — {sync_set.controller}")
        self._sync_set = sync_set
        self._result = sync_set
        self._sender = sender
        # The port a test message would go to, resolved like Sync does.
        self._test_port = resolve_output_port(sync_set, available_ports)

        hint = QLabel(
            "Messages are sent in this order. Double-click a value to edit it "
            "(channel 1–16, data 0–127)."
        )
        hint.setWordWrap(True)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Type", "Channel", "Data 1", "Data 2"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumWidth(420)
        self._fill(sync_set.messages)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        self.up_button = QPushButton("Move up")
        self.up_button.clicked.connect(lambda: self._move_selected(-1))
        self.down_button = QPushButton("Move down")
        self.down_button.clicked.connect(lambda: self._move_selected(1))
        self.send_button = QPushButton("Send selected")
        self.send_button.clicked.connect(self._send_selected)
        if self._test_port is None:
            self.send_button.setEnabled(False)
            self.send_button.setToolTip(f"{sync_set.controller} is not connected")
        else:
            self.send_button.setToolTip(f"Send the selected message to {self._test_port}")
        row_buttons = QHBoxLayout()
        for button in (self.delete_button, self.up_button, self.down_button):
            row_buttons.addWidget(button)
        row_buttons.addStretch(1)
        row_buttons.addWidget(self.send_button)

        self.status = QLabel("")
        self.status.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)
        layout.addLayout(row_buttons)
        layout.addWidget(self.status)
        layout.addWidget(buttons)

    def _fill(self, messages: Sequence[SyncMessage]) -> None:
        self.table.setRowCount(0)
        for message in messages:
            row = self.table.rowCount()
            self.table.insertRow(row)
            combo = QComboBox()
            combo.addItems(_EVENT_TYPES)
            combo.setCurrentText(message.event_type)
            self.table.setCellWidget(row, 0, combo)
            for column, value in ((1, message.channel), (2, message.data1), (3, message.data2)):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

    def _rows(self) -> list[tuple[str, str, str, str]]:
        rows = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 0)
            cells = [self.table.item(row, column) for column in (1, 2, 3)]
            channel, data1, data2 = (cell.text() if cell is not None else "" for cell in cells)
            rows.append((combo.currentText() if isinstance(combo, QComboBox) else "", channel, data1, data2))
        return rows

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else self.table.currentRow()

    def _validated(self) -> tuple[SyncMessage, ...] | None:
        try:
            return messages_from_rows(self._rows())
        except ValueError as exc:
            self.status.setText(str(exc))
            return None

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if 0 <= row < self.table.rowCount():
            self.table.removeRow(row)

    def _move_selected(self, offset: int) -> None:
        row = self._selected_row()
        messages = self._validated()
        if messages is None or not 0 <= row < len(messages):
            return
        self._fill(move_message(messages, row, offset))
        self.table.selectRow(max(0, min(len(messages) - 1, row + offset)))

    def _send_selected(self) -> None:
        if self._test_port is None:
            return
        row = self._selected_row()
        messages = self._validated()
        if messages is None or not 0 <= row < len(messages):
            return
        message = messages[row]
        sender = self._sender
        if sender is None:
            from djmidi.midi_io import send_midi_message

            sender = send_midi_message
        try:
            sender(
                output_port_name=self._test_port,
                event_type=message.event_type,
                channel_1_based=message.channel,
                data1=message.data1,
                data2=message.data2,
            )
        except Exception as exc:  # noqa: BLE001 - a test send must never crash the dialog
            self.status.setText(f"Sending failed: {exc}")
            return
        self.status.setText(f"Sent message {row + 1} to {self._test_port}")

    def accept(self) -> None:
        messages = self._validated()
        if messages is None:
            return
        self._result = self._sync_set.with_messages(messages)
        super().accept()

    def edited_sync_set(self) -> ControllerSyncSet:
        """The edited set after OK; the original one otherwise."""
        return self._result
