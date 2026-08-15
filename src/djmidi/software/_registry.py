"""Registry primitives for DJ software mapping plugins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from djmidi.model import MidiConfig

Parser = Callable[[str], MidiConfig]
Exporter = Callable[[MidiConfig], str]


@dataclass(frozen=True)
class SoftwareDefinition:
    plugin_id: str
    name: str
    extensions: tuple[str, ...]
    parser: Parser
    exporter: Exporter
    display_order: int = 100

    def parse_file(self, path: str | PathLike[str]) -> MidiConfig:
        return self.parser(Path(path).read_text(encoding="utf-8"))

    def write_file(self, config: MidiConfig, path: str | PathLike[str]) -> None:
        Path(path).write_text(self.exporter(config), encoding="utf-8")


_REGISTRY: dict[str, SoftwareDefinition] = {}


def register(definition: SoftwareDefinition, *, replace: bool = False) -> None:
    if definition.plugin_id in _REGISTRY and not replace:
        raise ValueError(f"Software plugin already registered: {definition.plugin_id}")
    _REGISTRY[definition.plugin_id] = definition


def get_definition(plugin_id: str) -> SoftwareDefinition:
    try:
        return _REGISTRY[plugin_id]
    except KeyError:
        raise ValueError(f"Unknown software plugin: {plugin_id}") from None


def all_definitions() -> list[SoftwareDefinition]:
    return sorted(_REGISTRY.values(), key=lambda definition: (definition.display_order, definition.name))


__all__ = ["SoftwareDefinition", "all_definitions", "get_definition", "register"]
