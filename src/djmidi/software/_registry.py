"""Registry primitives for DJ software mapping plugins."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from djmidi.model import MidiConfig

_LOGGER = logging.getLogger(__name__)

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
    capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()

    def parse_file(self, path: str | PathLike[str]) -> MidiConfig:
        return self.parser(Path(path).read_text(encoding="utf-8"))

    def write_file(self, config: MidiConfig, path: str | PathLike[str]) -> None:
        Path(path).write_text(self.exporter(config), encoding="utf-8")

    def capability_report(self) -> dict[str, object]:
        """Return read-only metadata suitable for a preferences/status UI."""
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "extensions": self.extensions,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
        }

    def can_parse(self, root_tag: str, suffix: str) -> bool:
        normalized_suffix = suffix.lower() if suffix else ""
        return normalized_suffix in self.extensions or (
            self.plugin_id == "serato" and root_tag == "midi"
        ) or (self.plugin_id == "traktor" and root_tag == "NML")


_REGISTRY: dict[str, SoftwareDefinition] = {}
_ENABLED_PLUGIN_IDS: frozenset[str] | None = None


def register(definition: SoftwareDefinition, *, replace: bool = False) -> None:
    if definition.plugin_id in _REGISTRY and not replace:
        _LOGGER.error("Refusing to register software plugin %r: already registered", definition.plugin_id)
        raise ValueError(f"Software plugin already registered: {definition.plugin_id}")
    _REGISTRY[definition.plugin_id] = definition
    _LOGGER.info(
        "%s software plugin: %s (%s, extensions=%s)",
        "Replaced" if replace else "Registered",
        definition.plugin_id,
        definition.name,
        definition.extensions,
    )


def get_definition(plugin_id: str) -> SoftwareDefinition:
    try:
        return _REGISTRY[plugin_id]
    except KeyError:
        _LOGGER.warning("Unknown software plugin requested: %r", plugin_id)
        raise ValueError(f"Unknown software plugin: {plugin_id}") from None


def all_definitions() -> list[SoftwareDefinition]:
    return sorted(_REGISTRY.values(), key=lambda definition: (definition.display_order, definition.name))


def set_enabled_plugin_ids(plugin_ids: set[str] | frozenset[str] | None) -> None:
    global _ENABLED_PLUGIN_IDS
    _ENABLED_PLUGIN_IDS = None if plugin_ids is None else frozenset(plugin_ids)


def active_definitions() -> list[SoftwareDefinition]:
    definitions = all_definitions()
    if _ENABLED_PLUGIN_IDS is None:
        return definitions
    return [definition for definition in definitions if definition.plugin_id in _ENABLED_PLUGIN_IDS]


def detect_from_text(text: str, suffix: str = "") -> list[SoftwareDefinition]:
    """Returns software plugins compatible with an XML root and extension."""
    try:
        root_tag = ET.fromstring(text).tag
    except ET.ParseError:
        _LOGGER.debug("Software detection: text is not valid XML (suffix=%r)", suffix)
        return []
    signature_matches = [
        definition
        for definition in active_definitions()
        if (definition.plugin_id == "serato" and root_tag == "midi")
        or (definition.plugin_id == "traktor" and root_tag == "NML")
    ]
    matches = signature_matches or [
        definition for definition in active_definitions() if definition.can_parse(root_tag, suffix)
    ]
    _LOGGER.debug(
        "Software detection for root=<%s> suffix=%r: %s",
        root_tag,
        suffix,
        [definition.plugin_id for definition in matches] or "no match",
    )
    return matches


__all__ = [
    "SoftwareDefinition",
    "active_definitions",
    "all_definitions",
    "detect_from_text",
    "get_definition",
    "register",
    "set_enabled_plugin_ids",
]
