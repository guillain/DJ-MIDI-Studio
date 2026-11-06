from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class Alias:
    name: str
    value: str
    extra_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class Translation:
    action_on: str | None = None
    behaviour: str | None = None
    aliases: list[Alias] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class MappingElement:
    """A Serato function mapping, e.g. <codfather_st deck_set="Default" deck_id="1" slot_id="0">.

    `tag` is the Serato function name (the XML element's tag itself carries the
    semantics, unlike the other elements in this model).
    """

    tag: str
    deck_set: str | None = None
    deck_id: str | None = None
    slot_id: str | None = None
    translations: list[Translation] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class UserIO:
    event: str  # "click" or "output"
    mappings: list[MappingElement] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)


ConditionKey = tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
# The condition of a binding outside any <case>.
NO_CONDITION: ConditionKey = ()


def describe_condition(key: ConditionKey) -> str:
    parts = []
    for tag, attrs in key:
        values = dict(attrs)
        operator = values.get("operator", "equal")
        symbol = {"equal": "=", "not_equal": "!="}.get(operator, operator)
        value = values.get("cmp_value", "")
        parts.append(f"{tag} {symbol} {value}".strip())
    return ", ".join(parts)


@dataclass
class Condition:
    """One test inside a Serato ``<case><condition>`` block, e.g.
    ``<modifier_3 operator="equal" cmp_value="on"/>``: `tag` is the element
    name (a modifier), `attrs` its attributes in file order."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class Case:
    """A ``<case>`` under a ``<control>``: its ``<userio>`` blocks apply only
    while every condition holds (how hand-edited Serato mappings express
    modifier / SHIFT layers)."""

    conditions: list[Condition] = field(default_factory=list)
    userios: list[UserIO] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)
    condition_attrs: dict[str, str] = field(default_factory=dict)
    has_condition: bool = True
    # How many of the control's direct <userio> children come before this
    # case in the file, so a save writes the children back in their order.
    position: int | None = None

    def condition_key(self) -> ConditionKey:
        """The conditions as a hashable, order-independent value: two cases
        with the same tests are the same layer."""
        return tuple(sorted((test.tag, tuple(sorted(test.attrs.items()))) for test in self.conditions))

    def describe(self) -> str:
        """``modifier_1 = on, modifier_2 = off`` -- readable, language-neutral."""
        return describe_condition(self.condition_key())


@dataclass
class Control:
    channel: str
    event_type: str
    control: str
    userios: list[UserIO] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)
    # Conditional (<case>) blocks; `iter_bindings` walks them with `userios`.
    cases: list[Case] = field(default_factory=list)


def iter_bindings(control: Control) -> Iterator[tuple[UserIO, Case | None]]:
    """Every <userio> of `control` -- direct ones, then each <case>'s -- with
    the case it sits in (None outside any). Use this, not `control.userios`,
    wherever a binding is read: a <case> binding is a real binding."""
    for userio in control.userios:
        yield userio, None
    for case in control.cases:
        for userio in case.userios:
            yield userio, case


def condition_of(case: Case | None) -> ConditionKey:
    return case.condition_key() if case is not None else NO_CONDITION


@dataclass
class MidiConfig:
    app_version: str | None = None
    controls: list[Control] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)
