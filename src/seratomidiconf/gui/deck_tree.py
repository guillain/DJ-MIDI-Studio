"""Builds the "By Deck" view: the same config data as the main tree, but
grouped by Serato deck/slot first, showing which physical control (and which
controller) drives each function — the reverse direction of the Layout tab,
which starts from the controller and shows which decks it touches.

Each leaf is a MappingGroup (see mapping_group.py): the set of duplicate
Control/MappingElement instances Serato writes for one logical function,
collapsed into a single editable row instead of showing every duplicate."""

from __future__ import annotations

from PySide6.QtGui import QStandardItem, QStandardItemModel

from seratomidiconf import catalog
from seratomidiconf.gui.mapping_group import MappingGroup, build_mapping_groups
from seratomidiconf.gui.tree_model import NODE_ROLE
from seratomidiconf.model import MidiConfig


def _sort_numeric_then_text(value: str) -> tuple[bool, int, str]:
    return (not value.isdigit(), int(value) if value.isdigit() else 0, value)


def _group_label(group: MappingGroup) -> str:
    hits = catalog.lookup(group.channel, group.event_type, group.control_no)
    physical = "; ".join(f"{h.controller}: {h.name}" for h in hits) or "unknown physical control"
    count = f" (x{len(group.members)})" if len(group.members) > 1 else ""
    return f"{group.tag} [{group.event}] — ch{group.channel} {group.event_type} #{group.control_no} -> {physical}{count}"


def _group_by_deck_then_slot(config: MidiConfig) -> dict[str, dict[str, list[MappingGroup]]]:
    decks: dict[str, dict[str, list[MappingGroup]]] = {}
    for group in build_mapping_groups(config):
        decks.setdefault(group.deck_id, {}).setdefault(group.slot_id, []).append(group)
    return decks


def build_deck_tree(config: MidiConfig) -> QStandardItemModel:
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Deck / Slot / Function -> physical control"])
    root = model.invisibleRootItem()

    decks = _group_by_deck_then_slot(config)

    for deck_id in sorted(decks, key=_sort_numeric_then_text):
        deck_item = QStandardItem(f"Deck {deck_id}")
        deck_item.setEditable(False)
        slots = decks[deck_id]
        for slot_id in sorted(slots, key=_sort_numeric_then_text):
            slot_item = QStandardItem(f"Slot {slot_id}")
            slot_item.setEditable(False)
            for group in slots[slot_id]:
                leaf = QStandardItem(_group_label(group))
                leaf.setEditable(False)
                leaf.setData(group, NODE_ROLE)
                slot_item.appendRow(leaf)
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
        model.setHorizontalHeaderLabels([f"Deck {deck_id}"])
        root = model.invisibleRootItem()
        slots = decks[deck_id]
        for slot_id in sorted(slots, key=_sort_numeric_then_text):
            slot_item = QStandardItem(f"Slot {slot_id}")
            slot_item.setEditable(False)
            for group in slots[slot_id]:
                leaf = QStandardItem(_group_label(group))
                leaf.setEditable(False)
                leaf.setData(group, NODE_ROLE)
                slot_item.appendRow(leaf)
            root.appendRow(slot_item)
        columns.append((deck_id, model))
    return columns
