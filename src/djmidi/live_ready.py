""""Ready for live" mapping check (issue #254).

A pre-gig read-through of the loaded mapping that answers one question: is
there anything here that would surprise me on stage? It lists three kinds of
finding, each with a severity and a plain-language hint, and never changes
the mapping -- fixing is always the DJ's call:

- **essential** (warning): a deck has no input mapping for one of the
  `ESSENTIAL_FUNCTIONS` (Play, Cue, Sync, Load). A function is recognised
  from the *words* of its tag (`Play/Pause` -> play, `Sync On` -> sync), not
  from a table of Serato tag names: none of the repository's real Serato
  exports maps any of these four (they only use loop and `codfather_*` tags,
  see `function_names.py`), so this project has no confirmed Serato tag to
  list, and guessing one would be fabricating. Words work for Traktor's
  command names too. A custom Serato file only lists what was remapped --
  Serato's built-in support for the controller may well cover Play/Cue/Sync/
  Load -- so this stays a warning whose hint says exactly that.
- **conflict** (error): reused from `validator` -- a trigger that fires two
  different functions on the same deck (`find_deck_conflicts`), or whose
  repeated copies disagree with each other (only one is honoured). Serato's
  verbatim 10x repetition is not a conflict and is never reported.
- **led** (info): an input binding whose function has an output (LED
  feedback) counterpart, but whose trigger carries no output mapping for it,
  so the button won't light. "Has a counterpart" is decided from evidence
  only: a tag that this file maps as output somewhere, or one of
  `KNOWN_OUTPUT_FUNCTIONS`, the tags seen with output mappings in the
  repository's real exports. `auto_loop_roll_specific_length` is never mapped
  as output there, so it is never flagged.

Qt-free, like `validator.py`, so it is tested without a QApplication; the
report window is `gui/live_ready_dialog.py`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from djmidi.function_names import function_label
from djmidi.model import Control, MidiConfig
from djmidi.validator import (
    Severity,
    TriggerKey,
    _group_by_trigger,
    find_deck_conflicts,
)


@dataclass(frozen=True)
class EssentialFunction:
    """A function every deck should be able to trigger live.

    A mapping counts as this function when its tag contains one of `words`
    and none of `excluded` (split on anything that isn't a letter or digit,
    case-insensitive): a hot cue is not the main Cue button."""

    key: str
    label: str
    words: frozenset[str]
    excluded: frozenset[str] = frozenset()

    def matches(self, tag: str) -> bool:
        tokens = set(tag_words(tag))
        return bool(tokens & self.words) and not tokens & self.excluded


# The minimum a deck needs on stage -- a clear constant, per issue #254.
ESSENTIAL_FUNCTIONS: tuple[EssentialFunction, ...] = (
    EssentialFunction("play", "Play", frozenset({"play"})),
    EssentialFunction("cue", "Cue", frozenset({"cue"}), frozenset({"hot", "hotcue"})),
    EssentialFunction("sync", "Sync", frozenset({"sync"})),
    EssentialFunction("load", "Load", frozenset({"load"})),
)

# Tags mapped as output (LED feedback) in the repository's real Serato
# exports (`data/xdj_xz-ddj_xp2-4decks.xml`, `data/serato/*.xml.zip`).
KNOWN_OUTPUT_FUNCTIONS: frozenset[str] = frozenset({"auto_loop_specific_length", "codfather_st", "codfather_fx"})

SEVERITY_ORDER: dict[str, int] = {"error": 0, "warning": 1, "info": 2}

_WORD_RE = re.compile(r"[a-z0-9]+")
_NO_DECK = ("", "(none)")


def tag_words(tag: str) -> list[str]:
    """`"Play/Pause"` -> `["play", "pause"]`, `"hot_cue_1"` -> `["hot", "cue", "1"]`."""
    return _WORD_RE.findall(tag.lower())


@dataclass(frozen=True)
class ReadyFinding:
    severity: Severity
    category: str  # "essential", "conflict" or "led"
    message: str
    hint: str
    location: str = ""
    deck_id: str | None = None
    # The first raw control involved, for "show me" navigation (not compared).
    control: Control | None = field(default=None, compare=False, repr=False)


@dataclass
class ReadyReport:
    findings: list[ReadyFinding]
    decks: tuple[str, ...]

    def counts(self) -> Counter[str]:
        return Counter(finding.severity for finding in self.findings)

    @property
    def verdict(self) -> str:
        """One line for the top of the report."""
        counts = self.counts()
        if counts["error"]:
            return f"Not ready: {counts['error']} problem(s) to fix before playing."
        if counts["warning"]:
            return f"Check before playing: {counts['warning']} warning(s)."
        return "Ready for live."


def _trigger_text(key: TriggerKey) -> str:
    channel, event_type, control = key
    return f"channel {channel}, {event_type} {control}"


def _location(key: TriggerKey) -> str:
    channel, event_type, control = key
    return f"control[channel={channel}, event_type={event_type}, control={control}]"


def _deck_sort_key(deck: str) -> tuple[int, int, str]:
    return (0, int(deck), "") if deck.isdigit() else (1, 0, deck)


def mapped_decks(config: MidiConfig) -> tuple[str, ...]:
    """Every deck an input ("click") mapping targets, in deck order."""
    decks = {
        mapping.deck_id
        for control in config.controls
        for userio in control.userios
        if userio.event == "click"
        for mapping in userio.mappings
        if mapping.deck_id and mapping.deck_id not in _NO_DECK
    }
    return tuple(sorted(decks, key=_deck_sort_key))


def _check_essentials(
    config: MidiConfig, decks: tuple[str, ...], essentials: tuple[EssentialFunction, ...]
) -> list[ReadyFinding]:
    if not decks:
        return [
            ReadyFinding(
                severity="warning",
                category="essential",
                message="No input mapping targets a deck, so no deck has Play, Cue, Sync or Load here.",
                hint="If Serato's built-in support for your controller drives the decks, this is fine; "
                "otherwise map at least Play, Cue, Sync and Load for each deck you play.",
            )
        ]
    covered: dict[str, set[str]] = {deck: set() for deck in decks}
    for control in config.controls:
        for userio in control.userios:
            if userio.event != "click":
                continue
            for mapping in userio.mappings:
                if mapping.deck_id not in covered:
                    continue
                for essential in essentials:
                    if essential.matches(mapping.tag):
                        covered[mapping.deck_id].add(essential.key)
    findings = []
    for deck in decks:
        for essential in essentials:
            if essential.key in covered[deck]:
                continue
            findings.append(
                ReadyFinding(
                    severity="warning",
                    category="essential",
                    message=f"Deck {deck} has no {essential.label} mapping.",
                    hint=f"This file only lists the controls you remapped: if Serato's built-in support for "
                    f"your controller handles {essential.label}, you're fine. Otherwise map a button to "
                    f"{essential.label} on deck {deck} before going on stage.",
                    deck_id=deck,
                )
            )
    return findings


def _check_conflicts(groups: dict[TriggerKey, list[Control]], config: MidiConfig) -> list[ReadyFinding]:
    findings = []
    deck_conflicts = find_deck_conflicts(config)
    for key, conflicts in deck_conflicts.items():
        for conflict in conflicts:
            names = ", ".join(function_label(tag, slot) for tag, slot in conflict.functions)
            findings.append(
                ReadyFinding(
                    severity="error",
                    category="conflict",
                    message=f"One control ({_trigger_text(key)}) fires several functions on deck "
                    f"{conflict.deck_id}: {names}.",
                    hint="Pressing it on stage triggers all of them at once. Keep one function per deck "
                    "on this control, or move the others to a free button.",
                    location=_location(key),
                    deck_id=conflict.deck_id,
                    control=groups[key][0],
                )
            )
    for key, controls in groups.items():
        if key in deck_conflicts or len(controls) <= 1:
            continue
        distinct: list[Control] = []
        for control in controls:
            if control not in distinct:
                distinct.append(control)
        if len(distinct) > 1:
            findings.append(
                ReadyFinding(
                    severity="error",
                    category="conflict",
                    message=f"The copies of one control ({_trigger_text(key)}) disagree: "
                    f"{len(distinct)} different versions.",
                    hint="Serato honours only one of them, so the control may not do what you expect. "
                    "Make every copy identical (edit it from the By Deck view, which keeps copies together).",
                    location=_location(key),
                    control=controls[0],
                )
            )
    return findings


def _check_led_feedback(
    groups: dict[TriggerKey, list[Control]], config: MidiConfig, known_output: frozenset[str]
) -> list[ReadyFinding]:
    output_tags = set(known_output) | {
        mapping.tag
        for control in config.controls
        for userio in control.userios
        if userio.event == "output"
        for mapping in userio.mappings
    }
    findings = []
    for key, controls in groups.items():
        inputs: set[tuple[str, str | None, str | None]] = set()
        outputs: set[tuple[str, str | None, str | None]] = set()
        for control in controls:
            for userio in control.userios:
                target = inputs if userio.event == "click" else outputs if userio.event == "output" else None
                if target is None:
                    continue
                for mapping in userio.mappings:
                    target.add((mapping.tag, mapping.deck_id, mapping.slot_id))
        missing = sorted(
            (item for item in inputs - outputs if item[0] in output_tags),
            key=lambda item: (item[0], item[1] or "", item[2] or ""),
        )
        for tag, deck, slot in missing:
            findings.append(
                ReadyFinding(
                    severity="info",
                    category="led",
                    message=f"{function_label(tag, slot)} on deck {deck or '?'} ({_trigger_text(key)}) "
                    "has no LED feedback mapping.",
                    hint="The function works, but this button won't light to show its state. Add an output "
                    "mapping for the same function on this control if you rely on the light.",
                    location=_location(key),
                    deck_id=deck,
                    control=controls[0],
                )
            )
    return findings


def check_live_ready(
    config: MidiConfig,
    essentials: tuple[EssentialFunction, ...] = ESSENTIAL_FUNCTIONS,
    known_output: frozenset[str] = KNOWN_OUTPUT_FUNCTIONS,
) -> ReadyReport:
    """Run every check; findings come sorted by severity (errors first). Read-only."""
    groups = _group_by_trigger(config)
    decks = mapped_decks(config)
    findings = (
        _check_conflicts(groups, config)
        + _check_essentials(config, decks, essentials)
        + _check_led_feedback(groups, config, known_output)
    )
    findings.sort(key=lambda finding: SEVERITY_ORDER.get(finding.severity, len(SEVERITY_ORDER)))
    return ReadyReport(findings=findings, decks=decks)


def report_text(report: ReadyReport) -> str:
    """Plain text of the whole report, for the clipboard."""
    lines = [report.verdict, ""]
    for finding in report.findings:
        lines.append(f"[{finding.severity}] {finding.message}")
        lines.append(f"    {finding.hint}")
    return "\n".join(lines)


__all__ = [
    "ESSENTIAL_FUNCTIONS",
    "KNOWN_OUTPUT_FUNCTIONS",
    "SEVERITY_ORDER",
    "EssentialFunction",
    "ReadyFinding",
    "ReadyReport",
    "check_live_ready",
    "mapped_decks",
    "report_text",
    "tag_words",
]
