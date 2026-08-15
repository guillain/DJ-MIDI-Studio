"""Discoverable DJ software mapping plugins."""

from __future__ import annotations

import importlib
import importlib.metadata
import pkgutil

from djmidi.software._registry import (
    SoftwareDefinition,
    all_definitions,
    detect_from_text,
    get_definition,
)

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
    if _EXTERNAL_DISCOVERED:
        return
    entry_points = importlib.metadata.entry_points(group="djmidi.software")
    if not trust_external:
        DISCOVERY_DIAGNOSTICS.extend(
            f"blocked external software plugin {entry_point.name!r}: trust is disabled"
            for entry_point in entry_points
        )
        return
    for entry_point in entry_points:
        try:
            entry_point.load()
        except Exception as exc:  # noqa: BLE001 - external plugin failures become diagnostics
            DISCOVERY_DIAGNOSTICS.append(
                f"failed external software plugin {entry_point.name!r}: {exc}"
            )
    _EXTERNAL_DISCOVERED = True


discover_plugins()


def plugin_names() -> list[str]:
    return [definition.name for definition in all_definitions()]


__all__ = [
    "DISCOVERY_DIAGNOSTICS",
    "SoftwareDefinition",
    "all_definitions",
    "detect_from_text",
    "discover_plugins",
    "get_definition",
    "plugin_names",
]
