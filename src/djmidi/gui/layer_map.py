"""Layered mapping overview: for one controller, what each physical control
does in every layer -- normal, +SHIFT, each pad-mode bank -- side by side,
with the free (unmapped) combinations marked so a DJ sees where a new
function fits (issue #253).

Qt-free, like gui/cheat_sheet.py whose function index it reuses, so the
resolution is tested without a QApplication; gui/layer_map_dialog.py draws
the result. Read-only: derived from the loaded mapping plus
layout.reverse_lookup(), never from fabricated MIDI data -- a layer only
exists here because the controller's own catalog names a variant for it.

A row is one schematic cell (layout.cell_key): every deck's copy of a pad
collapses to one "Pad 3" row, and a button to one row with its +SHIFT /
long-press variants, so a cell lists every deck layer that shares the
physical control ("Hot cue · slot 3 (D1, D3)"). A cell is *free* when none
of its raw triggers is mapped, *partial* when only some are (e.g. pad 3 of
PAD MODE 2 mapped on deck 1 but not decks 2-4) -- both count as room for a
new function, and `free_triggers` says exactly which channels are left.

Layers come from the variant names alone: the pad bank in parentheses after
"Pad N" (cheat_sheet._BANK_RE: "(PAD MODE 2)", "(HOT CUE mode)",
"(SCENE 1)"), a SHIFT marker anywhere, and for other controls whatever
qualifier layout._base_name() strips ("(long press)", "(press twice)", ...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from djmidi import catalog
from djmidi.gui import layout as layout_mod
from djmidi.gui.cheat_sheet import (
    _BANK_RE,
    _EVENT_TYPE_FOR_KIND,
    FunctionIndex,
    build_function_index,
    format_functions,
    is_shift,
)
from djmidi.i18n import Translate, untranslated
from djmidi.model import MidiConfig

NORMAL = "Normal"
SHIFT = "SHIFT"

STATUS_MAPPED = "mapped"
STATUS_PARTIAL = "partial"
STATUS_FREE = "free"

# Output-only entries (LED feedback) are not a place to put a function.
_OUTPUT_ONLY_SECTIONS = frozenset({"MIDI-OUT"})
_SHIFT_RE = re.compile(r"\s*\(?\+\s*SHIFT\)?", re.IGNORECASE)
_PAD_NUMBER_RE = re.compile(r"(\d+)$")

Trigger = tuple[str, str, str]  # (channel, event_type, data1), model.Control's convention


def _bank(variant: catalog.ControlInfo) -> str:
    """The pad bank a variant belongs to, without parentheses, or ""."""
    if variant.section != "PAD":
        return ""
    match = _BANK_RE.search(variant.name)
    return match.group(1)[1:-1].strip() if match else ""


def _qualifier(variant: catalog.ControlInfo) -> str:
    """A non-pad variant's qualifier minus any SHIFT marker ("long press",
    "direct button"), or ""."""
    if variant.section == "PAD":
        return ""
    suffix = variant.name[len(layout_mod._base_name(variant.name)) :]
    text = _SHIFT_RE.sub("", suffix).strip().strip("()").strip(" ,")
    # DDJ-XP2's "Rotary Selector (+SHIFT press)" is just the SHIFT layer.
    return "" if text == "press" else text


def layer_of(variant: catalog.ControlInfo) -> str:
    """The layer column a catalog variant belongs to: "Normal", "SHIFT",
    "PAD MODE 2", "PAD MODE 2 + SHIFT", "long press", ..."""
    base = _bank(variant) or _qualifier(variant)
    if is_shift(variant):
        return f"{base} + {SHIFT}" if base else SHIFT
    return base or NORMAL


@dataclass(frozen=True)
class LayerCell:
    """One (control, layer) combination. `functions` are display lines
    ("Play (D1, D2)"); `free_triggers` lists every raw trigger of this
    combination the mapping leaves unbound."""

    layer: str
    variants: tuple[catalog.ControlInfo, ...]
    functions: tuple[str, ...]
    triggers: tuple[Trigger, ...]
    free_triggers: tuple[Trigger, ...]

    @property
    def status(self) -> str:
        if not self.free_triggers:
            return STATUS_MAPPED
        if len(self.free_triggers) < len(self.triggers):
            return STATUS_PARTIAL
        return STATUS_FREE


@dataclass(frozen=True)
class LayerRow:
    section: str
    control: str
    cells: dict[str, LayerCell] = field(default_factory=dict)
    """Layer name -> cell; a layer missing here doesn't exist for this
    control (a button has no pad bank)."""

    @property
    def is_mapped(self) -> bool:
        return any(cell.functions for cell in self.cells.values())


@dataclass(frozen=True)
class LayerMap:
    controller: str
    layers: tuple[str, ...]
    rows: tuple[LayerRow, ...]

    def sections(self) -> list[str]:
        return list(dict.fromkeys(row.section for row in self.rows))

    def count(self, status: str) -> int:
        return sum(1 for row in self.rows for cell in row.cells.values() if cell.status == status)


def _triggers(variants: list[catalog.ControlInfo]) -> list[Trigger]:
    triggers: list[Trigger] = []
    for variant in variants:
        event_type = _EVENT_TYPE_FOR_KIND[variant.note_or_cc]
        for channel in variant.channels:
            trigger = (channel, event_type, variant.data1)
            if trigger not in triggers:
                triggers.append(trigger)
    return triggers


def _cell(layer: str, variants: list[catalog.ControlInfo], index: FunctionIndex) -> LayerCell:
    triggers = _triggers(variants)
    lines: list[tuple[str, str]] = []
    free: list[Trigger] = []
    for trigger in triggers:
        bound = index.get(trigger, [])
        if not bound:
            free.append(trigger)
        lines.extend(line for line in bound if line not in lines)
    return LayerCell(layer, tuple(variants), tuple(format_functions(lines)), tuple(triggers), tuple(free))


def _layer_rank(layers: list[str], banks: list[str], qualifiers: list[str]) -> list[str]:
    """Normal, SHIFT, the other qualifiers (each plain then + SHIFT), then
    every pad bank in reverse_lookup() order (each plain then + SHIFT)."""

    def rank(layer: str) -> tuple[int, int, int]:
        shifted = layer == SHIFT or layer.endswith(f" + {SHIFT}")
        base = "" if layer in (NORMAL, SHIFT) else layer.removesuffix(f" + {SHIFT}")
        if base in banks:
            return (2, banks.index(base), int(shifted))
        if not base:
            return (0, 0, int(shifted))
        return (1, qualifiers.index(base) if base in qualifiers else len(qualifiers), int(shifted))

    return sorted(layers, key=rank)


def _row_rank(controller: str, keys: list[layout_mod.CellKey]) -> list[layout_mod.CellKey]:
    """Pads first, by number (as layout.build_layout leads with them), then
    the controller's section_order, then first-seen order."""
    section_order = list(catalog.get_definition(controller).section_order)
    first_seen = {key: index for index, key in enumerate(keys)}

    def rank(key: layout_mod.CellKey) -> tuple[int, int, int]:
        section, label = key[1], key[2]
        if section == "PAD":
            match = _PAD_NUMBER_RE.search(label)
            return (0, 0, int(match.group(1)) if match else first_seen[key])
        section_rank = section_order.index(section) if section in section_order else len(section_order)
        return (1, section_rank, first_seen[key])

    return sorted(keys, key=rank)


def build_layer_map(
    config: MidiConfig | None, controller: str, translate: Translate = untranslated
) -> LayerMap:
    """The layer overview of `controller` for `config` (None = an empty
    mapping: every combination free). `translate` (the "FunctionNames"
    context) puts the functions' slot suffix in the interface language."""
    index: FunctionIndex = build_function_index(config, translate) if config is not None else {}
    lookup = layout_mod.reverse_lookup(controller)
    keys = [key for key in lookup if key[1] not in _OUTPUT_ONLY_SECTIONS]
    qualifiers: list[str] = []
    seen_layers: list[str] = []
    rows: list[LayerRow] = []
    for key in _row_rank(controller, keys):
        by_layer: dict[str, list[catalog.ControlInfo]] = {}
        for variant in lookup[key]:
            layer = layer_of(variant)
            by_layer.setdefault(layer, []).append(variant)
            if (qualifier := _qualifier(variant)) and qualifier not in qualifiers:
                qualifiers.append(qualifier)
            if layer not in seen_layers:
                seen_layers.append(layer)
        cells = {layer: _cell(layer, variants, index) for layer, variants in by_layer.items()}
        rows.append(LayerRow(key[1], key[2], cells))
    # Pad banks keep reverse_lookup()'s lowest-bank-first order, not the
    # pad-number-sorted row order the loop above saw them in.
    return LayerMap(controller, tuple(_layer_rank(seen_layers, _all_banks(lookup), qualifiers)), tuple(rows))


def _all_banks(lookup: dict[layout_mod.CellKey, list[catalog.ControlInfo]]) -> list[str]:
    banks: list[str] = []
    for key, variants in lookup.items():
        if key[1] != "PAD":
            continue
        for variant in variants:
            if (bank := _bank(variant)) and bank not in banks:
                banks.append(bank)
    return banks


def describe_trigger(trigger: Trigger) -> str:
    """"ch 9 · Note 18" -- a raw trigger as the tooltip of a free cell
    lists it."""
    channel, event_type, data1 = trigger
    kind = "Note" if "note" in event_type.casefold() else "CC"
    return f"ch {channel} · {kind} {data1}"


__all__ = [
    "NORMAL",
    "SHIFT",
    "STATUS_FREE",
    "STATUS_MAPPED",
    "STATUS_PARTIAL",
    "LayerCell",
    "LayerMap",
    "LayerRow",
    "build_layer_map",
    "describe_trigger",
    "is_shift",
    "layer_of",
]
