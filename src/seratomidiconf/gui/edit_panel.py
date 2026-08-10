from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seratomidiconf.gui.commands import (
    AddAliasCommand,
    RemoveAliasCommand,
    SetAttrCommand,
)
from seratomidiconf.model import Alias, Control, MappingElement, Translation, UserIO


class EditPanel(QWidget):
    """Shows editable fields for whichever tree node is currently selected.
    Every edit goes through `undo_stack` so it can be undone/redone."""

    def __init__(
        self,
        undo_stack: QUndoStack,
        on_applied: Callable[[object], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._undo_stack = undo_stack
        self._on_applied = on_applied
        self._node: object | None = None
        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel("Select a node in the tree to edit it."))
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
        self._clear_body()
        self._node = node
        if node is None:
            return
        if isinstance(node, Control):
            self._body = self._build_control_form(node)
        elif isinstance(node, UserIO):
            self._body = self._build_userio_form(node)
        elif isinstance(node, MappingElement):
            self._body = self._build_mapping_form(node)
        else:
            return
        self._layout.addWidget(self._body)

    def _build_control_form(self, control: Control) -> QWidget:
        box = QGroupBox("Control (MIDI trigger)")
        form = QFormLayout(box)

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
        return box

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
