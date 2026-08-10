"""Groups catalog entries into a schematic grid of physical controls per
controller, so the GUI can draw a clickable, non-photorealistic layout and
highlight which physical buttons are actually used in a loaded config.

This is a schematic, not a scaled replica of the real hardware: non-pad
controls are auto-flowed into rows per section, and pad grids use the real
physical row/column arrangement (4x4 on DDJ-XP2, 4x2 on XDJ-XZ)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from seratomidiconf import catalog

CellKey = tuple[str, str, str]  # (controller, section, label)

_SHIFT_SUFFIXES = (
    " (+SHIFT press)",
    " (+SHIFT)",
    " +SHIFT",
    " (long press)",
    " (direct button, +SHIFT)",
    " (direct button)",
    " (press twice)",
)

_PAD_NUM_RE = re.compile(r"(?:Pad|Performance Pad) (\d+)")

_SECTION_ORDER = {
    "DDJ-XP2": ["DECK", "PAD MODE", "EFFECT", "BROWSE", "OTHER", "MIDI-OUT"],
    "XDJ-XZ": ["DECK", "EFFECT"],
}
_PAD_COLS = {"DDJ-XP2": 4, "XDJ-XZ": 4}
_COLS_PER_ROW = 4


def _base_name(name: str) -> str:
    for suffix in _SHIFT_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def cell_key(hit: catalog.ControlInfo) -> CellKey:
    """The layout cell a catalog hit belongs to: all pad-modes of one physical pad
    collapse to one cell, and a button collapses with its +SHIFT/long-press variants."""
    if hit.section == "PAD":
        match = _PAD_NUM_RE.search(hit.name)
        label = f"Pad {match.group(1)}" if match else hit.name
    else:
        label = _base_name(hit.name)
    return (hit.controller, hit.section, label)


@dataclass(frozen=True)
class LayoutCell:
    key: CellKey
    label: str
    section: str
    row: int
    col: int


def build_layout(controller: str) -> list[LayoutCell]:
    entries = catalog.static_entries(controller)

    labels: dict[CellKey, str] = {}
    order: list[CellKey] = []
    for entry in entries:
        key = (entry.controller, entry.section, _base_name(entry.name))
        if key not in labels:
            labels[key] = _base_name(entry.name)
            order.append(key)

    section_order = _SECTION_ORDER.get(controller, [])

    def rank(key: CellKey) -> tuple[int, int]:
        try:
            section_rank = section_order.index(key[1])
        except ValueError:
            section_rank = len(section_order)
        return (section_rank, order.index(key))

    cells: list[LayoutCell] = []
    row = 0
    col = 0
    current_section: str | None = None
    for key in sorted(order, key=rank):
        section = key[1]
        if section != current_section:
            if current_section is not None:
                row += 1
            current_section = section
            col = 0
        cells.append(LayoutCell(key, labels[key], section, row, col))
        col += 1
        if col >= _COLS_PER_ROW:
            col = 0
            row += 1
    if col != 0:
        row += 1

    pad_row0 = row
    pad_cols = _PAD_COLS[controller]
    for n in range(1, catalog.PAD_COUNTS[controller] + 1):
        r, c = divmod(n - 1, pad_cols)
        key = (controller, "PAD", f"Pad {n}")
        cells.append(LayoutCell(key, f"Pad {n}", "PAD", pad_row0 + r, c))

    return cells
