"""Editing Serato modifier / SHIFT layers (issue #434).

A hand-edited Serato mapping wraps bindings in ``<case><condition>
<modifier_N operator="equal" cmp_value="on"/></condition><userio…/></case>``
blocks (`model.Case`). Until now they were read and written back byte for
byte but never editable. This module computes the edits -- change a block's
conditions, put a direct binding into a new layer, take a layer's bindings
back out -- as *new* lists for one control (`LayerEdit`), never mutating the
model, so the GUI applies them as one undoable swap.

Nothing here invents Serato vocabulary: the modifiers and operators offered
come from the loaded file (`known_modifiers`, `known_operators`), "equal"
being the only operator real files are known to use, and every value stays
free text.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from dataclasses import dataclass

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.model import Case, Condition, Control, MidiConfig, UserIO

DEFAULT_OPERATOR = "equal"
DEFAULT_VALUES = ("on", "off")
_MODIFIER_RE = re.compile(r"^modifier_\d+$")
# An XML element name (what a condition's tag is written as).
_TAG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

_BAD_TAG = QT_TRANSLATE_NOOP("CaseEdit", "Condition {number}: \"{tag}\" isn't a valid modifier name.")
_EMPTY_FIELD = QT_TRANSLATE_NOOP("CaseEdit", "Condition {number}: the operator and the value can't be empty.")
_NO_CONDITION = QT_TRANSLATE_NOOP("CaseEdit", "A layer needs at least one condition.")


class LayerError(ValueError):
    """An edit that can't be applied; ``str()`` is English, `describe` translates."""

    def __init__(self, template: str, **fields: object) -> None:
        self.template = template
        self.fields = fields
        super().__init__(template.format(**fields))

    def describe(self, translate: Translate = untranslated) -> str:
        return translate(self.template).format(**self.fields)


@dataclass(frozen=True)
class ConditionSpec:
    """One condition as typed: modifier, operator, value."""

    tag: str
    operator: str = DEFAULT_OPERATOR
    value: str = "on"


@dataclass
class LayerEdit:
    """What `control.userios` and `control.cases` become."""

    userios: list[UserIO]
    cases: list[Case]


def find_control_of(config: MidiConfig | None, node: Case | UserIO) -> Control | None:
    """The control holding `node` (a case, or a direct or case binding)."""
    if config is None:
        return None
    for control in config.controls:
        if any(case is node for case in control.cases):
            return control
        if any(userio is node for userio in control.userios):
            return control
        if any(userio is node for case in control.cases for userio in case.userios):
            return control
    return None


def known_modifiers(config: MidiConfig | None) -> list[str]:
    """Modifier names the file already uses: condition tags, then
    ``modifier_N`` mapping elements (the modifier definitions), sorted."""
    names: set[str] = set()
    for control in config.controls if config is not None else ():
        for case in control.cases:
            names.update(condition.tag for condition in case.conditions)
        for userio in [*control.userios, *(u for case in control.cases for u in case.userios)]:
            names.update(mapping.tag for mapping in userio.mappings if _MODIFIER_RE.match(mapping.tag))
    return sorted(names, key=_natural_key)


def known_operators(config: MidiConfig | None) -> list[str]:
    """Operators the file's conditions use; "equal" first, always offered."""
    found = {
        condition.attrs.get("operator", "")
        for control in (config.controls if config is not None else ())
        for case in control.cases
        for condition in case.conditions
    }
    return [DEFAULT_OPERATOR, *sorted(op for op in found if op and op != DEFAULT_OPERATOR)]


def specs_of(case: Case) -> list[ConditionSpec]:
    return [
        ConditionSpec(c.tag, c.attrs.get("operator", DEFAULT_OPERATOR), c.attrs.get("cmp_value", ""))
        for c in case.conditions
    ]


def validate_specs(specs: Iterable[ConditionSpec]) -> list[ConditionSpec]:
    specs = [ConditionSpec(s.tag.strip(), s.operator.strip(), s.value.strip()) for s in specs]
    if not specs:
        raise LayerError(_NO_CONDITION)
    for number, spec in enumerate(specs, start=1):
        if not _TAG_RE.match(spec.tag):
            raise LayerError(_BAD_TAG, number=number, tag=spec.tag)
        if not spec.operator or not spec.value:
            raise LayerError(_EMPTY_FIELD, number=number)
    return specs


def _condition(spec: ConditionSpec, previous: Condition | None = None) -> Condition:
    """A condition for `spec`, keeping `previous`'s other attributes and
    attribute order when it edits an existing one."""
    if previous is None:
        return Condition(spec.tag, {"operator": spec.operator, "cmp_value": spec.value})
    attrs = dict(previous.attrs)
    attrs["operator"] = spec.operator
    attrs["cmp_value"] = spec.value
    return Condition(spec.tag, attrs)


def _copy(control: Control) -> tuple[list[UserIO], list[Case]]:
    return list(control.userios), list(control.cases)


def set_conditions(control: Control, case: Case, specs: Iterable[ConditionSpec]) -> LayerEdit:
    """`case`'s conditions replaced by `specs` (the case is copied)."""
    specs = validate_specs(specs)
    userios, cases = _copy(control)
    index = _index(cases, case)
    new_case = copy.copy(case)
    previous = list(case.conditions)
    new_case.conditions = [
        _condition(spec, previous[i] if i < len(previous) else None) for i, spec in enumerate(specs)
    ]
    new_case.has_condition = True
    cases[index] = new_case
    return LayerEdit(userios, cases)


def move_into_layer(control: Control, userio: UserIO, specs: Iterable[ConditionSpec]) -> LayerEdit:
    """A direct binding moved into a new layer (appended after the others)."""
    specs = validate_specs(specs)
    userios, cases = _copy(control)
    userios.pop(_index(userios, userio))
    cases.append(Case(conditions=[_condition(spec) for spec in specs], userios=[userio]))
    return LayerEdit(userios, cases)


def remove_layer(control: Control, case: Case) -> LayerEdit:
    """`case` removed; its bindings become direct ones again (appended)."""
    userios, cases = _copy(control)
    removed = cases.pop(_index(cases, case))
    return LayerEdit([*userios, *removed.userios], cases)


def _index(items: list, item: object) -> int:
    for index, candidate in enumerate(items):
        if candidate is item:
            return index
    raise ValueError("not part of this control")


def _natural_key(name: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name))


__all__ = [
    "DEFAULT_OPERATOR",
    "DEFAULT_VALUES",
    "ConditionSpec",
    "LayerEdit",
    "LayerError",
    "find_control_of",
    "known_modifiers",
    "known_operators",
    "move_into_layer",
    "remove_layer",
    "set_conditions",
    "specs_of",
    "validate_specs",
]
