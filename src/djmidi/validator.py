from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from djmidi.model import Control, MidiConfig

Severity = Literal["error", "warning", "info"]

KNOWN_ACTION_ON = {"press", "any"}
KNOWN_BEHAVIOUR = {"toggle", "explicit"}


@dataclass
class ValidationIssue:
    severity: Severity
    message: str
    location: str


def _control_location(control) -> str:
    return f"control[channel={control.channel}, event_type={control.event_type}, control={control.control}]"


def _mapping_location(control, userio, mapping) -> str:
    return f"{_control_location(control)}/userio[event={userio.event}]/{mapping.tag}[deck_id={mapping.deck_id}, slot_id={mapping.slot_id}]"


def _check_duplicate_triggers(config: MidiConfig) -> list[ValidationIssue]:
    """The same (channel, event_type, control) can legitimately appear more than once in
    Serato-generated files as long as every occurrence maps to the same thing. Despite
    looking redundant, real Serato exports rely on this exact repetition (observed: every
    unique trigger repeated the same number of times) and deleting the "duplicates" has
    been confirmed to break the config in Serato — so this is flagged as informational
    only, not something to clean up. If occurrences disagree with each other, that's a
    real conflict: only one will actually be honoured by Serato."""
    groups: dict[tuple[str, str, str], list[Control]] = {}
    for control in config.controls:
        key = (control.channel, control.event_type, control.control)
        groups.setdefault(key, []).append(control)

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
                    message=f"Trigger (channel={key[0]}, event_type={key[1]}, control={key[2]}) is bound "
                    f"{len(controls)} times with {len(distinct)} different mappings; only one will take effect.",
                    location=_control_location(controls[0]),
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    severity="info",
                    message=f"Trigger (channel={key[0]}, event_type={key[1]}, control={key[2]}) is defined "
                    f"{len(controls)} times with identical content. This repetition appears required by "
                    f"Serato — do not deduplicate.",
                    location=_control_location(controls[0]),
                )
            )
    return issues


def _check_required_fields(config: MidiConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for control in config.controls:
        if not control.channel or not control.event_type or not control.control:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message="Control is missing a required attribute (channel/event_type/control).",
                    location=_control_location(control),
                )
            )
        for userio in control.userios:
            for mapping in userio.mappings:
                if not mapping.deck_id or not mapping.slot_id:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            message=f"Mapping <{mapping.tag}> is missing deck_id or slot_id.",
                            location=_mapping_location(control, userio, mapping),
                        )
                    )
                for translation in mapping.translations:
                    if not translation.action_on:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                message=f"<translation> under <{mapping.tag}> is missing action_on.",
                                location=_mapping_location(control, userio, mapping),
                            )
                        )
    return issues


def _check_unknown_values(config: MidiConfig) -> list[ValidationIssue]:
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
                                message=f"Unrecognized action_on value '{translation.action_on}'.",
                                location=_mapping_location(control, userio, mapping),
                            )
                        )
                    if translation.behaviour and translation.behaviour not in KNOWN_BEHAVIOUR:
                        issues.append(
                            ValidationIssue(
                                severity="info",
                                message=f"Unrecognized behaviour value '{translation.behaviour}'.",
                                location=_mapping_location(control, userio, mapping),
                            )
                        )
    return issues


def _check_inconsistent_click_targets(config: MidiConfig) -> list[ValidationIssue]:
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
                    message=f"Target <{tag}> (deck_id={deck_id}, slot_id={slot_id}) is bound to 'click' by "
                    f"{len(bindings)} different controls with inconsistent behaviour/action_on: {sorted(distinct)}.",
                    location=_mapping_location(control, userio, mapping),
                )
            )
    return issues


def validate(config: MidiConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues += _check_duplicate_triggers(config)
    issues += _check_required_fields(config)
    issues += _check_unknown_values(config)
    issues += _check_inconsistent_click_targets(config)
    return issues
