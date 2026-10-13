from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog, midi_learn
from djmidi.gui import help_texts
from djmidi.gui.commands import (
    AddAliasCommand,
    AddGroupAliasCommand,
    OnGroupApplied,
    RemoveAliasCommand,
    RemoveGroupAliasCommand,
    SetAttrCommand,
    SetGroupAttrCommand,
)
from djmidi.gui.help_button import help_row
from djmidi.gui.mapping_group import MappingGroup
from djmidi.midi_io import MidiEvent
from djmidi.midi_learn import LearnedTrigger
from djmidi.model import Alias, Control, MappingElement, MidiConfig, Translation, UserIO

ConfirmConflict = Callable[[LearnedTrigger, list[str]], bool]


class EditPanel(QWidget):
    """Shows editable fields for whichever tree node is currently selected.
    Every edit goes through `undo_stack` so it can be undone/redone."""

    def __init__(
        self,
        undo_stack: QUndoStack,
        on_applied: Callable[[object], None],
        on_group_applied: OnGroupApplied | None = None,
        parent: QWidget | None = None,
        config_provider: Callable[[], MidiConfig | None] | None = None,
        ensure_listening: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._undo_stack = undo_stack
        self._on_applied = on_applied
        self._on_group_applied = on_group_applied or (lambda: None)
        self._config_provider = config_provider or (lambda: None)
        # MIDI Learn (issue #220) reuses the Live Monitor's input stream rather
        # than opening ports of its own: `ensure_listening` starts monitoring
        # if needed and says whether any input is open, and MainWindow feeds
        # every live event to `feed_learn_event`.
        self._ensure_listening = ensure_listening or (lambda: False)
        self.confirm_conflict: ConfirmConflict = self._ask_conflict
        self._learn_controls: Callable[[], list[Control]] | None = None
        self._learn_apply: Callable[[LearnedTrigger], None] | None = None
        self._learn_button: QPushButton | None = None
        self._learn_status: QLabel | None = None
        self._learn_message = ""
        self._learning = False
        self._learn_timer = QTimer(self)
        self._learn_timer.setSingleShot(True)
        self._learn_timer.setInterval(midi_learn.LEARN_TIMEOUT_MS)
        self._learn_timer.timeout.connect(lambda: self.cancel_learn("No control pressed — Learn timed out."))
        self._node: object | None = None
        self._layout = QVBoxLayout(self)
        self._layout.addLayout(help_row(self, *help_texts.EDIT_PANEL))
        self._prompt_label = QLabel("Select a node in the tree to edit it.")
        self._layout.addWidget(self._prompt_label)
        self._body: QWidget | None = None

    @property
    def current_node(self) -> object | None:
        return self._node

    def _push(self, target: object, attr: str, old_value: str | None, new_value: str | None, relabel_node: object) -> None:
        if old_value == new_value:
            return
        self._undo_stack.push(SetAttrCommand(target, attr, old_value, new_value, relabel_node, self._on_applied))

    def _clear_body(self) -> None:
        if self._body is not None:
            self._layout.removeWidget(self._body)
            self._body.deleteLater()
            self._body = None

    def set_node(self, node: object | None) -> None:
        self.cancel_learn(None)
        if node is not self._node:
            # A Learn result stays visible across the rebuild its own edit
            # triggers, but not once the user moves to another item.
            self._learn_message = ""
        self._clear_body()
        self._learn_button = None
        self._learn_status = None
        self._learn_controls = None
        self._learn_apply = None
        self._node = node
        if isinstance(node, Control):
            self._body = self._build_control_form(node)
        elif isinstance(node, UserIO):
            self._body = self._build_userio_form(node)
        elif isinstance(node, MappingElement):
            self._body = self._build_mapping_form(node)
        elif isinstance(node, MappingGroup):
            self._body = self._build_group_form(node)
        # The "select a node…" prompt is only useful while there is nothing to
        # edit; once a form is shown it's just noise above the fields.
        self._prompt_label.setVisible(self._body is None)
        if self._body is not None:
            self._layout.addWidget(self._body)

    def _build_physical_control_box(self, channel: str | None, event_type: str | None, control_no: str | None) -> QWidget:
        """A full-width box for the catalog match(es), kept out of any QFormLayout
        so its text isn't squeezed into the narrow field column of a form."""
        hits = catalog.lookup(channel, event_type, control_no)
        if hits:
            text = "\n".join(f"{h.controller}: {h.name}" for h in hits)
        else:
            text = "(not found in DDJ-XP2 / XDJ-XZ reference tables)"
        box = QGroupBox("Physical control")
        box_layout = QVBoxLayout(box)
        label = QLabel(text)
        label.setWordWrap(True)
        font = label.font()
        font.setPointSize(font.pointSize() + 1)
        label.setFont(font)
        # Keep enough vertical room for a long multi-controller match even
        # when the right-hand splitter is initially restored very small.
        # The label remains vertically expanding so the user can enlarge it
        # further with the splitter.
        line_height = label.fontMetrics().lineSpacing()
        label.setMinimumHeight(line_height * 12)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        box.setMinimumHeight(
            line_height * 12
            + box_layout.contentsMargins().top()
            + box_layout.contentsMargins().bottom()
            + 18
        )
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        box_layout.addWidget(label)
        return box

    def _build_control_form(self, control: Control) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        trigger_box = QGroupBox("Control (MIDI trigger)")
        form = QFormLayout(trigger_box)

        channel = QLineEdit(control.channel or "")
        event_type = QLineEdit(control.event_type or "")
        control_no = QLineEdit(control.control or "")

        channel.editingFinished.connect(lambda: self._push(control, "channel", control.channel, channel.text(), control))
        event_type.editingFinished.connect(
            lambda: self._push(control, "event_type", control.event_type, event_type.text(), control)
        )
        control_no.editingFinished.connect(
            lambda: self._push(control, "control", control.control, control_no.text(), control)
        )

        form.addRow("Channel", channel)
        form.addRow("Event type", event_type)
        form.addRow("Control", control_no)
        form.addRow(self._build_learn_row(lambda: [control], lambda trigger: self._learn_into_controls([control], trigger)))
        layout.addWidget(trigger_box)

        layout.addWidget(self._build_physical_control_box(control.channel, control.event_type, control.control))
        return container

    def _build_userio_form(self, userio: UserIO) -> QWidget:
        box = QGroupBox("User I/O")
        form = QFormLayout(box)
        event = QLineEdit(userio.event or "")

        event.editingFinished.connect(lambda: self._push(userio, "event", userio.event, event.text(), userio))

        form.addRow("Event (click/output)", event)
        form.addRow(QLabel(f"{len(userio.mappings)} mapping(s)"))
        return box

    def _build_mapping_form(self, mapping: MappingElement) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        deck_box = QGroupBox(f"<{mapping.tag}> target")
        form = QFormLayout(deck_box)
        deck_set = QLineEdit(mapping.deck_set or "")
        deck_id = QLineEdit(mapping.deck_id or "")
        slot_id = QLineEdit(mapping.slot_id or "")

        deck_set.editingFinished.connect(
            lambda: self._push(mapping, "deck_set", mapping.deck_set, deck_set.text(), mapping)
        )
        deck_id.editingFinished.connect(lambda: self._push(mapping, "deck_id", mapping.deck_id, deck_id.text(), mapping))
        slot_id.editingFinished.connect(lambda: self._push(mapping, "slot_id", mapping.slot_id, slot_id.text(), mapping))

        form.addRow("Deck set", deck_set)
        form.addRow("Deck id", deck_id)
        form.addRow("Slot id", slot_id)
        layout.addWidget(deck_box)

        # The trigger belongs to the parent <control>, so learning here moves
        # that whole control (with every function it holds).
        parent_control = midi_learn.find_parent_control(self._config_provider(), mapping)
        if parent_control is not None:
            learn_box = QGroupBox(
                f"Trigger: ch{parent_control.channel} {parent_control.event_type} #{parent_control.control}"
            )
            learn_layout = QVBoxLayout(learn_box)
            learn_layout.addWidget(
                self._build_learn_row(
                    lambda: [parent_control],
                    lambda trigger: self._learn_into_controls([parent_control], trigger),
                )
            )
            layout.addWidget(learn_box)

        translations_box = QGroupBox("Translations")
        translations_layout = QVBoxLayout(translations_box)
        translations_table = QTableWidget(0, 2)
        translations_table.setHorizontalHeaderLabels(["action_on", "behaviour"])
        translations_layout.addWidget(translations_table)

        aliases_box = QGroupBox("Aliases (on/off values) for selected translation")
        aliases_layout = QVBoxLayout(aliases_box)
        aliases_table = QTableWidget(0, 2)
        aliases_table.setHorizontalHeaderLabels(["name", "value"])
        aliases_layout.addWidget(aliases_table)
        alias_buttons = QHBoxLayout()
        add_alias_btn = QPushButton("Add alias")
        remove_alias_btn = QPushButton("Remove alias")
        alias_buttons.addWidget(add_alias_btn)
        alias_buttons.addWidget(remove_alias_btn)
        aliases_layout.addLayout(alias_buttons)

        def selected_translation() -> Translation | None:
            row = translations_table.currentRow()
            if 0 <= row < len(mapping.translations):
                return mapping.translations[row]
            return None

        def refresh_aliases_table() -> None:
            translation = selected_translation()
            aliases_table.blockSignals(True)
            aliases_table.setRowCount(0)
            if translation is not None:
                for alias in translation.aliases:
                    row = aliases_table.rowCount()
                    aliases_table.insertRow(row)
                    aliases_table.setItem(row, 0, QTableWidgetItem(alias.name))
                    aliases_table.setItem(row, 1, QTableWidgetItem(alias.value))
            aliases_table.blockSignals(False)

        def refresh_translations_table() -> None:
            translations_table.blockSignals(True)
            translations_table.setRowCount(0)
            for translation in mapping.translations:
                row = translations_table.rowCount()
                translations_table.insertRow(row)
                translations_table.setItem(row, 0, QTableWidgetItem(translation.action_on or ""))
                translations_table.setItem(row, 1, QTableWidgetItem(translation.behaviour or ""))
            translations_table.blockSignals(False)

        def on_translation_cell_changed(row: int, column: int) -> None:
            if row >= len(mapping.translations):
                return
            translation = mapping.translations[row]
            text = translations_table.item(row, column).text()
            if column == 0:
                self._push(translation, "action_on", translation.action_on, text, mapping)
            else:
                self._push(translation, "behaviour", translation.behaviour, text, mapping)

        def on_alias_cell_changed(row: int, column: int) -> None:
            translation = selected_translation()
            if translation is None or row >= len(translation.aliases):
                return
            alias = translation.aliases[row]
            text = aliases_table.item(row, column).text()
            if column == 0:
                self._push(alias, "name", alias.name, text, mapping)
            else:
                self._push(alias, "value", alias.value, text, mapping)

        def on_add_alias() -> None:
            translation = selected_translation()
            if translation is None:
                return
            self._undo_stack.push(AddAliasCommand(translation, Alias(name="new", value="0"), mapping, self._on_applied))
            refresh_aliases_table()

        def on_remove_alias() -> None:
            translation = selected_translation()
            if translation is None:
                return
            row = aliases_table.currentRow()
            if 0 <= row < len(translation.aliases):
                self._undo_stack.push(RemoveAliasCommand(translation, row, mapping, self._on_applied))
                refresh_aliases_table()

        translations_table.itemChanged.connect(on_translation_cell_changed)
        translations_table.currentCellChanged.connect(lambda *_: refresh_aliases_table())
        aliases_table.itemChanged.connect(on_alias_cell_changed)
        add_alias_btn.clicked.connect(on_add_alias)
        remove_alias_btn.clicked.connect(on_remove_alias)

        refresh_translations_table()
        refresh_aliases_table()

        layout.addWidget(translations_box)
        layout.addWidget(aliases_box)
        return container

    def _build_group_form(self, group: MappingGroup) -> QWidget:
        """A MappingGroup bundles every Control/MappingElement that shares the same
        trigger and deck/slot/tag/event — normally the ~10 duplicate copies Serato
        writes for one function. Every field here edits all members at once."""
        container = QWidget()
        layout = QVBoxLayout(container)

        mappings = [m for _, _, m in group.members]
        translations_lists = [m.translations for m in mappings]

        info_box = QGroupBox(f"<{group.tag}> [{group.event}] — {len(group.members)} linked control(s)")
        info_form = QFormLayout(info_box)
        info_form.addRow("Trigger", QLabel(f"ch{group.channel} {group.event_type} #{group.control_no}"))
        group_controls = midi_learn.unique_controls(control for control, _, _ in group.members)
        info_form.addRow(
            self._build_learn_row(lambda: group_controls, lambda trigger: self._learn_into_group(group, trigger))
        )
        layout.addWidget(info_box)

        layout.addWidget(self._build_physical_control_box(group.channel, group.event_type, group.control_no))

        deck_box = QGroupBox("Target (applies to all linked controls)")
        form = QFormLayout(deck_box)
        deck_set = QLineEdit(group.representative.deck_set or "")
        deck_id = QLineEdit(group.representative.deck_id or "")
        slot_id = QLineEdit(group.representative.slot_id or "")

        def push_group(attr: str, new_value: str) -> None:
            old_values = [getattr(m, attr) for m in mappings]
            if all(old == new_value for old in old_values):
                return
            self._undo_stack.push(SetGroupAttrCommand(mappings, attr, old_values, new_value, self._on_group_applied))

        deck_set.editingFinished.connect(lambda: push_group("deck_set", deck_set.text()))
        deck_id.editingFinished.connect(lambda: push_group("deck_id", deck_id.text()))
        slot_id.editingFinished.connect(lambda: push_group("slot_id", slot_id.text()))

        form.addRow("Deck set", deck_set)
        form.addRow("Deck id", deck_id)
        form.addRow("Slot id", slot_id)
        layout.addWidget(deck_box)

        translations_box = QGroupBox("Translations (applies to all linked controls)")
        translations_layout = QVBoxLayout(translations_box)
        translations_table = QTableWidget(0, 2)
        translations_table.setHorizontalHeaderLabels(["action_on", "behaviour"])
        translations_layout.addWidget(translations_table)

        aliases_box = QGroupBox("Aliases for selected translation (applies to all linked controls)")
        aliases_layout = QVBoxLayout(aliases_box)
        aliases_table = QTableWidget(0, 2)
        aliases_table.setHorizontalHeaderLabels(["name", "value"])
        aliases_layout.addWidget(aliases_table)
        alias_buttons = QHBoxLayout()
        add_alias_btn = QPushButton("Add alias")
        remove_alias_btn = QPushButton("Remove alias")
        alias_buttons.addWidget(add_alias_btn)
        alias_buttons.addWidget(remove_alias_btn)
        aliases_layout.addLayout(alias_buttons)

        representative_translations = group.representative.translations

        def selected_row() -> int:
            return translations_table.currentRow()

        def translations_at(row: int) -> list[Translation]:
            return [translations[row] for translations in translations_lists if row < len(translations)]

        def refresh_aliases_table() -> None:
            row = selected_row()
            aliases_table.blockSignals(True)
            aliases_table.setRowCount(0)
            if 0 <= row < len(representative_translations):
                for alias in representative_translations[row].aliases:
                    r = aliases_table.rowCount()
                    aliases_table.insertRow(r)
                    aliases_table.setItem(r, 0, QTableWidgetItem(alias.name))
                    aliases_table.setItem(r, 1, QTableWidgetItem(alias.value))
            aliases_table.blockSignals(False)

        def refresh_translations_table() -> None:
            translations_table.blockSignals(True)
            translations_table.setRowCount(0)
            for translation in representative_translations:
                row = translations_table.rowCount()
                translations_table.insertRow(row)
                translations_table.setItem(row, 0, QTableWidgetItem(translation.action_on or ""))
                translations_table.setItem(row, 1, QTableWidgetItem(translation.behaviour or ""))
            translations_table.blockSignals(False)

        def on_translation_cell_changed(row: int, column: int) -> None:
            targets = translations_at(row)
            if not targets:
                return
            attr = "action_on" if column == 0 else "behaviour"
            new_value = translations_table.item(row, column).text()
            old_values = [getattr(t, attr) for t in targets]
            if all(old == new_value for old in old_values):
                return
            self._undo_stack.push(SetGroupAttrCommand(targets, attr, old_values, new_value, self._on_group_applied))

        def on_alias_cell_changed(row: int, column: int) -> None:
            trans_row = selected_row()
            targets = [
                translations[trans_row].aliases[row]
                for translations in translations_lists
                if trans_row < len(translations) and row < len(translations[trans_row].aliases)
            ]
            if not targets:
                return
            attr = "name" if column == 0 else "value"
            new_value = aliases_table.item(row, column).text()
            old_values = [getattr(a, attr) for a in targets]
            if all(old == new_value for old in old_values):
                return
            self._undo_stack.push(SetGroupAttrCommand(targets, attr, old_values, new_value, self._on_group_applied))

        def on_add_alias() -> None:
            trans_row = selected_row()
            targets = translations_at(trans_row)
            if not targets:
                return
            aliases = [Alias(name="new", value="0") for _ in targets]
            self._undo_stack.push(AddGroupAliasCommand(targets, aliases, self._on_group_applied))
            refresh_aliases_table()

        def on_remove_alias() -> None:
            trans_row = selected_row()
            targets = translations_at(trans_row)
            alias_row = aliases_table.currentRow()
            if not targets or not (0 <= alias_row < len(representative_translations[trans_row].aliases)):
                return
            self._undo_stack.push(RemoveGroupAliasCommand(targets, alias_row, self._on_group_applied))
            refresh_aliases_table()

        translations_table.itemChanged.connect(on_translation_cell_changed)
        translations_table.currentCellChanged.connect(lambda *_: refresh_aliases_table())
        aliases_table.itemChanged.connect(on_alias_cell_changed)
        add_alias_btn.clicked.connect(on_add_alias)
        remove_alias_btn.clicked.connect(on_remove_alias)

        refresh_translations_table()
        refresh_aliases_table()

        layout.addWidget(translations_box)
        layout.addWidget(aliases_box)
        return container

    # ─── MIDI Learn ────────────────────────────────────────────────────────────

    @property
    def is_learning(self) -> bool:
        return self._learning

    def _build_learn_row(
        self, controls: Callable[[], list[Control]], apply: Callable[[LearnedTrigger], None]
    ) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Learn")
        button.setToolTip(
            "Listen for the next control pressed on your controller and move this trigger to it. "
            f"Click again (or wait {midi_learn.LEARN_TIMEOUT_MS // 1000} s) to cancel."
        )
        status = QLabel(self._learn_message)
        status.setWordWrap(True)
        row_layout.addWidget(button)
        row_layout.addWidget(status, 1)
        button.clicked.connect(self._on_learn_clicked)
        self._learn_button = button
        self._learn_status = status
        self._learn_controls = controls
        self._learn_apply = apply
        return row

    def _set_learn_message(self, message: str) -> None:
        self._learn_message = message
        if self._learn_status is not None:
            self._learn_status.setText(message)

    def _on_learn_clicked(self) -> None:
        if self._learning:
            self.cancel_learn("Learn cancelled.")
        else:
            self.start_learn()

    def start_learn(self) -> bool:
        if self._learn_apply is None or self._learning:
            return False
        if not self._ensure_listening():
            self._set_learn_message("No MIDI input is open: connect a controller, or pick one in Live Monitor.")
            return False
        self._learning = True
        if self._learn_button is not None:
            self._learn_button.setText("Cancel")
        self._set_learn_message(f"Press a control on your controller… ({midi_learn.LEARN_TIMEOUT_MS // 1000} s)")
        self._learn_timer.start()
        return True

    def cancel_learn(self, message: str | None = "Learn cancelled.") -> None:
        if not self._learning:
            return
        self._learning = False
        self._learn_timer.stop()
        if self._learn_button is not None:
            self._learn_button.setText("Learn")
        if message is not None:
            self._set_learn_message(message)

    def feed_learn_event(self, event: MidiEvent) -> bool:
        """Called for every live MIDI event; returns True when the event was
        consumed by an active Learn (only a press is: a release is ignored)."""
        if not self._learning or self._learn_controls is None or self._learn_apply is None:
            return False
        trigger = midi_learn.trigger_from_event(event)
        if trigger is None:
            return False
        controls = self._learn_controls()
        apply = self._learn_apply
        self.cancel_learn(None)
        if all(midi_learn.trigger_of(control) == trigger for control in controls):
            self._set_learn_message(f"Already on {trigger.label()}.")
            return True
        conflicts = midi_learn.find_trigger_conflicts(self._config_provider(), trigger, controls)
        if conflicts and not self.confirm_conflict(trigger, midi_learn.describe_conflicts(conflicts)):
            self._set_learn_message(f"Not reassigned: {trigger.label()} is already used.")
            return True
        warning = f" (also used by {len(conflicts)} other control(s))" if conflicts else ""
        self._set_learn_message(f"Learned {trigger.label()}{warning}.")
        apply(trigger)
        return True

    def _ask_conflict(self, trigger: LearnedTrigger, lines: list[str]) -> bool:
        listing = "\n".join(f"• {line}" for line in lines)
        answer = QMessageBox.warning(
            self,
            "Trigger already used",
            f"{trigger.label()} is already bound to:\n\n{listing}\n\n"
            "Reassign anyway? Both will fire on the same control.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _learn_into_controls(self, controls: list[Control], trigger: LearnedTrigger) -> None:
        """One undo step: a macro of the existing SetAttrCommand per changed field."""
        self._undo_stack.beginMacro(f"MIDI Learn → {trigger.label()}")
        for control in controls:
            for attr in ("channel", "event_type", "control"):
                self._push(control, attr, getattr(control, attr), getattr(trigger, attr), control)
        self._undo_stack.endMacro()

    def _learn_into_group(self, group: MappingGroup, trigger: LearnedTrigger) -> None:
        """Moves every linked duplicate at once (a macro of SetGroupAttrCommand),
        plus the group's own trigger fields so the refreshed panel shows it."""
        controls = midi_learn.unique_controls(control for control, _, _ in group.members)
        fields = (("channel", "channel"), ("event_type", "event_type"), ("control", "control_no"))
        self._undo_stack.beginMacro(f"MIDI Learn → {trigger.label()} ({len(controls)} linked)")
        for control_attr, group_attr in fields:
            new_value = getattr(trigger, control_attr)
            old_values = [getattr(control, control_attr) for control in controls]
            if any(old != new_value for old in old_values):
                self._undo_stack.push(
                    SetGroupAttrCommand(controls, control_attr, old_values, new_value, self._on_group_applied)
                )
            old_group_value = getattr(group, group_attr)
            if old_group_value != new_value:
                self._undo_stack.push(
                    SetGroupAttrCommand([group], group_attr, [old_group_value], new_value, self._on_group_applied)
                )
        self._undo_stack.endMacro()
