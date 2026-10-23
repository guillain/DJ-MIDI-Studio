"""Reverse search over a loaded mapping (issue #185): "which control triggers
function X?".

The tree tabs answer the forward question (this button -> which functions);
this answers the other one. Every (function tag, deck, slot, userio event)
in the file becomes one `FunctionResult` listing the distinct raw triggers
bound to it -- Serato's ~10 verbatim duplicates of a trigger (see CLAUDE.md's
"10x duplication" finding) collapse into one trigger here, the same way the
By Deck tab's MappingGroup collapses them.

Matching is tokenized and case-insensitive: a tag is read with its
underscores as spaces (`auto_loop_roll_specific_length` -> "auto loop roll
specific length"), and every query token must match something:

- a word of the tag (exact beats prefix beats a substring of the whole tag),
- `deck N` / `slot N` pin the result's deck/slot id exactly (ids are shown
  as the file stores them, the same "Deck 0" the By Deck tab displays),
- a bare number matches the deck or slot id (or a number inside the tag),
- `click` / `output` (or `led`) match the userio event.

French keywords work alongside the English ones whatever the interface
language (issue #326): `platine N` = `deck N`, `emplacement N` = `slot N`,
`clic` / `appui` = `click`, `sortie` / `voyant` = `output`.

A result is shown under its readable name (`function_names`, "Loop roll"),
and that name's words match too, next to the raw tag's: the raw tag stays in
the row's tooltip.

Deliberately Qt-free so it's testable without a QApplication; physical
control names come from `catalog.lookup`, which is Qt-free too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from djmidi import catalog
from djmidi.function_names import function_name
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.model import Control, MappingElement, MidiConfig

#: A result's location parts, translated by the GUI (issue #318).
DECK_LABEL = QT_TRANSLATE_NOOP("FunctionSearchView", "Deck {deck}")
SLOT_LABEL = QT_TRANSLATE_NOOP("FunctionSearchView", "Slot {slot}")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_EVENT_WORDS = {
    "click": "click",
    "press": "click",
    "output": "output",
    "led": "output",
    # French (issue #326).
    "clic": "click",
    "appui": "click",
    "sortie": "output",
    "voyant": "output",
}
# Words that pin the next number to a deck or a slot, English and French.
_PIN_WORDS = {"deck": "deck", "platine": "deck", "slot": "slot", "emplacement": "slot"}

# Per-token scores. A function whose own words match the query beats one
# that only matches through a number; click (what the user presses) beats
# output (LED feedback) on ties.
_EXACT_WORD = 3.0
_PREFIX_WORD = 2.0
_SUBSTRING = 1.0
_NUMBER = 1.0
_EVENT = 0.5
_PHRASE_BONUS = 2.0


@dataclass(frozen=True)
class Trigger:
    """One raw MIDI trigger, in model.Control's own string convention."""

    channel: str
    event_type: str
    control: str

    def describe(self) -> str:
        return f"ch{self.channel} {self.event_type} #{self.control}"


@dataclass
class FunctionResult:
    tag: str
    event: str
    deck_id: str | None
    slot_id: str | None
    triggers: list[Trigger] = field(default_factory=list)
    # The first real Control seen for each trigger, aligned with `triggers`;
    # what navigation selects in the By Channel columns.
    controls: list[Control] = field(default_factory=list)
    # Every MappingElement (all duplicates) behind this result.
    mappings: list[MappingElement] = field(default_factory=list)
    score: float = 0.0

    @property
    def label(self) -> str:
        """The readable function name ("Loop roll"), or the raw tag when
        `function_names` has none."""
        return function_name(self.tag)

    def location(self, translate: Translate = untranslated) -> str:
        """"Deck 0 · Slot 3"; the GUI passes a `translate` for its own language."""
        parts = []
        if self.deck_id:
            parts.append(translate(DECK_LABEL).format(deck=self.deck_id))
        if self.slot_id:
            parts.append(translate(SLOT_LABEL).format(slot=self.slot_id))
        return " · ".join(parts) or "—"


def readable_label(tag: str) -> str:
    """`auto_loop_roll_specific_length` -> "auto loop roll specific length"."""
    return " ".join(_TOKEN_RE.findall(tag.lower())) or tag


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def physical_names(trigger: Trigger) -> list[str]:
    """Every catalog name this trigger resolves to, as "Controller: Name" --
    a merged config doesn't say which device sent it, so all matches are
    listed (the same ambiguity the rest of the app shows)."""
    return [
        f"{hit.controller}: {hit.name}"
        for hit in catalog.lookup(trigger.channel, trigger.event_type, trigger.control)
    ]


def index_functions(config: MidiConfig) -> list[FunctionResult]:
    """Every distinct function target in the file, in first-seen order."""
    results: dict[tuple[str, str, str | None, str | None], FunctionResult] = {}
    for control in config.controls:
        trigger = Trigger(control.channel, control.event_type, control.control)
        for userio in control.userios:
            for mapping in userio.mappings:
                key = (mapping.tag, userio.event, mapping.deck_id, mapping.slot_id)
                result = results.get(key)
                if result is None:
                    result = results[key] = FunctionResult(
                        tag=mapping.tag, event=userio.event, deck_id=mapping.deck_id, slot_id=mapping.slot_id
                    )
                if trigger not in result.triggers:
                    result.triggers.append(trigger)
                    result.controls.append(control)
                result.mappings.append(mapping)
    return list(results.values())


def _parse_query(query: str) -> tuple[list[str], str | None, str | None, str | None]:
    """Splits out `deck N` / `slot N` constraints and an event word; returns
    (free tokens, deck, slot, event)."""
    tokens = tokenize(query)
    free: list[str] = []
    deck = slot = event = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if token in _PIN_WORDS and following is not None and following.isdigit():
            if _PIN_WORDS[token] == "deck":
                deck = following
            else:
                slot = following
            index += 2
            continue
        if token in _EVENT_WORDS:
            event = _EVENT_WORDS[token]
        else:
            free.append(token)
        index += 1
    return free, deck, slot, event


def _token_score(token: str, words: list[str], joined: str, result: FunctionResult) -> float:
    if token in words:
        return _EXACT_WORD
    if any(word.startswith(token) for word in words):
        return _PREFIX_WORD
    if token.isdigit() and token in (result.deck_id, result.slot_id):
        return _NUMBER
    if len(token) > 1 and token in joined:
        return _SUBSTRING
    return 0.0


def _score(result: FunctionResult, free: list[str], deck, slot, event) -> float | None:
    if deck is not None and result.deck_id != deck:
        return None
    if slot is not None and result.slot_id != slot:
        return None
    if event is not None and result.event != event:
        return None
    raw_words = tokenize(result.tag)
    name_words = tokenize(function_name(result.tag))
    words = list(dict.fromkeys(raw_words + name_words))
    joined = "".join(raw_words) + " " + "".join(name_words)
    total = 0.0
    for token in free:
        score = _token_score(token, words, joined, result)
        if not score:
            return None
        total += score
    phrase = " ".join(free)
    if free and (phrase in " ".join(raw_words) or phrase in " ".join(name_words)):
        total += _PHRASE_BONUS
    if deck is not None or slot is not None:
        total += _NUMBER
    if event is not None:
        total += _EVENT
    return total


def _numeric(value: str | None) -> tuple[int, str]:
    if value is not None and value.isdigit():
        return (int(value), "")
    return (1 << 30, value or "")


def search_functions(source: MidiConfig | list[FunctionResult], query: str) -> list[FunctionResult]:
    """Results matching `query`, best first. `source` is a config, or an
    `index_functions` result reused across keystrokes. An empty query (or one
    with no usable token) returns nothing rather than the whole file."""
    free, deck, slot, event = _parse_query(query)
    if not free and deck is None and slot is None and event is None:
        return []
    index = index_functions(source) if isinstance(source, MidiConfig) else source
    matches: list[FunctionResult] = []
    for result in index:
        score = _score(result, free, deck, slot, event)
        if score is None:
            continue
        result.score = score
        matches.append(result)
    matches.sort(
        key=lambda r: (
            -r.score,
            r.event != "click",
            r.tag,
            _numeric(r.deck_id),
            _numeric(r.slot_id),
        )
    )
    return matches


__all__ = [
    "FunctionResult",
    "Trigger",
    "index_functions",
    "physical_names",
    "readable_label",
    "search_functions",
    "tokenize",
]
