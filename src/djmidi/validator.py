from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.model import Control, MidiConfig

_LOGGER = logging.getLogger(__name__)

Severity = Literal["error", "warning", "info"]

KNOWN_ACTION_ON = {"press", "any"}
KNOWN_BEHAVIOUR = {"toggle", "explicit"}

# Validation-table texts (issue #326): English templates, translated by the
# caller through `translate` before they are filled in. Tags, attribute names
# and values stay as the file writes them.
SEVERITY_LABELS: dict[str, str] = {
    "error": QT_TRANSLATE_NOOP("Validator", "error"),
    "warning": QT_TRANSLATE_NOOP("Validator", "warning"),
    "info": QT_TRANSLATE_NOOP("Validator", "info"),
}
_CONFLICTING_COPIES = QT_TRANSLATE_NOOP(
    "Validator",
    "Trigger (channel={channel}, event_type={event_type}, control={control}) is bound "
    "{count} times with {distinct} different mappings; only one will take effect.",
)
_IDENTICAL_COPIES = QT_TRANSLATE_NOOP(
    "Validator",
    "Trigger (channel={channel}, event_type={event_type}, control={control}) is defined "
    "{count} times with identical content. This repetition appears required by "
    "Serato — do not deduplicate.",
)
_MISSING_CONTROL_ATTRIBUTE = QT_TRANSLATE_NOOP(
    "Validator", "Control is missing a required attribute (channel/event_type/control)."
)
_MISSING_DECK_OR_SLOT = QT_TRANSLATE_NOOP("Validator", "Mapping <{tag}> is missing deck_id or slot_id.")
_MISSING_ACTION_ON = QT_TRANSLATE_NOOP("Validator", "<translation> under <{tag}> is missing action_on.")
_UNKNOWN_ACTION_ON = QT_TRANSLATE_NOOP("Validator", "Unrecognized action_on value '{value}'.")
_UNKNOWN_BEHAVIOUR = QT_TRANSLATE_NOOP("Validator", "Unrecognized behaviour value '{value}'.")
_INCONSISTENT_TARGET = QT_TRANSLATE_NOOP(
    "Validator",
    "Target <{tag}> (deck_id={deck_id}, slot_id={slot_id}) is bound to 'click' by "
    "{count} different controls with inconsistent behaviour/action_on: {values}.",
)
_CONFLICT_FUNCTION = QT_TRANSLATE_NOOP("Validator", "{tag} (slot {slot})")
_CONFLICT_DECK = QT_TRANSLATE_NOOP("Validator", "deck {deck}: {functions}")


def severity_label(severity: str, translate: Translate = untranslated) -> str:
    """The severity as the validation table shows it (issue #326)."""
    return translate(SEVERITY_LABELS[severity]) if severity in SEVERITY_LABELS else severity


@dataclass
class ValidationIssue:
    severity: Severity
    message: str
    location: str


TriggerKey = tuple[str, str, str]  # (channel, event_type, control), as on model.Control


@dataclass(frozen=True)
class DeckConflict:
    """One deck on which a single trigger fires two or more *different* functions.

    `functions` lists each distinct `(tag, slot_id)` the trigger's "click" mappings
    bind on that deck, sorted for stable display."""

    deck_id: str
    functions: tuple[tuple[str, str], ...]

    def describe(self, translate: Translate = untranslated) -> str:
        names = ", ".join(translate(_CONFLICT_FUNCTION).format(tag=tag, slot=slot) for tag, slot in self.functions)
        return translate(_CONFLICT_DECK).format(deck=self.deck_id, functions=names)


def _group_by_trigger(config: MidiConfig) -> dict[TriggerKey, list[Control]]:
    groups: dict[TriggerKey, list[Control]] = {}
    for control in config.controls:
        key = (control.channel, control.event_type, control.control)
        groups.setdefault(key, []).append(control)
    return groups


def find_deck_conflicts(config: MidiConfig) -> dict[TriggerKey, list[DeckConflict]]:
    """Triggers whose input ("click") mappings resolve to two or more different
    functions on the same deck -- what Live Monitor flags when such a trigger
    arrives live (issue #223).

    A function is a `(tag, slot_id)` pair, so Serato's verbatim 10x repetition of
    every trigger collapses to one function and is never a conflict (see
    `_check_duplicate_triggers`); output ("output", LED feedback) mappings are
    ignored since they don't fire anything. Triggers with no conflict are absent
    from the result."""
    result: dict[TriggerKey, list[DeckConflict]] = {}
    for key, controls in _group_by_trigger(config).items():
        by_deck: dict[str, set[tuple[str, str]]] = {}
        for control in controls:
            for userio in control.userios:
                if userio.event != "click":
                    continue
                for mapping in userio.mappings:
                    deck = mapping.deck_id or "(none)"
                    by_deck.setdefault(deck, set()).add((mapping.tag, mapping.slot_id or "(none)"))
        conflicts = [
            DeckConflict(deck_id=deck, functions=tuple(sorted(functions)))
            for deck, functions in sorted(by_deck.items())
            if len(functions) > 1
        ]
        if conflicts:
            result[key] = conflicts
    return result


def _control_location(control) -> str:
    return f"control[channel={control.channel}, event_type={control.event_type}, control={control.control}]"


def _mapping_location(control, userio, mapping) -> str:
    return f"{_control_location(control)}/userio[event={userio.event}]/{mapping.tag}[deck_id={mapping.deck_id}, slot_id={mapping.slot_id}]"


def _check_duplicate_triggers(config: MidiConfig, translate: Translate = untranslated) -> list[ValidationIssue]:
    """The same (channel, event_type, control) can legitimately appear more than once in
    Serato-generated files as long as every occurrence maps to the same thing. Despite
    looking redundant, real Serato exports rely on this exact repetition (observed: every
    unique trigger repeated the same number of times) and deleting the "duplicates" has
    been confirmed to break the config in Serato — so this is flagged as informational
    only, not something to clean up. If occurrences disagree with each other, that's a
    real conflict: only one will actually be honoured by Serato."""
    groups = _group_by_trigger(config)

    issues: list[ValidationIssue] = []
    for key, controls in groups.items():
        if len(controls) <= 1:
            continue
        distinct = []
        for control in controls:
            if control not in distinct:
                distinct.append(control)
        if len(distinct) > 1:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=translate(_CONFLICTING_COPIES).format(
                        channel=key[0], event_type=key[1], control=key[2], count=len(controls), distinct=len(distinct)
                    ),
                    location=_control_location(controls[0]),
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    severity="info",
                    message=translate(_IDENTICAL_COPIES).format(
                        channel=key[0], event_type=key[1], control=key[2], count=len(controls)
                    ),
                    location=_control_location(controls[0]),
                )
            )
    return issues


def _check_required_fields(config: MidiConfig, translate: Translate = untranslated) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for control in config.controls:
        if not control.channel or not control.event_type or not control.control:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message=translate(_MISSING_CONTROL_ATTRIBUTE),
                    location=_control_location(control),
                )
            )
        for userio in control.userios:
            for mapping in userio.mappings:
                if not mapping.deck_id or not mapping.slot_id:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            message=translate(_MISSING_DECK_OR_SLOT).format(tag=mapping.tag),
                            location=_mapping_location(control, userio, mapping),
                        )
                    )
                for translation in mapping.translations:
                    if not translation.action_on:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                message=translate(_MISSING_ACTION_ON).format(tag=mapping.tag),
                                location=_mapping_location(control, userio, mapping),
                            )
                        )
    return issues


def _check_unknown_values(config: MidiConfig, translate: Translate = untranslated) -> list[ValidationIssue]:
    """Flag action_on/behaviour values outside the ones observed in known-good configs.
    Informational only: the full set of values Serato accepts isn't documented here."""
    issues: list[ValidationIssue] = []
    for control in config.controls:
        for userio in control.userios:
            for mapping in userio.mappings:
                for translation in mapping.translations:
                    if translation.action_on and translation.action_on not in KNOWN_ACTION_ON:
                        issues.append(
                            ValidationIssue(
                                severity="info",
                                message=translate(_UNKNOWN_ACTION_ON).format(value=translation.action_on),
                                location=_mapping_location(control, userio, mapping),
                            )
                        )
                    if translation.behaviour and translation.behaviour not in KNOWN_BEHAVIOUR:
                        issues.append(
                            ValidationIssue(
                                severity="info",
                                message=translate(_UNKNOWN_BEHAVIOUR).format(value=translation.behaviour),
                                location=_mapping_location(control, userio, mapping),
                            )
                        )
    return issues


def _check_inconsistent_click_targets(
    config: MidiConfig, translate: Translate = untranslated
) -> list[ValidationIssue]:
    """If several physical controls bind "click" to the same (tag, deck_id, slot_id) target
    with different behaviour/action_on, the resulting behaviour for that function is ambiguous."""
    targets: dict[tuple[str, str | None, str | None], list[tuple[str, str | None, object]]] = {}
    for control in config.controls:
        for userio in control.userios:
            if userio.event != "click":
                continue
            for mapping in userio.mappings:
                key = (mapping.tag, mapping.deck_id, mapping.slot_id)
                for translation in mapping.translations:
                    targets.setdefault(key, []).append(
                        (translation.behaviour, translation.action_on, (control, userio, mapping))
                    )

    issues: list[ValidationIssue] = []
    for key, bindings in targets.items():
        distinct = {(behaviour, action_on) for behaviour, action_on, _ in bindings}
        if len(bindings) > 1 and len(distinct) > 1:
            tag, deck_id, slot_id = key
            _, _, (control, userio, mapping) = bindings[-1]
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message=translate(_INCONSISTENT_TARGET).format(
                        tag=tag, deck_id=deck_id, slot_id=slot_id, count=len(bindings), values=sorted(distinct)
                    ),
                    location=_mapping_location(control, userio, mapping),
                )
            )
    return issues


def validate(config: MidiConfig, translate: Translate = untranslated) -> list[ValidationIssue]:
    """Every structural problem and conflict in `config`. Messages are in
    English unless the GUI passes a `translate` for its language (issue #326)."""
    issues: list[ValidationIssue] = []
    issues += _check_duplicate_triggers(config, translate)
    issues += _check_required_fields(config, translate)
    issues += _check_unknown_values(config, translate)
    issues += _check_inconsistent_click_targets(config, translate)
    counts = Counter(issue.severity for issue in issues)
    log = _LOGGER.warning if counts["error"] else _LOGGER.info
    log(
        "Validation complete: %d error(s), %d warning(s), %d info (%d control(s) checked)",
        counts["error"],
        counts["warning"],
        counts["info"],
        len(config.controls),
    )
    for issue in issues:
        if issue.severity == "error":
            _LOGGER.debug("Validation error at %s: %s", issue.location, issue.message)
    return issues
