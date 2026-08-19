"""Discoverable DJ software mapping plugins."""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import pkgutil

from djmidi.software._registry import (
    SoftwareDefinition,
    active_definitions,
    all_definitions,
    detect_from_text,
    get_definition,
    set_enabled_plugin_ids,
)

_LOGGER = logging.getLogger(__name__)

_BUILTINS_DISCOVERED = False
_EXTERNAL_DISCOVERED = False
DISCOVERY_DIAGNOSTICS: list[str] = []


def discover_plugins(*, trust_external: bool = False) -> None:
    global _BUILTINS_DISCOVERED, _EXTERNAL_DISCOVERED
    if not _BUILTINS_DISCOVERED:
        _BUILTINS_DISCOVERED = True
        for module_info in pkgutil.iter_modules(__path__):
            if module_info.name.startswith("_"):
                continue
            importlib.import_module(f"{__name__}.{module_info.name}")
        _LOGGER.info("Discovered %d built-in software plugin(s)", len(all_definitions()))
    if _EXTERNAL_DISCOVERED:
        return
    entry_points = importlib.metadata.entry_points(group="djmidi.software")
    if not trust_external:
        if entry_points:
            _LOGGER.info(
                "Blocked %d external software plugin(s) (trust_external=False): %s",
                len(entry_points),
                [entry_point.name for entry_point in entry_points],
            )
        DISCOVERY_DIAGNOSTICS.extend(
            f"blocked external software plugin {entry_point.name!r}: trust is disabled"
            for entry_point in entry_points
        )
        return
    for entry_point in entry_points:
        try:
            entry_point.load()
        except Exception as exc:
            _LOGGER.warning("Failed to load external software plugin %r", entry_point.name, exc_info=True)
            DISCOVERY_DIAGNOSTICS.append(
                f"failed external software plugin {entry_point.name!r}: {exc}"
            )
        else:
            _LOGGER.info("Loaded external software plugin %r", entry_point.name)
    _EXTERNAL_DISCOVERED = True


discover_plugins()


def plugin_names() -> list[str]:
    return [definition.name for definition in active_definitions()]


__all__ = [
    "DISCOVERY_DIAGNOSTICS",
    "SoftwareDefinition",
    "active_definitions",
    "all_definitions",
    "detect_from_text",
    "discover_plugins",
    "get_definition",
    "plugin_names",
    "set_enabled_plugin_ids",
]
