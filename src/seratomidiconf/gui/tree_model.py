from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from seratomidiconf.model import Control, MappingElement, MidiConfig, UserIO

NODE_ROLE = Qt.ItemDataRole.UserRole + 1


def control_label(control: Control) -> str:
    return f"ch{control.channel}  {control.event_type}  #{control.control}"


def userio_label(userio: UserIO) -> str:
    return userio.event


def mapping_label(mapping: MappingElement) -> str:
    return f"{mapping.tag}  (deck {mapping.deck_id}, slot {mapping.slot_id})"


def _mapping_item(mapping: MappingElement) -> QStandardItem:
    item = QStandardItem(mapping_label(mapping))
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


def build_tree_model(config: MidiConfig) -> QStandardItemModel:
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Mapping"])
    root = model.invisibleRootItem()
    for control in config.controls:
        root.appendRow(_control_item(control))
    return model


def relabel_item(item: QStandardItem, node: object) -> None:
    if isinstance(node, Control):
        item.setText(control_label(node))
    elif isinstance(node, UserIO):
        item.setText(userio_label(node))
    elif isinstance(node, MappingElement):
        item.setText(mapping_label(node))
