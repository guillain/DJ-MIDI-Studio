"""Semantic diff between two mappings (issue #189).

Compares two `MidiConfig`s by what each MIDI trigger *does* rather than by
their XML text: a raw text diff of two real Serato files is unreadable (16k+
lines, every trigger repeated 10 times), and a reordered file would look
entirely different while meaning the same thing.

Both sides are reduced to a multiset keyed by trigger
`(channel, event_type, control, userio event)` and function
`(tag, deck_set, deck_id, slot_id)`, whose values count each distinct
translation/alias signature. That is what makes Serato's load-bearing 10x
duplication (see CLAUDE.md) diff cleanly: ten identical copies on both sides
compare equal, and a file that lost one copy reports a single `duplicates`
entry ("x10 -> x9") instead of nine spurious adds or removes.

Entry kinds, one entry per trigger for the first three and one per function
for the last two:

- `added`: functions on a trigger that only the new side binds at all, or
  extra functions on a trigger that keeps every old one;
- `removed`: the reverse;
- `reassigned`: a trigger that lost some functions and gained others (the
  "trigger -> function" change the issue asks for);
- `changed`: the same function on the same trigger with different
  translation/alias values (e.g. `behaviour` toggle -> explicit);
- `duplicates`: identical content, different number of copies.

`Control.extra_attrs` is deliberately ignored: for Traktor it holds the
binding's position in the `.tsi` blob, which says nothing about behaviour.
Functions are named with `function_names` ("Codfather ST (deck 3, slot 1)");
each entry also keeps the raw-tag wording (`old_raw`/`new_raw`,
`raw_summary()`) for the dialog's tooltip, and entries sort on the raw tag so
the order doesn't depend on the label table.

Qt-free; the GUI's comparison dialog only renders `MappingDiff.entries`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from djmidi.function_names import function_name
from djmidi.model import MappingElement, MidiConfig, Translation

KINDS = ("reassigned", "added", "removed", "changed", "duplicates")
KIND_LABELS = {
    "reassigned": "Re-assigned",
    "added": "Added",
    "removed": "Removed",
    "changed": "Changed values",
    "duplicates": "Duplicate count",
}

Trigger = tuple[str, str, str, str]
FunctionKey = tuple[str, str | None, str | None, str | None]
# (element extra attrs, translations), every part hashable and order-stable.
Signature = tuple

_Index = dict[Trigger, dict[FunctionKey, Counter]]


@dataclass(frozen=True)
class DiffEntry:
    kind: str
    channel: str
    event_type: str
    control: str
    event: str
    old_functions: tuple[str, ...] = ()
    new_functions: tuple[str, ...] = ()
    details: tuple[str, ...] = ()
    # The same functions with their raw Serato/Traktor tag, aligned with
    # old_functions/new_functions.
    old_raw: tuple[str, ...] = ()
    new_raw: tuple[str, ...] = ()

    @property
    def trigger(self) -> tuple[str, str, str]:
        """The raw `(channel, event_type, control)` -- what `catalog.lookup`
        and the layout views take."""
        return (self.channel, self.event_type, self.control)

    def summary(self) -> str:
        """One readable line: what the trigger did, and what it does now."""
        return self._summarize(self.old_functions, self.new_functions)

    def raw_summary(self) -> str:
        """`summary()` with the raw function tags instead of readable names."""
        return self._summarize(self.old_raw or self.old_functions, self.new_raw or self.new_functions)

    def _summarize(self, old_functions: tuple[str, ...], new_functions: tuple[str, ...]) -> str:
        old = ", ".join(old_functions)
        new = ", ".join(new_functions)
        if self.kind == "reassigned":
            return f"{old} -> {new}"
        if self.kind == "added":
            return new
        if self.kind == "removed":
            return old
        label = new or old
        return f"{label}: {'; '.join(self.details)}" if self.details else label


@dataclass
class MappingDiff:
    entries: list[DiffEntry] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.entries

    def by_kind(self, kind: str) -> list[DiffEntry]:
        return [entry for entry in self.entries if entry.kind == kind]

    def counts(self) -> dict[str, int]:
        return {kind: len(self.by_kind(kind)) for kind in KINDS}


def function_label(key: FunctionKey, raw: bool = False) -> str:
    """`Auto loop (deck 3, slot 8)`, or with `raw` the tag itself
    (`auto_loop_specific_length (deck 3, slot 8)`); a non-default deck set is
    named too, since Serato keeps one binding per set."""
    tag, deck_set, deck_id, slot_id = key
    name = tag if raw else function_name(tag)
    parts = []
    if deck_set and deck_set != "Default":
        parts.append(f"set {deck_set}")
    if deck_id:
        parts.append(f"deck {deck_id}")
    if slot_id:
        parts.append(f"slot {slot_id}")
    return f"{name} ({', '.join(parts)})" if parts else name


def _raw_label(key: FunctionKey) -> str:
    return function_label(key, raw=True)


def _attrs(attrs: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(attrs.items()))


def _translation_signature(translation: Translation) -> tuple:
    return (
        translation.action_on,
        translation.behaviour,
        tuple((alias.name, alias.value, _attrs(alias.extra_attrs)) for alias in translation.aliases),
        _attrs(translation.extra_attrs),
    )


def _signature(element: MappingElement) -> Signature:
    return (_attrs(element.extra_attrs), tuple(_translation_signature(t) for t in element.translations))


def _index(config: MidiConfig) -> _Index:
    index: _Index = defaultdict(lambda: defaultdict(Counter))
    for control in config.controls:
        for userio in control.userios:
            trigger = (control.channel, control.event_type, control.control, userio.event)
            for element in userio.mappings:
                key = (element.tag, element.deck_set, element.deck_id, element.slot_id)
                index[trigger][key][_signature(element)] += 1
    return index


def _sort_key(entry: DiffEntry) -> tuple:
    def number(text: str) -> tuple[int, str]:
        return (int(text), "") if text.isdigit() else (10**9, text)

    return (KINDS.index(entry.kind), number(entry.channel), entry.event_type, number(entry.control), entry.event)


def _describe_translation_change(position: str, old: tuple | None, new: tuple | None) -> list[str]:
    if old is None:
        return [f"{position or 'translation '}added"]
    if new is None:
        return [f"{position or 'translation '}removed"]
    lines = []
    for name, before, after in (("action_on", old[0], new[0]), ("behaviour", old[1], new[1])):
        if before != after:
            lines.append(f"{position}{name}: {before or '-'} -> {after or '-'}")
    old_aliases = {name: value for name, value, _extra in old[2]}
    new_aliases = {name: value for name, value, _extra in new[2]}
    for name in sorted(old_aliases.keys() | new_aliases.keys()):
        before, after = old_aliases.get(name), new_aliases.get(name)
        if before != after:
            lines.append(f"{position}alias {name}: {before or '-'} -> {after or '-'}")
    if old[2] != new[2] and old_aliases == new_aliases:
        lines.append(f"{position}alias order or attributes changed")
    if old[3] != new[3]:
        lines.append(f"{position}translation attributes changed")
    return lines


def describe_signature_change(old: Signature, new: Signature) -> list[str]:
    """Readable field-level differences between two signatures of one function."""
    lines = []
    old_attrs, new_attrs = dict(old[0]), dict(new[0])
    for name in sorted(old_attrs.keys() | new_attrs.keys()):
        if old_attrs.get(name) != new_attrs.get(name):
            lines.append(f"{name}: {old_attrs.get(name) or '-'} -> {new_attrs.get(name) or '-'}")
    old_translations, new_translations = old[1], new[1]
    many = max(len(old_translations), len(new_translations)) > 1
    for position in range(max(len(old_translations), len(new_translations))):
        prefix = f"translation {position + 1} " if many else ""
        before = old_translations[position] if position < len(old_translations) else None
        after = new_translations[position] if position < len(new_translations) else None
        if before != after:
            lines.extend(_describe_translation_change(prefix, before, after))
    return lines or ["values changed"]


def _changed_details(old: Counter, new: Counter) -> list[str]:
    """Field-level details when one variant replaced another. A variant added
    next to the old one (only some of the duplicated copies edited) is
    compared with the old copies' most common variant, and says how many
    copies carry it."""
    old_only = [sig for sig in old if sig not in new]
    new_only = [sig for sig in new if sig not in old]
    before = old_only[0] if len(old_only) == 1 else (old.most_common(1)[0][0] if not old_only else None)
    after = new_only[0] if len(new_only) == 1 else (new.most_common(1)[0][0] if not new_only else None)
    old_total, new_total = sum(old.values()), sum(new.values())
    if before is None or after is None:
        details = [f"{len(old)} distinct value set(s) -> {len(new)}"]
    else:
        details = describe_signature_change(before, after)
        if not old_only:
            details.append(f"on {sum(new[sig] for sig in new_only)} of {new_total} copies")
        elif not new_only:
            details.append(f"{sum(old[sig] for sig in old_only)} of {old_total} copies reverted")
    if old_total != new_total:
        details.append(f"copies: x{old_total} -> x{new_total}")
    return details


def diff_configs(old: MidiConfig, new: MidiConfig) -> MappingDiff:
    """What changed going from `old` to `new` (e.g. the `.bak` to the current
    file), sorted by kind and then trigger."""
    old_index, new_index = _index(old), _index(new)
    entries: list[DiffEntry] = []
    for trigger in old_index.keys() | new_index.keys():
        before = old_index.get(trigger, {})
        after = new_index.get(trigger, {})
        lost = sorted((key for key in before if key not in after), key=_raw_label)
        gained = sorted((key for key in after if key not in before), key=_raw_label)
        common = {
            "channel": trigger[0],
            "event_type": trigger[1],
            "control": trigger[2],
            "event": trigger[3],
        }
        old_labels = tuple(function_label(key) for key in lost)
        new_labels = tuple(function_label(key) for key in gained)
        old_raw = tuple(_raw_label(key) for key in lost)
        new_raw = tuple(_raw_label(key) for key in gained)
        if lost and gained:
            entries.append(
                DiffEntry(
                    "reassigned",
                    **common,
                    old_functions=old_labels,
                    new_functions=new_labels,
                    old_raw=old_raw,
                    new_raw=new_raw,
                )
            )
        elif gained:
            entries.append(DiffEntry("added", **common, new_functions=new_labels, new_raw=new_raw))
        elif lost:
            entries.append(DiffEntry("removed", **common, old_functions=old_labels, old_raw=old_raw))
        for key in sorted((k for k in before if k in after), key=_raw_label):
            old_counter, new_counter = before[key], after[key]
            label = (function_label(key),)
            raw = (_raw_label(key),)
            if set(old_counter) != set(new_counter):
                details = tuple(_changed_details(old_counter, new_counter))
                entries.append(
                    DiffEntry(
                        "changed",
                        **common,
                        old_functions=label,
                        new_functions=label,
                        details=details,
                        old_raw=raw,
                        new_raw=raw,
                    )
                )
            elif old_counter != new_counter:
                old_total, new_total = sum(old_counter.values()), sum(new_counter.values())
                detail = f"copies: x{old_total} -> x{new_total}" if old_total != new_total else "copy mix changed"
                entries.append(
                    DiffEntry(
                        "duplicates",
                        **common,
                        old_functions=label,
                        new_functions=label,
                        details=(detail,),
                        old_raw=raw,
                        new_raw=raw,
                    )
                )
    entries.sort(key=_sort_key)
    return MappingDiff(entries)
