"""Builds the "By Controller" view: one column per controller (DDJ-XP2,
XDJ-XZ), each a tree of every physical control from catalog.py grouped by
section (PAD, DECK, EFFECT, ...), showing which are actually used in the
loaded config. This is the tree counterpart of the Layout tab's schematic —
same underlying cells (gui.layout.build_layout), same usage data, browsable
as text instead of a graphical grid.

Unlike the By Channel/By Deck columns, leaves here aren't a single domain
object (a cell can represent dozens of real <control> elements at once), so
selecting one doesn't feed the edit panel directly — it behaves like
clicking the matching Layout cell: jump to and highlight the first real
match elsewhere. See MainWindow._on_layout_cell_activated."""

from __future__ import annotations

from PySide6.QtGui import QStandardItem, QStandardItemModel

from seratomidiconf import catalog
from seratomidiconf.gui import layout as layout_mod
from seratomidiconf.gui.layout_view import Usage, _deck_sort_key

CELL_KEY_ROLE = 1  # distinct from tree_model.NODE_ROLE, which holds domain objects


def _leaf_text(cell: layout_mod.LayoutCell, per_deck: dict[str, set[str]]) -> str:
    if not per_deck:
        return f"{cell.label} (not used)"
    decks = ", ".join(f"D{d}" for d in sorted(per_deck, key=_deck_sort_key))
    tags = sorted({tag for tags in per_deck.values() for tag in tags})
    return f"{cell.label} — {', '.join(tags)} ({decks})"


def build_controller_columns(
    usage: Usage,
) -> list[tuple[str, QStandardItemModel, list[tuple[int, bool]]]]:
    """Returns (controller, model, [(section_row, has_any_used_leaf), ...]) so
    the caller can expand only the sections that actually have content."""
    columns: list[tuple[str, QStandardItemModel, list[tuple[int, bool]]]] = []
    for controller in catalog.CONTROLLER_NAMES:
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels([controller])
        root = model.invisibleRootItem()

        by_section: dict[str, list[layout_mod.LayoutCell]] = {}
        section_order: list[str] = []
        for cell in layout_mod.build_layout(controller):
            if cell.section not in by_section:
                by_section[cell.section] = []
                section_order.append(cell.section)
            by_section[cell.section].append(cell)

        expand_flags: list[tuple[int, bool]] = []
        for row, section in enumerate(section_order):
            section_item = QStandardItem(section)
            section_item.setEditable(False)
            section_item.setSelectable(False)
            any_used = False
            for cell in by_section[section]:
                per_deck = usage.get(cell.key, {})
                if per_deck:
                    any_used = True
                leaf = QStandardItem(_leaf_text(cell, per_deck))
                leaf.setEditable(False)
                leaf.setData(cell.key, CELL_KEY_ROLE)
                section_item.appendRow(leaf)
            root.appendRow(section_item)
            expand_flags.append((row, any_used))

        columns.append((controller, model, expand_flags))
    return columns


__all__ = ["CELL_KEY_ROLE", "build_controller_columns"]
