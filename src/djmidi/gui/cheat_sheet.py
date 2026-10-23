"""Printable mapping cheat sheet: which function the loaded mapping binds
to each physical control (issue #182).

Qt-free, like gui/layout.py and gui/geometry.py, so the resolution is
tested without a QApplication; gui/cheat_sheet_pdf.py draws the result.

A controller with gui/geometry.CONTROL_GEOMETRY gets *photo* sheets: one
per pad bank the mapping actually uses (the first also carries every
non-pad control), each marker resolved the way the Controller Emulator's
dry-run does -- through layout.reverse_lookup(), narrowed to the marker's
physical side ("Pad 3 (R)" = decks 2/4) and to the sheet's pad-bank
token. Unlike the emulator, which acts on one variant per click, a sheet
lists every deck layer sharing a physical control (left pads = decks 1
and 3) and the SHIFT variant too, since a printed page has no state to
pick one. Mapped catalog entries no marker shows (or every entry, for a
controller with no geometry) go to a *table* sheet: section / control /
function.

Which controllers a mapping is "for" can't be inferred from the file
alone: on the real 4-deck fixture the same 64 triggers resolve on DDJ-XP2,
DDJ-1000, DDJ-FLX10 and DDJ-800 alike. candidate_controllers() therefore
only ranks the possibilities; the caller (the export dialog) lets the user
choose.

Functions print under their readable name (djmidi.function_names, issue
#209: "Loop roll · slot 3"); since paper has no tooltip, a final "Function
names" table sheet lists each readable name used with the raw tag it stands
for.

Page titles and the glossary's words are marked with
QT_TRANSLATE_NOOP("CheatSheet", ...) and go through build_sheets()'s
optional `labels` translator (English by default): the printed sheet is for
the DJ, so it follows the interface language (issue #333)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from djmidi import catalog
from djmidi.function_names import FUNCTION_NAMES, function_label
from djmidi.gui import geometry as geometry_mod
from djmidi.gui import layout as layout_mod
from djmidi.gui.mapping_group import build_mapping_groups
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.model import MidiConfig

_EVENT_TYPE_FOR_KIND: dict[catalog.NoteOrCC, str] = {
    "NOTE": "Note On",
    "CC": "Control Change",
}
_RIGHT = layout_mod._RIGHT_GRID_SUFFIX
# The pad-bank regex and the SHIFT / plain rules live in gui/layout.py so
# pick_default_variant() applies the same ones (issue #288).
_BANK_RE = layout_mod.PAD_BANK_RE

Trigger = tuple[
    str, str, str
]  # (channel, event_type, data1), model.Control's convention
FunctionIndex = dict[Trigger, list[tuple[str, str]]]  # -> [(deck label, function text)]


@dataclass(frozen=True)
class SheetEntry:
    """One mapped control: `functions` are display lines, SHIFT ones
    prefixed "SHIFT: ". `geometry` is None for a table row."""

    section: str
    control: str
    functions: tuple[str, ...]
    geometry: geometry_mod.ControlGeometry | None = None


@dataclass(frozen=True)
class Sheet:
    controller: str
    title: str
    kind: str  # "photo" or "table"
    entries: tuple[SheetEntry, ...] = field(default_factory=tuple)
    # Every geometry marker's box, mapped or not, so the renderer can show
    # the unmapped ones as empty outlines.
    unmapped: tuple[geometry_mod.ControlGeometry, ...] = field(default_factory=tuple)


GLOSSARY_TITLE = QT_TRANSLATE_NOOP("CheatSheet", "Function names")
_GLOSSARY_SECTION = QT_TRANSLATE_NOOP("CheatSheet", "Name")
_GLOSSARY_TAG = QT_TRANSLATE_NOOP("CheatSheet", "Serato tag: {tag}")
_TITLE_TABLE = QT_TRANSLATE_NOOP("CheatSheet", "{controller} — mapped controls")
_TITLE_BANK = QT_TRANSLATE_NOOP("CheatSheet", "{controller} — pads {bank}")
_TITLE_REST = QT_TRANSLATE_NOOP("CheatSheet", "{controller} — other mapped controls")


def function_text(tag: str, slot_id: str, translate: Translate = untranslated) -> str:
    """A Serato/Traktor function as printed: its readable name with the
    slot when the mapping element has one ("Auto loop · slot 8"), or the raw
    tag for a tag djmidi.function_names doesn't know. `translate` (the
    "FunctionNames" context) puts the slot suffix in the interface language
    (issue #331)."""
    return function_label(tag, slot_id, translate)


def deck_label(deck_id: str) -> str:
    """Serato's 0-indexed deck_id as the 1-indexed deck a DJ reads ("0" ->
    "D1"; same off-by-one layout.right_side_usage_deck_ids documents), or
    "" when the element carries no numeric deck."""
    return f"D{int(deck_id) + 1}" if deck_id.isdigit() else ""


def build_function_index(config: MidiConfig, translate: Translate = untranslated) -> FunctionIndex:
    """(channel, event_type, data1) -> every (deck, function) its input
    ("click") mapping elements bind it to, de-duplicated -- the 10x
    duplicate elements of a real Serato file collapse to one line."""
    index: FunctionIndex = {}
    for group in build_mapping_groups(config):
        if group.event != "click":
            continue
        line = (deck_label(group.deck_id), function_text(group.tag, group.slot_id, translate))
        lines = index.setdefault(
            (group.channel, group.event_type, group.control_no), []
        )
        if line not in lines:
            lines.append(line)
    return index


def candidate_controllers(
    config: MidiConfig, controllers: list[str] | None = None
) -> list[tuple[str, int]]:
    """Every registered controller (or every one in `controllers`) that
    resolves at least one of the mapping's distinct triggers, with that
    count, most matches first (registry order breaks ties)."""
    names = list(catalog.CONTROLLER_NAMES) if controllers is None else controllers
    triggers = {(c.channel, c.event_type, c.control) for c in config.controls}
    counts: Counter[str] = Counter()
    for trigger in triggers:
        for name in {hit.controller for hit in catalog.lookup(*trigger)}:
            counts[name] += 1
    ranked = [(name, counts[name]) for name in names if counts[name]]
    return sorted(ranked, key=lambda item: -item[1])


def _functions_for(
    entry: catalog.ControlInfo, index: FunctionIndex
) -> list[tuple[str, str]]:
    event_type = _EVENT_TYPE_FOR_KIND[entry.note_or_cc]
    lines: list[tuple[str, str]] = []
    for channel in entry.channels:
        for line in index.get((channel, event_type, entry.data1), []):
            if line not in lines:
                lines.append(line)
    return lines


def format_functions(lines: list[tuple[str, str]], prefix: str = "") -> list[str]:
    """Group (deck, function) pairs by function: "play (D1, D3)" rather than
    one line per deck layer when they agree."""
    decks_by_function: dict[str, list[str]] = {}
    for deck, function in lines:
        decks = decks_by_function.setdefault(function, [])
        if deck and deck not in decks:
            decks.append(deck)
    return [
        f"{prefix}{function} ({', '.join(decks)})" if decks else f"{prefix}{function}"
        for function, decks in decks_by_function.items()
    ]


_name_without_bank = layout_mod.name_without_bank
is_shift = layout_mod.is_shift_variant  # shared with gui/layer_map.py
_is_plain = layout_mod.is_plain_variant


def pad_banks(controller: str) -> list[str]:
    """The pad-bank tokens ("(PAD MODE 1)", "(HOT CUE mode)", ...) of a
    controller's pad variants, in reverse_lookup() order (lowest bank
    first); empty when its pads carry no bank."""
    banks: list[str] = []
    for key, variants in layout_mod.reverse_lookup(controller).items():
        if key[1] != "PAD":
            continue
        for variant in variants:
            match = _BANK_RE.search(variant.name)
            if match and match.group(1) not in banks:
                banks.append(match.group(1))
    return banks


def marker_variants(
    controller: str, label: str, bank: str | None = None
) -> list[catalog.ControlInfo]:
    """Every real catalog variant a geometry marker `label` stands for on
    its own physical side, restricted to `bank` when it's a pad and the
    bank matches -- the multi-variant counterpart of
    layout.resolve_side_aware_variant(). A combined label ("PAD MODE 1/5")
    contributes each alternative's variants; a side-bundled entry (one
    catalog entry spanning both sides' channels) is narrowed to this
    side's channels."""
    merged = layout_mod.cell_key_for_geometry_label(controller, label)
    if merged is None:
        return []  # display-only marker (jog wheel, tempo fader): no trigger
    section = merged[1]
    right_side = label.endswith(_RIGHT)
    base = label.removesuffix(_RIGHT)
    lookup = layout_mod.reverse_lookup(controller)
    side_channels = layout_mod._RIGHT_SIDE_CHANNELS.get(controller, {}).get(section)
    result: list[catalog.ControlInfo] = []
    for alternative in layout_mod._geometry_label_alternatives(base):
        variants = lookup.get((controller, section, alternative), [])
        if (
            alternative == layout_mod._geometry_label_alternatives(base)[0]
            and not variants
        ):
            variants = lookup.get(merged, [])
        if section == "PAD":
            variants = [
                v
                for v in variants
                if layout_mod.hit_matches_side(controller, section, v, right_side)
            ]
            if bank is not None:
                in_bank = [v for v in variants if bank.casefold() in v.name.casefold()]
                if in_bank:
                    variants = in_bank
        elif side_channels:
            narrowed = []
            for variant in variants:
                channels = tuple(
                    ch for ch in variant.channels if (ch in side_channels) == right_side
                )
                if channels:
                    narrowed.append(replace(variant, channels=channels))
            variants = narrowed
        result.extend(v for v in variants if v not in result)
    return result


def _marker_functions(
    variants: list[catalog.ControlInfo], index: FunctionIndex
) -> list[str]:
    plain = [v for v in variants if _is_plain(v)] or [
        v for v in variants if not is_shift(v)
    ]
    shifted = [v for v in variants if is_shift(v)]
    plain_lines: list[tuple[str, str]] = []
    for variant in plain:
        plain_lines.extend(
            line for line in _functions_for(variant, index) if line not in plain_lines
        )
    shift_lines: list[tuple[str, str]] = []
    for variant in shifted:
        shift_lines.extend(
            line for line in _functions_for(variant, index) if line not in shift_lines
        )
    return format_functions(plain_lines) + format_functions(shift_lines, "SHIFT: ")


def _covered(variants: list[catalog.ControlInfo]) -> set[tuple[str, str, str]]:
    return {(v.name, ch, v.data1) for v in variants for ch in v.channels}


def _table_entries(
    controller: str, index: FunctionIndex, covered: set[tuple[str, str, str]]
) -> list[SheetEntry]:
    """Every mapped catalog variant of `controller` not already in
    `covered`, one row per variant, in reverse_lookup() order."""
    entries: list[SheetEntry] = []
    seen: set[catalog.ControlInfo] = set()
    for variants in layout_mod.reverse_lookup(controller).values():
        for variant in variants:
            if variant in seen:
                continue
            seen.add(variant)
            channels = tuple(
                ch
                for ch in variant.channels
                if (variant.name, ch, variant.data1) not in covered
            )
            if not channels:
                continue
            lines = format_functions(
                _functions_for(replace(variant, channels=channels), index)
            )
            if lines:
                entries.append(SheetEntry(variant.section, variant.name, tuple(lines)))
    return entries


def glossary_sheet(config: MidiConfig, labels: Translate = untranslated) -> Sheet | None:
    """A table of every readable function name the mapping's input
    elements use, next to its raw tag -- the printed stand-in for the
    tooltips the app shows. None when every function prints raw anyway.
    `labels` translates the "CheatSheet" words."""
    tags = sorted(
        {group.tag for group in build_mapping_groups(config) if group.event == "click" and group.tag in FUNCTION_NAMES},
        key=lambda tag: FUNCTION_NAMES[tag],
    )
    if not tags:
        return None
    section = labels(_GLOSSARY_SECTION)
    entries = tuple(
        SheetEntry(section, FUNCTION_NAMES[tag], (labels(_GLOSSARY_TAG).format(tag=tag),)) for tag in tags
    )
    return Sheet("", labels(GLOSSARY_TITLE), "table", entries)


def build_sheets(
    config: MidiConfig,
    controllers: list[str],
    translate: Translate = untranslated,
    labels: Translate = untranslated,
) -> list[Sheet]:
    """The cheat sheet's logical pages for `controllers`, in that order.

    Per controller with geometry: one photo sheet for the first pad bank
    with a mapped pad (or the first bank, or no bank), carrying every
    marker; one more pad-only photo sheet per further mapped bank; then a
    table sheet of whatever mapped entries no marker showed, if any.
    Without geometry: a single table sheet (even an empty one, so every
    chosen controller gets a page). Last, the glossary_sheet() when any
    function prints under a readable name. `translate` is passed to
    function_text(); `labels` (the "CheatSheet" context) translates the page
    titles and the glossary."""
    index = build_function_index(config, translate)
    sheets: list[Sheet] = []
    for controller in controllers:
        geometry = geometry_mod.CONTROL_GEOMETRY.get(controller)
        if not geometry:
            sheets.append(
                Sheet(
                    controller,
                    labels(_TITLE_TABLE).format(controller=controller),
                    "table",
                    tuple(_table_entries(controller, index, set())),
                )
            )
            continue
        pad_labels = [
            label
            for label in geometry
            if (key := layout_mod.cell_key_for_geometry_label(controller, label))
            is not None
            and key[1] == "PAD"
        ]
        banks = pad_banks(controller)
        mapped_banks = [
            bank
            for bank in banks
            if any(
                _marker_functions(marker_variants(controller, label, bank), index)
                for label in pad_labels
            )
        ]
        pages: list[str | None] = mapped_banks or (banks[:1] or [None])
        covered: set[tuple[str, str, str]] = set()
        for number, bank in enumerate(pages):
            entries: list[SheetEntry] = []
            unmapped: list[geometry_mod.ControlGeometry] = []
            for label, geom in geometry.items():
                if number > 0 and label not in pad_labels:
                    continue
                variants = marker_variants(controller, label, bank)
                lines = _marker_functions(variants, index)
                if lines:
                    covered |= _covered(variants)
                    entries.append(
                        SheetEntry(variants[0].section, label, tuple(lines), geom)
                    )
                else:
                    unmapped.append(geom)
            title = labels(_TITLE_BANK).format(controller=controller, bank=bank.strip("()")) if bank else controller
            sheets.append(
                Sheet(
                    controller,
                    title,
                    "photo",
                    tuple(entries),
                    tuple(unmapped),
                )
            )
        rest = _table_entries(controller, index, covered)
        if rest:
            sheets.append(
                Sheet(
                    controller,
                    labels(_TITLE_REST).format(controller=controller),
                    "table",
                    tuple(rest),
                )
            )
    if controllers and (glossary := glossary_sheet(config, labels)) is not None:
        sheets.append(glossary)
    return sheets


__all__ = [
    "Sheet",
    "SheetEntry",
    "build_function_index",
    "build_sheets",
    "candidate_controllers",
    "deck_label",
    "format_functions",
    "function_text",
    "glossary_sheet",
    "is_shift",
    "marker_variants",
    "pad_banks",
]
