"""Copy one deck's mappings onto another (Qt-free).

A 4-deck Serato mapping usually repeats the same functions on every deck,
each deck on its own MIDI channel (the real fixture: deck 0 on channel 8,
1 on 10, 2 on 12, 3 on 14). :func:`plan_deck_copy` builds the copy of every
``<control>`` carrying a source-deck mapping: same note/CC on the mapped
channel, only the source deck's mapping elements, their ``deck_id`` set to
the target. Each ``<control>`` is copied one for one, so the 10x repetition
Serato needs (see CLAUDE.md) stays exactly as it was.

A trigger the target deck already uses is a *conflict*: skipped, or, with
``replace=True``, the target deck's existing mappings on it are removed
first (other decks' mappings on the same control are kept).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.model import Control, MidiConfig, iter_bindings

Trigger = tuple[str, str, str]  # (channel, event_type, control)

_SAME_DECK = QT_TRANSLATE_NOOP("DeckCopy", "Pick two different decks.")
_NO_SOURCE = QT_TRANSLATE_NOOP("DeckCopy", "Deck {deck} has no mappings to copy.")
_BAD_CHANNEL = QT_TRANSLATE_NOOP("DeckCopy", "Channel {channel} isn't a MIDI channel (1-16).")


class DeckCopyError(ValueError):
    pass


@dataclass(frozen=True)
class DeckCopyPlan:
    controls: list[Control]  # the whole new control list
    copied: tuple[Trigger, ...]  # target triggers that receive a copy
    conflicts: tuple[Trigger, ...]  # target triggers the target deck already used
    replaced: bool
    elements: int  # mapping elements written

    @property
    def skipped(self) -> tuple[Trigger, ...]:
        return () if self.replaced else self.conflicts


def _deck_elements(control: Control, deck: str):
    return [
        mapping for userio, _case in iter_bindings(control) for mapping in userio.mappings if mapping.deck_id == deck
    ]


def _keep_only(control: Control, keep) -> Control:
    """In place: every <userio> (direct or inside a <case>) keeps only the
    mapping elements `keep` accepts; emptied userios and cases are dropped,
    a kept case keeps its condition."""
    for userio, _case in iter_bindings(control):
        userio.mappings = [mapping for mapping in userio.mappings if keep(mapping)]
    control.userios = [userio for userio in control.userios if userio.mappings]
    for case in control.cases:
        case.userios = [userio for userio in case.userios if userio.mappings]
    control.cases = [case for case in control.cases if case.userios]
    return control


def _has_bindings(control: Control) -> bool:
    return bool(control.userios or control.cases)


def deck_ids(config: MidiConfig) -> list[str]:
    """Every deck id a mapping element names, numeric ones in number order."""
    found = {
        mapping.deck_id
        for control in config.controls
        for userio, _case in iter_bindings(control)
        for mapping in userio.mappings
        if mapping.deck_id is not None
    }
    return sorted(found, key=lambda deck: (not deck.isdigit(), int(deck) if deck.isdigit() else 0, deck))


def deck_channels(config: MidiConfig, deck: str) -> list[str]:
    """The MIDI channels of the controls carrying `deck`'s mappings."""
    channels = {control.channel for control in config.controls if _deck_elements(control, deck)}
    return sorted(channels, key=lambda channel: (not channel.isdigit(), int(channel) if channel.isdigit() else 0))


def default_channel_map(config: MidiConfig, source: str, target: str) -> dict[str, str]:
    """Source channel -> target channel: the target deck's own channels by
    rank when it has as many, else unchanged."""
    source_channels = deck_channels(config, source)
    target_channels = deck_channels(config, target)
    if len(target_channels) == len(source_channels):
        return dict(zip(source_channels, target_channels, strict=True))
    return {channel: channel for channel in source_channels}


def _check_channel(channel: str, translate: Translate) -> str:
    if not channel.isdigit() or not 1 <= int(channel) <= 16:
        raise DeckCopyError(translate(_BAD_CHANNEL).format(channel=channel))
    return str(int(channel))


def plan_deck_copy(
    config: MidiConfig,
    source: str,
    target: str,
    channel_map: Mapping[str, str] | None = None,
    *,
    replace: bool = False,
    translate: Translate = untranslated,
) -> DeckCopyPlan:
    if source == target:
        raise DeckCopyError(translate(_SAME_DECK))
    channel_map = dict(channel_map or default_channel_map(config, source, target))
    sources = [control for control in config.controls if _deck_elements(control, source)]
    if not sources:
        raise DeckCopyError(translate(_NO_SOURCE).format(deck=source))

    def target_trigger(control: Control) -> Trigger:
        channel = _check_channel(channel_map.get(control.channel, control.channel), translate)
        return (channel, control.event_type, control.control)

    wanted = list(dict.fromkeys(target_trigger(control) for control in sources))
    used = {
        (control.channel, control.event_type, control.control)
        for control in config.controls
        if _deck_elements(control, target)
    }
    conflicts = tuple(trigger for trigger in wanted if trigger in used)
    blocked = set() if replace else set(conflicts)
    cleared = set(conflicts) if replace else set()

    controls: list[Control] = []
    for control in config.controls:
        if (control.channel, control.event_type, control.control) not in cleared:
            controls.append(control)
            continue
        kept = _keep_only(copy.deepcopy(control), lambda mapping: mapping.deck_id != target)
        if _has_bindings(kept):
            controls.append(kept)

    elements = 0
    copied: list[Trigger] = []
    for control in sources:
        trigger = target_trigger(control)
        if trigger in blocked:
            continue
        duplicate = _keep_only(copy.deepcopy(control), lambda mapping: mapping.deck_id == source)
        duplicate.channel = trigger[0]
        for userio, _case in iter_bindings(duplicate):
            for mapping in userio.mappings:
                mapping.deck_id = target
            elements += len(userio.mappings)
        controls.append(duplicate)
        copied.append(trigger)
    return DeckCopyPlan(
        controls=controls,
        copied=tuple(dict.fromkeys(copied)),
        conflicts=conflicts,
        replaced=replace,
        elements=elements,
    )


__all__ = [
    "DeckCopyError",
    "DeckCopyPlan",
    "deck_channels",
    "deck_ids",
    "default_channel_map",
    "plan_deck_copy",
]
