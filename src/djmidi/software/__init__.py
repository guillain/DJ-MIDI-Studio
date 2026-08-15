"""Discoverable DJ software mapping plugins."""

from __future__ import annotations

import importlib
import pkgutil

from djmidi.software._registry import (
    SoftwareDefinition,
    all_definitions,
    get_definition,
)

_DISCOVERED = False


def discover_plugins() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module_info.name}")


discover_plugins()


def plugin_names() -> list[str]:
    return [definition.name for definition in all_definitions()]


__all__ = ["SoftwareDefinition", "all_definitions", "discover_plugins", "get_definition", "plugin_names"]
