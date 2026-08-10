"""Builds the "By Deck" view: the same config data as the main tree, but
grouped by Serato deck/slot first, showing which physical control (and which
controller) drives each function — the reverse direction of the Layout tab,
which starts from the controller and shows which decks it touches."""

from __future__ import annotations

from PySide6.QtGui import QStandardItem, QStandardItemModel

from seratomidiconf import catalog
from seratomidiconf.gui.tree_model import NODE_ROLE
from seratomidiconf.model import Control, MidiConfig


def _sort_numeric_then_text(value: str) -> tuple[bool, int, str]:
    return (not value.isdigit(), int(value) if value.isdigit() else 0, value)


def build_deck_tree(config: MidiConfig) -> QStandardItemModel:
    model = QStandardItemModel()
    model.setHorizontalHeaderLabels(["Deck / Slot / Function -> physical control"])
    root = model.invisibleRootItem()

    decks: dict[str, dict[str, list[tuple[str, str, Control]]]] = {}
    for control in config.controls:
        for userio in control.userios:
            for mapping in userio.mappings:
                deck_id = mapping.deck_id or "(none)"
                slot_id = mapping.slot_id or "(none)"
                decks.setdefault(deck_id, {}).setdefault(slot_id, []).append((mapping.tag, userio.event, control))

    for deck_id in sorted(decks, key=_sort_numeric_then_text):
        deck_item = QStandardItem(f"Deck {deck_id}")
        deck_item.setEditable(False)
        slots = decks[deck_id]
        for slot_id in sorted(slots, key=_sort_numeric_then_text):
            slot_item = QStandardItem(f"Slot {slot_id}")
            slot_item.setEditable(False)
            for tag, event, control in slots[slot_id]:
                hits = catalog.lookup(control.channel, control.event_type, control.control)
                physical = "; ".join(f"{h.controller}: {h.name}" for h in hits) or "unknown physical control"
                leaf = QStandardItem(
                    f"{tag} [{event}] — ch{control.channel} {control.event_type} #{control.control} -> {physical}"
                )
                leaf.setEditable(False)
                leaf.setData(control, NODE_ROLE)
                slot_item.appendRow(leaf)
            deck_item.appendRow(slot_item)
        root.appendRow(deck_item)

    return model
