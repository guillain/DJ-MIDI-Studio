"""Macros → Manage Macros…: create, edit and delete MIDI macros (issue #228).

Thin by design: validation lives in ``midi_macros.steps_from_rows`` /
``validate_macros`` and reordering reuses ``controller_sync.move_message``'s
logic on steps. Nothing is written here -- OK hands the edited list back to
the main window, which saves it to the Macros folder and rebuilds the menu.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.controller_sync import ControllerSyncSet, move_message
from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import MIDI_MACROS
from djmidi.gui.macro_player import MacroPlayer
from djmidi.midi_macros import MacroStep, MidiMacro, steps_from_rows, validate_macros

_EVENT_TYPES = ("Note On", "Note Off", "Control Change")
_COLUMNS = ("Type", "Channel", "Data 1", "Data 2", "Delay (ms)")


class MacroManagerDialog(QDialog):
    def __init__(
        self,
        macros: Sequence[MidiMacro],
        available_ports: Sequence[str] = (),
        sync_sets: Sequence[ControllerSyncSet] = (),
        reserved_shortcuts: Iterable[str] = (),
        sender: Callable[..., None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("MIDI Macros")
        self._macros: list[MidiMacro] = list(macros)
        self._result: list[MidiMacro] = list(macros)
        self._ports = list(available_ports)
        self._sync_sets = list(sync_sets)
        # The app's own menu shortcuts (Ctrl+O, Ctrl+S...): a macro may not take them.
        self._reserved = {text.casefold(): text for text in reserved_shortcuts if text}
        self._current = -1
        self._player = MacroPlayer(sender, self)
        self._player.finished.connect(lambda result: self.status.setText(result.summary()))

        # Left: the macro list.
        self.macro_list = QListWidget()
        self.macro_list.setMinimumWidth(170)
        self.macro_list.currentRowChanged.connect(self._on_macro_selected)
        self.new_button = QPushButton("New")
        self.new_button.clicked.connect(self._new_macro)
        self.delete_macro_button = QPushButton("Delete")
        self.delete_macro_button.clicked.connect(self._delete_macro)
        list_buttons = QHBoxLayout()
        list_buttons.addWidget(self.new_button)
        list_buttons.addWidget(self.delete_macro_button)
        left = QVBoxLayout()
        left.addWidget(self.macro_list, 1)
        left.addLayout(list_buttons)

        # Right: the selected macro.
        self.name_edit = QLineEdit()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.addItems(self._ports)
        self.port_combo.setToolTip(
            "Output port, or a controller name: matched against the connected ports like ⟳ Sync does"
        )
        self.shortcut_edit = QKeySequenceEdit()
        self.shortcut_edit.setMaximumSequenceLength(1)
        clear_shortcut = QPushButton("Clear")
        clear_shortcut.clicked.connect(self.shortcut_edit.clear)
        shortcut_row = QHBoxLayout()
        shortcut_row.addWidget(self.shortcut_edit, 1)
        shortcut_row.addWidget(clear_shortcut)
        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Output port", self.port_combo)
        form.addRow("Shortcut", shortcut_row)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumWidth(440)

        self.add_step_button = QPushButton("Add step")
        self.add_step_button.clicked.connect(self._add_step)
        self.delete_step_button = QPushButton("Delete step")
        self.delete_step_button.clicked.connect(self._delete_step)
        self.up_button = QPushButton("Move up")
        self.up_button.clicked.connect(lambda: self._move_step(-1))
        self.down_button = QPushButton("Move down")
        self.down_button.clicked.connect(lambda: self._move_step(1))
        self.from_sync_button = QPushButton("Add sync set…")
        self.from_sync_button.setToolTip("Append the messages of a recorded controller sync set")
        self.from_sync_button.setEnabled(bool(self._sync_sets))
        self.from_sync_button.clicked.connect(self._add_from_sync_set)
        self.test_button = QPushButton("Test")
        self.test_button.setToolTip("Play this macro now, as edited")
        self.test_button.clicked.connect(self._test_macro)
        step_buttons = QHBoxLayout()
        for button in (self.add_step_button, self.delete_step_button, self.up_button, self.down_button):
            step_buttons.addWidget(button)
        step_buttons.addStretch(1)
        step_buttons.addWidget(self.from_sync_button)
        step_buttons.addWidget(self.test_button)

        self.editor = QWidget()
        right = QVBoxLayout(self.editor)
        right.setContentsMargins(0, 0, 0, 0)
        right.addLayout(form)
        hint = QLabel(
            "Steps play top to bottom; each waits its delay before sending "
            "(channel 1–16, data 0–127, delay 0–60000 ms)."
        )
        hint.setWordWrap(True)
        right.addWidget(hint)
        right.addWidget(self.table, 1)
        right.addLayout(step_buttons)

        body = QHBoxLayout()
        body.addLayout(left)
        body.addWidget(self.editor, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *MIDI_MACROS))
        bottom.addWidget(self.status, 1)
        bottom.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addLayout(bottom)

        for macro in self._macros:
            self.macro_list.addItem(macro.name)
        if self._macros:
            self.macro_list.setCurrentRow(0)
        else:
            self._show(None)

    # --- editor <-> macro ---------------------------------------------------

    def _show(self, macro: MidiMacro | None) -> None:
        self.editor.setEnabled(macro is not None)
        self.delete_macro_button.setEnabled(macro is not None)
        macro = macro or MidiMacro("")
        self.name_edit.setText(macro.name)
        self.port_combo.setCurrentText(macro.output_port)
        self.shortcut_edit.setKeySequence(QKeySequence(macro.shortcut))
        self._fill(macro.steps)

    def _fill(self, steps: Sequence[MacroStep]) -> None:
        self.table.setRowCount(0)
        for step in steps:
            self._append_row(step)

    def _append_row(self, step: MacroStep) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        combo = QComboBox()
        combo.addItems(_EVENT_TYPES)
        combo.setCurrentText(step.message.event_type)
        self.table.setCellWidget(row, 0, combo)
        values = (step.message.channel, step.message.data1, step.message.data2, step.delay_ms)
        for column, value in enumerate(values, start=1):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, column, item)

    def _rows(self) -> list[tuple[str, ...]]:
        rows = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 0)
            cells = [self.table.item(row, column) for column in range(1, len(_COLUMNS))]
            values = [cell.text() if cell is not None else "" for cell in cells]
            rows.append((combo.currentText() if isinstance(combo, QComboBox) else "", *values))
        return rows

    def _edited(self) -> MidiMacro | None:
        """The macro as edited, or ``None`` (with the reason shown) when invalid."""
        name = self.name_edit.text().strip()
        if not name:
            self.status.setText("A macro needs a name")
            return None
        try:
            steps = steps_from_rows(self._rows())
        except ValueError as exc:
            self.status.setText(str(exc))
            return None
        shortcut = self.shortcut_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if shortcut and shortcut.casefold() in self._reserved:
            self.status.setText(f"{shortcut} is already used by the app's menus")
            return None
        return MidiMacro(name, self.port_combo.currentText().strip(), steps, shortcut)

    def _commit(self) -> bool:
        """Stores the editor into the list; False (and stays put) if invalid."""
        if not 0 <= self._current < len(self._macros):
            return True
        macro = self._edited()
        if macro is None:
            return False
        self._macros[self._current] = macro
        self.macro_list.item(self._current).setText(macro.name)
        return True

    def _on_macro_selected(self, row: int) -> None:
        if row == self._current:
            return
        if not self._commit():
            self.macro_list.blockSignals(True)
            self.macro_list.setCurrentRow(self._current)
            self.macro_list.blockSignals(False)
            return
        self._current = row
        self.status.setText("")
        self._show(self._macros[row] if 0 <= row < len(self._macros) else None)

    # --- macro list -----------------------------------------------------------

    def _new_macro(self) -> None:
        if not self._commit():
            return
        taken = {macro.name.casefold() for macro in self._macros}
        number = len(self._macros) + 1
        while f"macro {number}" in taken:
            number += 1
        port = self._ports[0] if self._ports else ""
        self._macros.append(MidiMacro(f"Macro {number}", port))
        self.macro_list.addItem(self._macros[-1].name)
        self.macro_list.setCurrentRow(len(self._macros) - 1)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _delete_macro(self) -> None:
        row = self._current
        if not 0 <= row < len(self._macros):
            return
        del self._macros[row]
        self._current = -1
        self.macro_list.blockSignals(True)
        self.macro_list.takeItem(row)
        self.macro_list.blockSignals(False)
        if self._macros:
            next_row = min(row, len(self._macros) - 1)
            self.macro_list.setCurrentRow(next_row)
            self._on_macro_selected(next_row)
        else:
            self._show(None)

    # --- steps ----------------------------------------------------------------

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else self.table.currentRow()

    def _add_step(self) -> None:
        # A new step repeats the selected (or last) one, the usual next edit.
        rows = self._rows()
        index = self._selected_row()
        source = rows[index] if 0 <= index < len(rows) else (rows[-1] if rows else None)
        step = MacroStep.from_dict({"event_type": "Note On", "channel": 1, "data1": 0, "data2": 127})
        if source is not None:
            try:
                step = steps_from_rows([source])[0]
            except ValueError:
                pass
        self._append_row(step)
        self.table.selectRow(self.table.rowCount() - 1)

    def _delete_step(self) -> None:
        row = self._selected_row()
        if 0 <= row < self.table.rowCount():
            self.table.removeRow(row)

    def _move_step(self, offset: int) -> None:
        row = self._selected_row()
        try:
            steps = steps_from_rows(self._rows())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        if not 0 <= row < len(steps):
            return
        self._fill(move_message(steps, row, offset))
        self.table.selectRow(max(0, min(len(steps) - 1, row + offset)))

    def _add_from_sync_set(self) -> None:
        labels = [f"{sync_set.label} ({len(sync_set.messages)} msg)" for sync_set in self._sync_sets]
        label, ok = QInputDialog.getItem(self, "Add sync set", "Append the messages of:", labels, 0, False)
        if ok and label in labels:
            self.append_sync_set(self._sync_sets[labels.index(label)])

    def append_sync_set(self, sync_set: ControllerSyncSet) -> None:
        for message in sync_set.messages:
            self._append_row(MacroStep(message))
        if not self.port_combo.currentText().strip():
            self.port_combo.setCurrentText(sync_set.output_port or sync_set.controller)

    def _test_macro(self) -> None:
        macro = self._edited()
        if macro is not None:
            self._player.play(macro, self._ports)

    # --- result ---------------------------------------------------------------

    def accept(self) -> None:
        if not self._commit():
            return
        problems = validate_macros(self._macros)
        if problems:
            self.status.setText(problems[0])
            return
        self._result = list(self._macros)
        super().accept()

    def edited_macros(self) -> list[MidiMacro]:
        """The edited list after OK; the original one otherwise."""
        return self._result
