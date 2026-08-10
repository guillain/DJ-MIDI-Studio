from __future__ import annotations

from PySide6.QtCore import Signal
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

from seratomidiconf.model import Alias, Control, MappingElement, Translation, UserIO


class EditPanel(QWidget):
    """Shows editable fields for whichever tree node is currently selected."""

    changed = Signal(object)  # emits the node that was edited

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._node: object | None = None
        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel("Select a node in the tree to edit it."))
        self._body: QWidget | None = None

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

        def on_channel_changed(text: str) -> None:
            control.channel = text
            self.changed.emit(control)

        def on_event_type_changed(text: str) -> None:
            control.event_type = text
            self.changed.emit(control)

        def on_control_changed(text: str) -> None:
            control.control = text
            self.changed.emit(control)

        channel.editingFinished.connect(lambda: on_channel_changed(channel.text()))
        event_type.editingFinished.connect(lambda: on_event_type_changed(event_type.text()))
        control_no.editingFinished.connect(lambda: on_control_changed(control_no.text()))

        form.addRow("Channel", channel)
        form.addRow("Event type", event_type)
        form.addRow("Control", control_no)
        return box

    def _build_userio_form(self, userio: UserIO) -> QWidget:
        box = QGroupBox("User I/O")
        form = QFormLayout(box)
        event = QLineEdit(userio.event or "")

        def on_event_changed() -> None:
            userio.event = event.text()
            self.changed.emit(userio)

        event.editingFinished.connect(on_event_changed)
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

        def on_deck_set_changed() -> None:
            mapping.deck_set = deck_set.text()
            self.changed.emit(mapping)

        def on_deck_id_changed() -> None:
            mapping.deck_id = deck_id.text()
            self.changed.emit(mapping)

        def on_slot_id_changed() -> None:
            mapping.slot_id = slot_id.text()
            self.changed.emit(mapping)

        deck_set.editingFinished.connect(on_deck_set_changed)
        deck_id.editingFinished.connect(on_deck_id_changed)
        slot_id.editingFinished.connect(on_slot_id_changed)

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
                translation.action_on = text
            else:
                translation.behaviour = text
            self.changed.emit(mapping)

        def on_alias_cell_changed(row: int, column: int) -> None:
            translation = selected_translation()
            if translation is None or row >= len(translation.aliases):
                return
            alias = translation.aliases[row]
            text = aliases_table.item(row, column).text()
            if column == 0:
                alias.name = text
            else:
                alias.value = text
            self.changed.emit(mapping)

        def on_add_alias() -> None:
            translation = selected_translation()
            if translation is None:
                return
            translation.aliases.append(Alias(name="new", value="0"))
            refresh_aliases_table()
            self.changed.emit(mapping)

        def on_remove_alias() -> None:
            translation = selected_translation()
            if translation is None:
                return
            row = aliases_table.currentRow()
            if 0 <= row < len(translation.aliases):
                del translation.aliases[row]
                refresh_aliases_table()
                self.changed.emit(mapping)

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
