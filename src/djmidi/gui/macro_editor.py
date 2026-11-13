"""Macros → Manage Macros…: create, edit and delete MIDI macros (issue #228).

Thin by design: validation lives in ``midi_macros.steps_from_rows`` /
``validate_macros`` and reordering reuses ``controller_sync.move_message``'s
logic on steps. Nothing is written here -- OK hands the edited list back to
the main window, which saves it to the Macros folder and rebuilds the menu.

The Trigger row's Learn button (issue #252) binds the macro to controller
presses: every press is added to the trigger sequence, and the capture ends
on its own once no press came for the sequence's maximum gap (or on a
second click). *Learn steps* records the controller's messages as steps
instead, each with the delay actually waited since the previous one. The
dialog never opens a MIDI port itself: the main window passes
``ensure_listening`` (starts the Live Monitor, like the mapping editor's
Learn) and routes every live event to :meth:`feed_learn_event` while the
dialog is open.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog, user_paths
from djmidi.atelier.actions import TO_CONTROLLER
from djmidi.atelier.describe import describe_message, macro_target
from djmidi.controller_sync import ControllerSyncSet, SyncMessage, move_message
from djmidi.gui.action_groups import FlowLayout
from djmidi.gui.feature_step_dialog import FeatureStepDialog
from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import MIDI_MACROS
from djmidi.gui.macro_player import MacroPlayer
from djmidi.gui.translation import translator
from djmidi.gui.window_size import keep_wrapped_text_visible, usable_minimum
from djmidi.i18n import QT_TRANSLATE_NOOP
from djmidi.midi_learn import LEARN_TIMEOUT_MS
from djmidi.midi_macros import (
    MAX_TRIGGER_GAP_MS,
    MAX_TRIGGER_LENGTH,
    MIN_TRIGGER_GAP_MS,
    WAIT_TYPES,
    MacroBundleError,
    MacroStep,
    MacroTrigger,
    MidiMacro,
    PortOpener,
    annotate_with_features,
    merge_imported_macros,
    read_macro_bundle,
    sequence_label,
    step_from_event,
    step_type,
    steps_from_rows,
    validate_macros,
    write_macro_bundle,
)

if TYPE_CHECKING:
    from djmidi.midi_io import MidiEvent

_EVENT_TYPES = ("Note On", "Note Off", "Control Change")
# Wait steps (issue #367): the stored type key, and its label in the Type list.
_WAIT_LABELS = {
    WAIT_TYPES[0]: QT_TRANSLATE_NOOP("MacroManagerDialog", "Wait for Note On"),
    WAIT_TYPES[1]: QT_TRANSLATE_NOOP("MacroManagerDialog", "Wait for Control Change"),
}
_COLUMNS = (
    QT_TRANSLATE_NOOP("MacroManagerDialog", "Type"),
    QT_TRANSLATE_NOOP("MacroManagerDialog", "Channel"),
    QT_TRANSLATE_NOOP("MacroManagerDialog", "Data 1"),
    QT_TRANSLATE_NOOP("MacroManagerDialog", "Data 2"),
    QT_TRANSLATE_NOOP("MacroManagerDialog", "Delay (ms)"),
)
# Read-only last column (issue #413): each step named by the output
# controller's feature ("BEAT SYNC: LED on"); not part of the stored step.
_FEATURE_HEADER = QT_TRANSLATE_NOOP("MacroManagerDialog", "Feature")
_FEATURE_COLUMN = len(_COLUMNS)
_verb_translate = translator("FeatureActions")
# Step errors, duplicate checks and play results come from Qt-free
# midi_macros (issues #319, #326).
_macro_translate = translator("MidiMacros")


class MacroManagerDialog(QDialog):
    def __init__(
        self,
        macros: Sequence[MidiMacro],
        available_ports: Sequence[str] = (),
        sync_sets: Sequence[ControllerSyncSet] = (),
        reserved_shortcuts: Iterable[str] = (),
        sender: Callable[..., None] | None = None,
        parent=None,
        ensure_listening: Callable[[], bool] | None = None,
        port_opener: PortOpener | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("MIDI Macros"))
        self._macros: list[MidiMacro] = list(macros)
        self._result: list[MidiMacro] = list(macros)
        self._ports = list(available_ports)
        self._sync_sets = list(sync_sets)
        # The app's own menu shortcuts (Ctrl+O, Ctrl+S...): a macro may not take them.
        self._reserved = {text.casefold(): text for text in reserved_shortcuts if text}
        self._current = -1
        # The edited macro's controller trigger sequence, and the Learn state:
        # `_learn_target` is "trigger", "steps" or None.
        self._triggers: tuple[MacroTrigger, ...] = ()
        self._ensure_listening = ensure_listening
        self._learn_target: str | None = None
        self._captured = 0
        self._last_capture: float | None = None
        self._learn_timer = QTimer(self)
        self._learn_timer.setSingleShot(True)
        self._learn_timer.timeout.connect(self._on_learn_timeout)
        self._player = MacroPlayer(sender, self, port_opener)
        self._player.finished.connect(lambda result: self.status.setText(result.summary(_macro_translate)))

        # Left: the macro list.
        self.macro_list = QListWidget()
        usable_minimum(self.macro_list, 170, 120)  # a few rows even in the smallest window
        self.macro_list.setMinimumWidth(170)
        self.macro_list.currentRowChanged.connect(self._on_macro_selected)
        self.new_button = QPushButton(self.tr("New"))
        self.new_button.clicked.connect(self._new_macro)
        self.delete_macro_button = QPushButton(self.tr("Delete"))
        self.delete_macro_button.clicked.connect(self._delete_macro)
        list_buttons = QHBoxLayout()
        list_buttons.addWidget(self.new_button)
        list_buttons.addWidget(self.delete_macro_button)
        self.export_button = QPushButton(self.tr("Export…"))
        self.export_button.setToolTip(self.tr("Saves every macro above to a file another user can import."))
        self.export_button.clicked.connect(self._on_export_clicked)
        self.import_button = QPushButton(self.tr("Import…"))
        self.import_button.setToolTip(self.tr("Adds the macros from a file someone else exported."))
        self.import_button.clicked.connect(self._on_import_clicked)
        share_buttons = QHBoxLayout()
        share_buttons.addWidget(self.export_button)
        share_buttons.addWidget(self.import_button)
        left = QVBoxLayout()
        left.addWidget(self.macro_list, 1)
        left.addLayout(list_buttons)
        left.addLayout(share_buttons)

        # Right: the selected macro.
        self.name_edit = QLineEdit()
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.addItems(self._ports)
        self.port_combo.currentTextChanged.connect(lambda _text: self._on_port_changed())
        self.port_combo.setToolTip(
            self.tr("Output port, or a controller name: matched against the connected ports like ⟳ Sync does")
        )
        self.shortcut_edit = QKeySequenceEdit()
        self.shortcut_edit.setMaximumSequenceLength(1)
        clear_shortcut = QPushButton(self.tr("Clear"))
        clear_shortcut.clicked.connect(self.shortcut_edit.clear)
        shortcut_row = QHBoxLayout()
        shortcut_row.addWidget(self.shortcut_edit, 1)
        shortcut_row.addWidget(clear_shortcut)
        self.trigger_label = QLabel(self.tr("None"))
        self.trigger_label.setWordWrap(True)
        self.learn_button = QPushButton(self.tr("Learn"))
        self.learn_button.setToolTip(
            self.tr(
                "Press one button, or several in a row, on your controller: this macro then plays whenever "
                "they are pressed in that order. Learning stops once you stop pressing for the maximum gap, "
                "or when you click again."
            )
        )
        if ensure_listening is None:
            self.learn_button.setEnabled(False)
            self.learn_button.setToolTip(self.tr("MIDI Learn needs the main window's Live Monitor"))
        self.learn_button.clicked.connect(self._on_learn_clicked)
        self.clear_trigger_button = QPushButton(self.tr("Clear"))
        self.clear_trigger_button.clicked.connect(lambda: self._set_triggers(()))
        trigger_row = QHBoxLayout()
        trigger_row.addWidget(self.trigger_label, 1)
        trigger_row.addWidget(self.learn_button)
        trigger_row.addWidget(self.clear_trigger_button)
        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(MIN_TRIGGER_GAP_MS, MAX_TRIGGER_GAP_MS)
        self.gap_spin.setSingleStep(100)
        self.gap_spin.setSuffix(self.tr(" ms"))
        self.gap_spin.setToolTip(
            self.tr(
                "For a trigger of several presses: the longest pause allowed between two of them. "
                "Learn also stops after this pause."
            )
        )
        form = QFormLayout()
        form.addRow(self.tr("Name"), self.name_edit)
        form.addRow(self.tr("Output port"), self.port_combo)
        # Atelier (issue #413): with a port that is no controller (a virtual
        # port to the DJ software), the controller whose presses the macro
        # imitates -- its steps then read and build as that controller's
        # presses. Hidden when the port is a controller.
        self.simulates_combo = QComboBox()
        self.simulates_combo.addItem(self.tr("None (plain MIDI)"), "")
        for name in (definition.name for definition in catalog.all_controller_definitions()):
            self.simulates_combo.addItem(name, name)
        self.simulates_combo.setToolTip(
            self.tr("The controller this macro imitates towards the DJ software, through this virtual port.")
        )
        self.simulates_combo.currentIndexChanged.connect(lambda _index: self._on_port_changed())
        self.simulates_label = QLabel(self.tr("Simulates"))
        form.addRow(self.simulates_label, self.simulates_combo)
        form.addRow(self.tr("Shortcut"), shortcut_row)
        form.addRow(self.tr("Trigger"), trigger_row)
        form.addRow(self.tr("Max gap"), self.gap_spin)
        self.scenes_edit = QLineEdit()
        self.scenes_edit.setPlaceholderText(self.tr("All scenes"))
        self.scenes_edit.setToolTip(
            self.tr(
                "Sync scenes the controller trigger plays this macro in, separated by commas (empty: every "
                "scene). Two macros on the same trigger are fine when their scenes don't overlap. The "
                "Macros menu and the shortcut always play it."
            )
        )
        form.addRow(self.tr("Only in scenes"), self.scenes_edit)
        # A toggle (issue #367): two step lists, played in turn.
        self.toggle_box = QCheckBox(self.tr("Toggle: alternate between two step lists"))
        self.toggle_box.toggled.connect(self._on_toggle_changed)
        self.side_tabs = QTabBar()
        self.side_tabs.addTab(self.tr("A — 1st, 3rd… play"))
        self.side_tabs.addTab(self.tr("B — 2nd, 4th… play"))
        self.side_tabs.currentChanged.connect(self._on_side_changed)
        self._sides: list[tuple[MacroStep, ...]] = [(), ()]
        self._side = 0

        self.table = QTableWidget(0, len(_COLUMNS) + 1)
        usable_minimum(self.table, 440, 90)  # a few rows; the dialog must still fit 900x600
        self.table.setHorizontalHeaderLabels([self.tr(column) for column in _COLUMNS] + [self.tr(_FEATURE_HEADER)])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_FEATURE_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumWidth(440)
        self.table.itemChanged.connect(self._on_step_item_changed)

        self.add_step_button = QPushButton(self.tr("Add step"))
        self.add_step_button.clicked.connect(self._add_step)
        # Atelier (issue #413): pick a control and an LED action instead of
        # typing the numbers; enabled when the output port is a controller.
        self.add_feature_button = QPushButton(self.tr("Add from controller…"))
        self.add_feature_button.clicked.connect(self._add_feature_steps)
        self.add_feature_button.setEnabled(False)
        self.feature_step_dialog_factory = FeatureStepDialog
        self.delete_step_button = QPushButton(self.tr("Delete step"))
        self.delete_step_button.clicked.connect(self._delete_step)
        self.up_button = QPushButton(self.tr("Move up"))
        self.up_button.clicked.connect(lambda: self._move_step(-1))
        self.down_button = QPushButton(self.tr("Move down"))
        self.down_button.clicked.connect(lambda: self._move_step(1))
        self.learn_steps_button = QPushButton(self.tr("Learn steps"))
        self.learn_steps_button.setToolTip(
            self.tr(
                "Play the notes on your controller: each message is added as a step, with the delay you "
                "actually waited. Click again (or pause {seconds} s) to stop."
            ).format(seconds=LEARN_TIMEOUT_MS // 1000)
        )
        if ensure_listening is None:
            self.learn_steps_button.setEnabled(False)
            self.learn_steps_button.setToolTip(self.tr("MIDI Learn needs the main window's Live Monitor"))
        self.learn_steps_button.clicked.connect(self._on_learn_steps_clicked)
        self.from_sync_button = QPushButton(self.tr("Add sync set…"))
        self.from_sync_button.setToolTip(self.tr("Append the messages of a recorded controller sync set"))
        self.from_sync_button.setEnabled(bool(self._sync_sets))
        self.from_sync_button.clicked.connect(self._add_from_sync_set)
        self.test_button = QPushButton(self.tr("Test"))
        self.test_button.setToolTip(self.tr("Play this macro now, as edited"))
        self.test_button.clicked.connect(self._test_macro)
        # Wraps onto more lines in a narrow window instead of widening it.
        step_buttons_widget = QWidget()
        step_buttons = FlowLayout(step_buttons_widget)
        for button in (self.add_step_button, self.delete_step_button, self.up_button, self.down_button):
            step_buttons.addWidget(button)
        step_buttons.addWidget(self.add_feature_button)
        step_buttons.addWidget(self.learn_steps_button)
        step_buttons.addWidget(self.from_sync_button)
        step_buttons.addWidget(self.test_button)

        self.editor = QWidget()
        right = QVBoxLayout(self.editor)
        right.setContentsMargins(0, 0, 0, 0)
        right.addLayout(form)
        hint = QLabel(
            self.tr(
                "Steps play top to bottom; each waits its delay before sending "
                "(channel 1–16, data 0–127, delay 0–60000 ms)."
            )
        )
        hint.setWordWrap(True)
        right.addWidget(hint)
        right.addWidget(self.toggle_box)
        right.addWidget(self.side_tabs)
        right.addWidget(self.table, 1)
        right.addWidget(step_buttons_widget)

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
        keep_wrapped_text_visible(self)

    # --- editor <-> macro ---------------------------------------------------

    def _show(self, macro: MidiMacro | None) -> None:
        self.editor.setEnabled(macro is not None)
        self.delete_macro_button.setEnabled(macro is not None)
        macro = macro or MidiMacro("")
        self.name_edit.setText(macro.name)
        self._set_simulates(macro.simulates)
        self.port_combo.setCurrentText(macro.output_port)
        self._on_port_changed()
        self.shortcut_edit.setKeySequence(QKeySequence(macro.shortcut))
        self.cancel_learn(None)
        self._set_triggers(macro.triggers)
        self.gap_spin.setValue(macro.trigger_gap_ms)
        self.scenes_edit.setText(", ".join(macro.scenes))
        self._sides = [macro.steps, macro.alternate_steps]
        self._side = 0
        self.side_tabs.blockSignals(True)
        self.side_tabs.setCurrentIndex(0)
        self.side_tabs.blockSignals(False)
        self.toggle_box.blockSignals(True)
        self.toggle_box.setChecked(macro.is_toggle)
        self.toggle_box.blockSignals(False)
        self.side_tabs.setVisible(macro.is_toggle)
        self._fill(macro.steps)

    def _store_side(self) -> bool:
        """Keeps the visible table as its side's steps; False if invalid."""
        try:
            self._sides[self._side] = steps_from_rows(self._rows(), _macro_translate)
        except ValueError as exc:
            self.status.setText(str(exc))
            return False
        return True

    def _on_side_changed(self, index: int) -> None:
        if index == self._side:
            return
        if not self._store_side():
            self.side_tabs.blockSignals(True)
            self.side_tabs.setCurrentIndex(self._side)
            self.side_tabs.blockSignals(False)
            return
        self._side = index
        self._fill(self._sides[index])

    def _on_toggle_changed(self, checked: bool) -> None:
        self.side_tabs.setVisible(checked)
        if not checked and self._side != 0:
            self.side_tabs.setCurrentIndex(0)

    def _fill(self, steps: Sequence[MacroStep]) -> None:
        self.table.setRowCount(0)
        for step in steps:
            self._append_row(step)

    def _append_row(self, step: MacroStep) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        combo = QComboBox()
        for event_type in _EVENT_TYPES:
            combo.addItem(event_type, event_type)
        for key, label in _WAIT_LABELS.items():
            combo.addItem(self.tr(label), key)
        combo.setCurrentIndex(max(combo.findData(step_type(step)), 0))
        self.table.setCellWidget(row, 0, combo)
        values = (step.message.channel, step.message.data1, step.message.data2, step.delay_ms)
        self.table.blockSignals(True)
        for column, value in enumerate(values, start=1):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, column, item)
        feature_item = QTableWidgetItem()
        feature_item.setFlags(feature_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, _FEATURE_COLUMN, feature_item)
        self.table.blockSignals(False)
        combo.currentIndexChanged.connect(lambda _index, combo=combo: self._refresh_feature_row(self._row_of(combo)))
        self._refresh_feature_row(row)

    def _row_of(self, combo: QComboBox) -> int:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 0) is combo:
                return row
        return -1

    def _on_step_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != _FEATURE_COLUMN:
            self._refresh_feature_row(item.row())

    def _set_simulates(self, name: str) -> None:
        index = self.simulates_combo.findData(name)
        if index < 0 and name:  # a controller not registered here: keep the name
            self.simulates_combo.addItem(name, name)
            index = self.simulates_combo.count() - 1
        self.simulates_combo.blockSignals(True)
        self.simulates_combo.setCurrentIndex(max(index, 0))
        self.simulates_combo.blockSignals(False)

    def target(self) -> tuple[str, str] | None:
        """(controller, direction) the steps are about (`macro_target`)."""
        return macro_target(self.port_combo.currentText(), self.simulates_combo.currentData() or "")

    def _on_port_changed(self) -> None:
        drives = macro_target(self.port_combo.currentText()) is not None
        self.simulates_combo.setVisible(not drives)
        self.simulates_label.setVisible(not drives)
        self._refresh_feature_column()
        target = self.target()
        self.add_feature_button.setEnabled(target is not None)
        if target is None:
            tip = self.tr("Pick a controller's output port, or the controller this macro simulates, to add steps.")
        elif target[1] == TO_CONTROLLER:
            tip = self.tr("Add steps by picking one of {controller}'s controls and an LED action.").format(
                controller=target[0]
            )
        else:
            tip = self.tr("Add steps imitating one of {controller}'s controls: a tap, a press, a release or a value.").format(
                controller=target[0]
            )
        self.add_feature_button.setToolTip(tip)

    def _add_feature_steps(self) -> None:
        target = self.target()
        if target is None:
            return
        controller, direction = target
        dialog = self.feature_step_dialog_factory(controller, self, direction)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for step in dialog.steps():
            self._append_row(step)
        self.table.selectRow(self.table.rowCount() - 1)

    def _refresh_feature_column(self) -> None:
        for row in range(self.table.rowCount()):
            self._refresh_feature_row(row)

    def feature_text(self, row: int) -> str:
        item = self.table.item(row, _FEATURE_COLUMN)
        return item.text() if item is not None else ""

    def _refresh_feature_row(self, row: int) -> None:
        """Names step `row` by the output controller's feature, when the
        output port is a known controller and the step is a plain message."""
        item = self.table.item(row, _FEATURE_COLUMN) if row >= 0 else None
        if item is None:
            return
        target = self.target()
        text = ""
        if target is None:
            tip = self.tr("Pick a controller's output port, or the controller this macro simulates, to see each step as one of its features.")
        else:
            controller, direction = target
            if direction == TO_CONTROLLER:
                tip = self.tr("Steps sent to {controller}, read as its features (LED messages).").format(
                    controller=controller
                )
            else:
                tip = self.tr("Steps imitating {controller}, read as its presses and values.").format(
                    controller=controller
                )
            message = self._row_message(row)
            if message is not None:
                text = describe_message(controller, message, direction, _verb_translate) or ""
        self.table.blockSignals(True)
        item.setText(text)
        item.setToolTip(tip)
        self.table.blockSignals(False)

    def _row_message(self, row: int) -> SyncMessage | None:
        combo = self.table.cellWidget(row, 0)
        kind = combo.currentData() if isinstance(combo, QComboBox) else ""
        if kind not in _EVENT_TYPES:  # a wait step waits for a press, it doesn't drive the controller
            return None
        try:
            values = [int(self.table.item(row, column).text()) for column in (1, 2, 3)]
            return SyncMessage.create(kind, *values)
        except (AttributeError, TypeError, ValueError):
            return None

    def _rows(self) -> list[tuple[str, ...]]:
        rows = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 0)
            cells = [self.table.item(row, column) for column in range(1, len(_COLUMNS))]
            values = [cell.text() if cell is not None else "" for cell in cells]
            rows.append((combo.currentData() if isinstance(combo, QComboBox) else "", *values))
        return rows

    def _edited(self) -> MidiMacro | None:
        """The macro as edited, or ``None`` (with the reason shown) when invalid."""
        name = self.name_edit.text().strip()
        if not name:
            self.status.setText(self.tr("A macro needs a name"))
            return None
        if not self._store_side():
            return None
        steps = self._sides[0]
        alternate = self._sides[1] if self.toggle_box.isChecked() else ()
        scenes = tuple(dict.fromkeys(part.strip() for part in self.scenes_edit.text().split(",") if part.strip()))
        shortcut = self.shortcut_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if shortcut and shortcut.casefold() in self._reserved:
            self.status.setText(self.tr("{shortcut} is already used by the app's menus").format(shortcut=shortcut))
            return None
        # Steps that drive a known controller record its feature (issue #413).
        return annotate_with_features(
            MidiMacro(
                name,
                self.port_combo.currentText().strip(),
                steps,
                shortcut,
                self._triggers,
                self.gap_spin.value(),
                alternate,
                scenes,
                self.simulates_combo.currentData() or "",
            )
        )

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
        template = self.tr("Macro {number}")
        while template.format(number=number).casefold() in taken:
            number += 1
        port = self._ports[0] if self._ports else ""
        self._macros.append(MidiMacro(template.format(number=number), port))
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

    # --- sharing (issue #408) --------------------------------------------------

    def _on_export_clicked(self) -> None:
        if not self._commit():
            return
        if not self._macros:
            self.status.setText(self.tr("Nothing to export yet."))
            return
        default = str(user_paths.subfolder(user_paths.EXPORTS) / "macros.json")
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export macros"), default, self.tr("JSON files (*.json)"))
        if not path:
            return
        try:
            write_macro_bundle(path, self._macros)
        except OSError as exc:
            QMessageBox.warning(
                self, self.tr("Export macros"), self.tr("Could not write {path}:").format(path=path) + f"\n{exc}"
            )
            return
        self.status.setText(self.tr("Exported {count} macro(s) to {path}.").format(count=len(self._macros), path=path))

    def _on_import_clicked(self) -> None:
        default = str(user_paths.subfolder(user_paths.EXPORTS))
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Import macros"), default, self.tr("JSON files (*.json)"))
        if not path:
            return
        try:
            imported = read_macro_bundle(path)
        except (OSError, MacroBundleError) as exc:
            QMessageBox.warning(self, self.tr("Import macros"), self.tr("Could not read {path}:").format(path=path) + f"\n{exc}")
            return
        existing_names = {macro.name.casefold() for macro in self._macros}
        colliding = sum(1 for macro in imported if macro.name.casefold() in existing_names)
        overwrite = False
        if colliding:
            choice = QMessageBox.question(
                self,
                self.tr("Import macros"),
                self.tr(
                    "{count} of the {total} imported macro(s) share a name with one you already have. "
                    "Replace them, or keep both (the imported one renamed)?"
                ).format(count=colliding, total=len(imported)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            overwrite = choice == QMessageBox.StandardButton.Yes
        if not self._commit():
            return
        self._macros = merge_imported_macros(self._macros, imported, overwrite)
        self.macro_list.blockSignals(True)
        self.macro_list.clear()
        for macro in self._macros:
            self.macro_list.addItem(macro.name)
        self.macro_list.blockSignals(False)
        self._current = -1
        if self._macros:
            self.macro_list.setCurrentRow(0)
        self.status.setText(self.tr("Imported {count} macro(s).").format(count=len(imported)))

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
            steps = steps_from_rows(self._rows(), _macro_translate)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        if not 0 <= row < len(steps):
            return
        self._fill(move_message(steps, row, offset))
        self.table.selectRow(max(0, min(len(steps) - 1, row + offset)))

    def _add_from_sync_set(self) -> None:
        labels = [
            self.tr("{label} ({count} msg)").format(label=sync_set.label, count=len(sync_set.messages))
            for sync_set in self._sync_sets
        ]
        label, ok = QInputDialog.getItem(
            self, self.tr("Add sync set"), self.tr("Append the messages of:"), labels, 0, False
        )
        if ok and label in labels:
            self.append_sync_set(self._sync_sets[labels.index(label)])

    def append_sync_set(self, sync_set: ControllerSyncSet) -> None:
        for message in sync_set.messages:
            self._append_row(MacroStep(message))
        if not self.port_combo.currentText().strip():
            self.port_combo.setCurrentText(sync_set.output_port or sync_set.controller)

    def _test_macro(self) -> None:
        """Plays the step list on screen (side B of a toggle when shown)."""
        macro = self._edited()
        if macro is not None:
            self._player.play(macro.variant(self.toggle_box.isChecked() and self._side == 1), self._ports)

    # --- MIDI Learn (issues #252, trigger sequences) ------------------------

    @property
    def is_learning(self) -> bool:
        return self._learn_target is not None

    def _set_triggers(self, triggers: Sequence[MacroTrigger]) -> None:
        self._triggers = tuple(triggers)
        self.trigger_label.setText(sequence_label(self._triggers, _macro_translate) or self.tr("None"))
        self.clear_trigger_button.setEnabled(bool(self._triggers))

    def _on_learn_clicked(self) -> None:
        if self._learn_target == "trigger":
            self._finish_learn()
        else:
            self.start_learn()

    def _on_learn_steps_clicked(self) -> None:
        if self._learn_target == "steps":
            self._finish_learn()
        else:
            self.start_step_learn()

    def start_learn(self) -> bool:
        """Learn the trigger: every press is added to a new sequence."""
        return self._start("trigger")

    def start_step_learn(self) -> bool:
        """Learn steps: every message is appended to the steps."""
        return self._start("steps")

    def _start(self, target: str) -> bool:
        if self._ensure_listening is None or not 0 <= self._current < len(self._macros):
            return False
        self.cancel_learn(None)
        if not self._ensure_listening():
            self.status.setText(self.tr("No MIDI input is open: connect a controller, or pick one in Live Monitor."))
            return False
        self._learn_target = target
        self._captured = 0
        self._last_capture = None
        if target == "trigger":
            self.learn_button.setText(self.tr("Stop"))
            self.status.setText(
                self.tr("Press a button, or several in a row, on your controller… ({seconds} s)").format(
                    seconds=LEARN_TIMEOUT_MS // 1000
                )
            )
        else:
            self.learn_steps_button.setText(self.tr("Stop"))
            self.status.setText(
                self.tr("Play the notes to record on your controller… ({seconds} s)").format(
                    seconds=LEARN_TIMEOUT_MS // 1000
                )
            )
        self._learn_timer.start(LEARN_TIMEOUT_MS)
        return True

    def _end(self) -> None:
        self._learn_target = None
        self._learn_timer.stop()
        self.learn_button.setText(self.tr("Learn"))
        self.learn_steps_button.setText(self.tr("Learn steps"))

    def _on_learn_timeout(self) -> None:
        if self._captured:
            self._finish_learn()
        else:
            self.cancel_learn(self.tr("No control pressed — Learn timed out."))

    def _finish_learn(self) -> None:
        """Ends a Learn, keeping what it captured."""
        target, captured = self._learn_target, self._captured
        if target is None:
            return
        if not captured:
            self.cancel_learn()
            return
        self._end()
        if target == "trigger":
            self.status.setText(
                self.tr("Learned {trigger}.").format(trigger=sequence_label(self._triggers, _macro_translate))
            )
        else:
            self.status.setText(self.tr("Learned {count} step(s).").format(count=captured))

    def cancel_learn(self, message: str | None = "") -> None:
        """Stops a Learn; `message` replaces the status line, "" means the
        default "Learn cancelled." and None leaves the line alone. What was
        already captured stays."""
        if self._learn_target is None:
            return
        self._end()
        if message == "":
            message = self.tr("Learn cancelled.")
        if message is not None:
            self.status.setText(message)

    def feed_learn_event(self, event: MidiEvent) -> bool:
        """Called for every live MIDI event while the dialog is open; returns
        True when an active Learn consumed it (a press for the trigger; a
        Note On/Off or CC from the controller for the steps)."""
        if self._learn_target == "trigger":
            return self._capture_trigger(event)
        if self._learn_target == "steps":
            return self._capture_step(event)
        # A Test run waiting for a press (issue #367) gets it.
        return self._player.feed_event(event)

    def _capture_trigger(self, event: MidiEvent) -> bool:
        press = MacroTrigger.from_event(event)
        if press is None:
            return False
        sequence = (*self._triggers, press) if self._captured else (press,)
        self._captured += 1
        self._set_triggers(sequence)
        if len(sequence) >= MAX_TRIGGER_LENGTH:
            self._finish_learn()
            return True
        self.status.setText(
            self.tr("Learning {trigger}… press the next one, or pause {ms} ms to finish.").format(
                trigger=sequence_label(sequence, _macro_translate), ms=self.gap_spin.value()
            )
        )
        self._learn_timer.start(self.gap_spin.value())
        return True

    def _capture_step(self, event: MidiEvent) -> bool:
        delay = 0.0 if self._last_capture is None else (event.timestamp - self._last_capture) * 1000
        step = step_from_event(event, delay)
        if step is None:
            return False
        self._last_capture = event.timestamp
        self._captured += 1
        self._append_row(step)
        self.table.scrollToBottom()
        self.status.setText(self.tr("Recorded {count} step(s)… click Stop when done.").format(count=self._captured))
        self._learn_timer.start(LEARN_TIMEOUT_MS)
        return True

    # --- result ---------------------------------------------------------------

    def done(self, result: int) -> None:
        self.cancel_learn(None)
        # A Test run waiting on a delay holds its port open (issue #314).
        self._player.stop_all()
        super().done(result)

    def accept(self) -> None:
        if not self._commit():
            return
        problems = validate_macros(self._macros, _macro_translate)
        if problems:
            self.status.setText(problems[0])
            return
        self._result = list(self._macros)
        super().accept()

    def edited_macros(self) -> list[MidiMacro]:
        """The edited list after OK; the original one otherwise."""
        return self._result
