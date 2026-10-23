from __future__ import annotations

import re

from PySide6.QtCore import (
    QCoreApplication,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QStandardItem, QStandardItemModel

from djmidi.function_names import function_name, label_with_raw
from djmidi.model import Control, MappingElement, MidiConfig, UserIO

NODE_ROLE = Qt.ItemDataRole.UserRole + 1


def control_label(control: Control) -> str:
    return f"ch{control.channel}  {control.event_type}  #{control.control}"


def userio_label(userio: UserIO) -> str:
    return userio.event


def mapping_label(mapping: MappingElement) -> str:
    """Readable function name (issue #209) + deck/slot; the raw tag is in
    the row's tooltip (mapping_tooltip)."""
    return f"{function_name(mapping.tag)}  " + QCoreApplication.translate("MappingTree", "(deck {deck}, slot {slot})").format(
        deck=mapping.deck_id, slot=mapping.slot_id
    )


def mapping_tooltip(mapping: MappingElement) -> str:
    return f"{label_with_raw(mapping.tag)} — " + QCoreApplication.translate("MappingTree", "deck {deck}, slot {slot}").format(
        deck=mapping.deck_id, slot=mapping.slot_id
    )


class MappingFilterProxy(QSortFilterProxyModel):
    """The By Channel columns' search filter: a mapping row shows its
    readable function name, but typing its raw Serato tag
    (`auto_loop_roll_specific_length`) must still find it, so a row also
    matches on its MappingElement's tag."""

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex) -> bool:
        if super().filterAcceptsRow(source_row, source_parent):
            return True
        needle = self.filterRegularExpression().pattern()
        if not needle:
            return False
        node = self.sourceModel().index(source_row, 0, source_parent).data(NODE_ROLE)
        return isinstance(node, MappingElement) and _fixed_string_in(needle, node.tag)


def _fixed_string_in(pattern: str, text: str) -> bool:
    """`setFilterFixedString` stores the text as an escaped regex, so the
    pattern is searched as-is, case-insensitively like the proxy itself."""
    return bool(re.search(pattern, text, re.IGNORECASE))


def _mapping_item(mapping: MappingElement) -> QStandardItem:
    item = QStandardItem(mapping_label(mapping))
    item.setToolTip(mapping_tooltip(mapping))
    item.setData(mapping, NODE_ROLE)
    item.setEditable(False)
    return item


def _userio_item(userio: UserIO) -> QStandardItem:
    item = QStandardItem(userio_label(userio))
    item.setData(userio, NODE_ROLE)
    item.setEditable(False)
    for mapping in userio.mappings:
        item.appendRow(_mapping_item(mapping))
    return item


def _control_item(control: Control) -> QStandardItem:
    item = QStandardItem(control_label(control))
    item.setData(control, NODE_ROLE)
    item.setEditable(False)
    for userio in control.userios:
        item.appendRow(_userio_item(userio))
    return item


def _numeric_sort_key(value: str) -> tuple[bool, int, str]:
    """Sorts "2" before "10"; falls back to plain text for non-numeric values."""
    return (not value.isdigit(), int(value) if value.isdigit() else 0, value)


def _group_item(text: str) -> QStandardItem:
    """A label-only row (channel/note grouping): not tied to a model object,
    so it carries no NODE_ROLE and is never itself selected for editing."""
    item = QStandardItem(text)
    item.setEditable(False)
    item.setSelectable(False)
    return item


def _index_control_subtree(control: Control, control_item: QStandardItem, node_to_item: dict[int, QStandardItem]) -> None:
    node_to_item[id(control)] = control_item
    for row in range(control_item.rowCount()):
        userio_item = control_item.child(row)
        node_to_item[id(userio_item.data(NODE_ROLE))] = userio_item
        for mapping_row in range(userio_item.rowCount()):
            mapping_item = userio_item.child(mapping_row)
            node_to_item[id(mapping_item.data(NODE_ROLE))] = mapping_item


def build_channel_columns(config: MidiConfig) -> list[tuple[str, QStandardItemModel, dict[int, QStandardItem]]]:
    """One tree per channel — the "By Channel" tab shows these side by side as
    columns instead of nesting the channel level inside a single tree, so the
    channel is implicit in which column you're looking at. Each tree is
    Note/Control -> Control -> UserIO -> Mapping, same as build_tree_model
    minus the outer Channel grouping."""
    by_channel: dict[str, dict[str, list[Control]]] = {}
    for control in config.controls:
        by_channel.setdefault(control.channel, {}).setdefault(control.control, []).append(control)

    columns: list[tuple[str, QStandardItemModel, dict[int, QStandardItem]]] = []
    for channel in sorted(by_channel, key=_numeric_sort_key):
        by_note = by_channel[channel]
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels([QCoreApplication.translate("MappingTree", "Channel {channel}").format(channel=channel)])
        root = model.invisibleRootItem()
        node_to_item: dict[int, QStandardItem] = {}
        for note in sorted(by_note, key=_numeric_sort_key):
            note_item = _group_item(QCoreApplication.translate("MappingTree", "Note/Control {note}").format(note=note))
            for control in by_note[note]:
                control_item = _control_item(control)
                _index_control_subtree(control, control_item, node_to_item)
                note_item.appendRow(control_item)
            root.appendRow(note_item)
        columns.append((channel, model, node_to_item))
    return columns


def build_tree_model(config: MidiConfig) -> tuple[QStandardItemModel, dict[int, QStandardItem]]:
    """Returns the tree model plus a lookup from id(node) to its QStandardItem,
    so edits (including undo/redo replays) can relabel the right row directly.

    Controls are grouped by channel, then by note/control number, before the
    existing Control -> UserIO -> MappingElement hierarchy — the raw MIDI
    trigger is the natural way to browse this file (a real config repeats the
    same handful of channels hundreds of times)."""
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels([QCoreApplication.translate("MappingTree", "Channel / Note / Mapping")])
    root = model.invisibleRootItem()
    node_to_item: dict[int, QStandardItem] = {}

    by_channel: dict[str, dict[str, list[Control]]] = {}
    for control in config.controls:
        by_channel.setdefault(control.channel, {}).setdefault(control.control, []).append(control)

    for channel in sorted(by_channel, key=_numeric_sort_key):
        by_note = by_channel[channel]
        channel_item = _group_item(QCoreApplication.translate("MappingTree", "Channel {channel}").format(channel=channel))
        for note in sorted(by_note, key=_numeric_sort_key):
            note_item = _group_item(QCoreApplication.translate("MappingTree", "Note/Control {note}").format(note=note))
            for control in by_note[note]:
                control_item = _control_item(control)
                _index_control_subtree(control, control_item, node_to_item)
                note_item.appendRow(control_item)
            channel_item.appendRow(note_item)
        root.appendRow(channel_item)

    return model, node_to_item


def relabel_item(item: QStandardItem, node: object) -> None:
    if isinstance(node, Control):
        item.setText(control_label(node))
    elif isinstance(node, UserIO):
        item.setText(userio_label(node))
    elif isinstance(node, MappingElement):
        item.setText(mapping_label(node))
        item.setToolTip(mapping_tooltip(node))
