from __future__ import annotations

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


@dataclass
class Control:
    channel: str
    event_type: str
    control: str
    userios: list[UserIO] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class MidiConfig:
    app_version: str | None = None
    controls: list[Control] = field(default_factory=list)
    extra_attrs: dict[str, str] = field(default_factory=dict)
