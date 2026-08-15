"""Groups catalog entries into a schematic grid of physical controls per
controller, so the GUI can draw a clickable, non-photorealistic layout and
highlight which physical buttons are actually used in a loaded config.

This is a schematic, not a scaled replica of the real hardware: non-pad
controls are auto-flowed into rows per section, and pad grids use the real
physical row/column arrangement (4x4 on DDJ-XP2, 4x2 on XDJ-XZ)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from djmidi import catalog

CellKey = tuple[str, str, str]  # (controller, section, label)
VisualKind = Literal["button", "pad", "knob", "fader", "jog"]

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


def visual_kind_for(section: str, name: str) -> VisualKind:
    """Infer a DJ-oriented control shape from catalog vocabulary.

    This is deliberately presentation-only: MIDI mappings remain entirely
    defined by the catalog/XML. Unknown controls safely fall back to buttons.
    """
    if section.upper() == "PAD" or _PAD_NUM_RE.search(name):
        return "pad"
    lowered = name.casefold()
    if "jog" in lowered or "wheel" in lowered or "rotary" in lowered:
        return "jog"
    if any(
        word in lowered
        for word in ("fader", "volume", "level", "crossfader", "master level", "booth")
    ):
        return "fader"
    if any(
        word in lowered
        for word in (
            "trim",
            "gain",
            "eq",
            "filter",
            "frequency",
            "parameter",
            "effect",
            "color",
            "sound color",
            "mix",
        )
    ):
        return "knob"
    return "button"


_DISPLAY_CONTROLS: dict[str, tuple[tuple[str, VisualKind], ...]] = {
    "XDJ-XZ": (
        ("Channel 1 Trim", "knob"),
        ("Channel 1 EQ High", "knob"),
        ("Channel 1 EQ Mid", "knob"),
        ("Channel 1 EQ Low", "knob"),
        ("Channel 1 Volume", "fader"),
        ("Channel 2 Trim", "knob"),
        ("Channel 2 EQ High", "knob"),
        ("Channel 2 EQ Mid", "knob"),
        ("Channel 2 EQ Low", "knob"),
        ("Channel 2 Volume", "fader"),
        ("Master Level", "knob"),
        ("Booth Level", "knob"),
        ("Crossfader", "fader"),
    ),
    "DDJ-XP2": (
        ("Slide FX 1", "fader"),
        ("Slide FX 2", "fader"),
        ("Effect 1 Depth", "knob"),
        ("Effect 2 Depth", "knob"),
        ("Effect 3 Depth", "knob"),
    ),
}


@dataclass(frozen=True)
class LayoutCell:
    key: CellKey
    label: str
    section: str
    row: int
    col: int
    visual_kind: VisualKind = "button"


def build_layout(controller: str) -> list[LayoutCell]:
    definition = catalog.get_definition(controller)
    entries = definition.static_entries

    labels: dict[CellKey, str] = {}
    order: list[CellKey] = []
    for entry in entries:
        key = (entry.controller, entry.section, _base_name(entry.name))
        if key not in labels:
            labels[key] = _base_name(entry.name)
            order.append(key)

    section_order = list(definition.section_order)

    def rank(key: CellKey) -> tuple[int, int]:
        try:
            section_rank = section_order.index(key[1])
        except ValueError:
            section_rank = len(section_order)
        return (section_rank, order.index(key))

    cells: list[LayoutCell] = []

    # Pads first: they're what a real Serato config maps almost exclusively
    # (see the empirical finding in CLAUDE.md), so lead with the section
    # that's actually populated instead of burying it under rows of unused
    # DECK/EFFECT/BROWSE reference cells.
    pad_cols = definition.pad_columns
    for n in range(1, definition.pad_count + 1):
        r, c = divmod(n - 1, pad_cols)
        key = (controller, "PAD", f"Pad {n}")
        cells.append(LayoutCell(key, f"Pad {n}", "PAD", r, c, "pad"))
    row = -(-definition.pad_count // pad_cols) if definition.pad_count else 0  # ceil division
    col = 0
    current_section: str | None = None

    for key in sorted(order, key=rank):
        section = key[1]
        if section != current_section:
            if current_section is not None:
                row += 1
            current_section = section
            col = 0
        cells.append(LayoutCell(key, labels[key], section, row, col, visual_kind_for(section, labels[key])))
        col += 1
        if col >= _COLS_PER_ROW:
            col = 0
            row += 1

    # Continuous controls are intentionally not part of the discrete MIDI
    # catalog yet, but they still deserve a visual place in a DJ layout. These
    # display-only cells make the mixer legible without pretending they have a
    # mapping; their key can never resolve to a catalog hit by accident.
    display_controls = _DISPLAY_CONTROLS.get(controller, ())
    if display_controls:
        row += 1
        col = 0
        for label, kind in display_controls:
            key = (controller, "MIXER", label)
            cells.append(LayoutCell(key, label, "MIXER", row, col, kind))
            col += 1
            if col >= _COLS_PER_ROW:
                col = 0
                row += 1

    return cells
