"""Builds the "By Deck" view: the same config data as the main tree, but
grouped by Serato deck/slot first, showing which physical control (and which
controller) drives each function — the reverse direction of the Layout tab,
which starts from the controller and shows which decks it touches.

Each leaf is a MappingGroup (see mapping_group.py): the set of duplicate
Control/MappingElement instances Serato writes for one logical function,
collapsed into a single editable row instead of showing every duplicate."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QStandardItem, QStandardItemModel

from djmidi import catalog
from djmidi.function_names import function_name, label_with_raw
from djmidi.gui.mapping_group import MappingGroup, build_mapping_groups
from djmidi.gui.translation import translator
from djmidi.gui.tree_model import NODE_ROLE
from djmidi.model import MidiConfig


def _sort_numeric_then_text(value: str) -> tuple[bool, int, str]:
    return (not value.isdigit(), int(value) if value.isdigit() else 0, value)


def _group_label(group: MappingGroup) -> str:
    hits = catalog.lookup(group.channel, group.event_type, group.control_no)
    physical = "; ".join(f"{h.controller}: {h.name}" for h in hits) or QCoreApplication.translate("MappingTree", "unknown physical control")
    count = f" (x{len(group.members)})" if len(group.members) > 1 else ""
    return f"{function_name(group.tag)} [{group.event}] — ch{group.channel} {group.event_type} #{group.control_no} -> {physical}{count}"


def _leaf(group: MappingGroup) -> QStandardItem:
    """A function row: readable name in the text, raw tag in the tooltip."""
    leaf = QStandardItem(_group_label(group))
    leaf.setToolTip(f"{label_with_raw(group.tag, group.slot_id, translator("FunctionNames"))} [{group.event}]")
    leaf.setEditable(False)
    leaf.setData(group, NODE_ROLE)
    return leaf


def _group_by_deck_then_slot(config: MidiConfig) -> dict[str, dict[str, list[MappingGroup]]]:
    decks: dict[str, dict[str, list[MappingGroup]]] = {}
    for group in build_mapping_groups(config):
        decks.setdefault(group.deck_id, {}).setdefault(group.slot_id, []).append(group)
    return decks


def build_deck_tree(config: MidiConfig) -> QStandardItemModel:
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels([QCoreApplication.translate("MappingTree", "Deck / Slot / Function -> physical control")])
    root = model.invisibleRootItem()

    decks = _group_by_deck_then_slot(config)

    for deck_id in sorted(decks, key=_sort_numeric_then_text):
        deck_item = QStandardItem(QCoreApplication.translate("MappingTree", "Deck {deck}").format(deck=deck_id))
        deck_item.setEditable(False)
        slots = decks[deck_id]
        for slot_id in sorted(slots, key=_sort_numeric_then_text):
            slot_item = QStandardItem(QCoreApplication.translate("MappingTree", "Slot {slot}").format(slot=slot_id))
            slot_item.setEditable(False)
            for group in slots[slot_id]:
                slot_item.appendRow(_leaf(group))
            deck_item.appendRow(slot_item)
        root.appendRow(deck_item)

    return model


def build_deck_columns(config: MidiConfig) -> list[tuple[str, QStandardItemModel]]:
    """One tree per deck — the "By Deck" tab shows these side by side as
    columns. Each tree is Slot -> function (MappingGroup), same as
    build_deck_tree minus the outer Deck grouping."""
    decks = _group_by_deck_then_slot(config)

    columns: list[tuple[str, QStandardItemModel]] = []
    for deck_id in sorted(decks, key=_sort_numeric_then_text):
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels([QCoreApplication.translate("MappingTree", "Deck {deck}").format(deck=deck_id)])
        root = model.invisibleRootItem()
        slots = decks[deck_id]
        for slot_id in sorted(slots, key=_sort_numeric_then_text):
            slot_item = QStandardItem(QCoreApplication.translate("MappingTree", "Slot {slot}").format(slot=slot_id))
            slot_item.setEditable(False)
            for group in slots[slot_id]:
                slot_item.appendRow(_leaf(group))
            root.appendRow(slot_item)
        columns.append((deck_id, model))
    return columns
