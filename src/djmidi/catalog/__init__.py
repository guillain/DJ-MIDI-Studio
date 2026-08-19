"""Reference tables mapping raw MIDI (channel, NOTE/CC, data1) triples to
physical control names, one module per controller (see ddj_xp2.py, xdj_xz.py),
registered into a small plugin-style registry (_registry.py).

Scope (per controller): discrete press/toggle controls (buttons, pad grids),
which are what Serato MIDI configs actually remap. Continuous controls
(faders, TRIM/EQ knobs, jog wheels, touch strips/encoders) are intentionally
left out — they're rarely remapped and their value ranges don't reduce to a
single readable name.

To add a new controller (e.g. a Behringer CMD LC-1 or a generic "miniPad"):

1. Get the device's MIDI message list (manufacturer PDF/manual, or transcribe
   from the device itself) — channel numbers, NOTE/CC, and data1 per control.
2. Create `catalog/<your_controller>.py` modeled on `ddj_xp2.py` (bespoke pad
   note order) or `xdj_xz.py` (still bespoke here, but simpler): a
   `_STATIC: list[ControlInfo]` for named buttons, and if there's a pad grid,
   either a bespoke `_pad_lookup` function or — if the notes are laid out
   sequentially per mode (pad N at note (N-1) + mode_index*16) —
   `_registry.make_sequential_pad_lookup(...)`, which covers that common case
   without writing a formula by hand.
3. End the module with `register(ControllerDefinition(name=..., static_entries=_STATIC,
   pad_lookup=..., pad_count=..., pad_columns=..., section_order=(...)))`.
   `pad_count=0` (the default) is fine for a controller with no pad grid at all.
4. Put that module in this package or expose it through the
   `djmidi.controllers` entry-point group. Discovery imports it automatically;
   `CONTROLLER_NAMES`, the Layout/Controller-tree/Controller-image tabs'
   controller combos, and `lookup()` all pick it up automatically.
5. Optional: set `reference_image` and drop a cropped reference image at
   `assets/controllers/<name>.png` (the image view falls back to a "not found"
   placeholder if there isn't one yet).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import pkgutil

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    ControllerMatch,
    NoteOrCC,
    _event_kind,
    active_controller_definitions,
    active_controller_names,
    all_controller_definitions,
    detect_controller,
    get_definition,
    make_sequential_pad_lookup,
    register,
    set_enabled_plugin_ids,
)

_LOGGER = logging.getLogger(__name__)

_BUILTINS_DISCOVERED = False
_EXTERNAL_DISCOVERED = False
DISCOVERY_DIAGNOSTICS: list[str] = []


def discover_plugins(*, trust_external: bool = False) -> None:
    """Discovers built-in and installed controller plugins.

    Built-ins are ordinary modules in this package and register themselves on
    import. Installed integrations may expose a module/function through the
    ``djmidi.controllers`` entry-point group. Discovery is idempotent so GUI
    consumers can safely refresh after installing or enabling an integration.
    """
    global _BUILTINS_DISCOVERED, _EXTERNAL_DISCOVERED
    if not _BUILTINS_DISCOVERED:
        _BUILTINS_DISCOVERED = True
        for module_info in pkgutil.iter_modules(__path__):
            if module_info.name.startswith("_") or module_info.name in {"codegen"}:
                continue
            importlib.import_module(f"{__name__}.{module_info.name}")
        _LOGGER.info("Discovered %d built-in controller catalog(s)", len(all_controller_definitions()))
    if _EXTERNAL_DISCOVERED:
        return
    entry_points = importlib.metadata.entry_points(group="djmidi.controllers")
    if not trust_external:
        if entry_points:
            _LOGGER.info(
                "Blocked %d external controller plugin(s) (trust_external=False): %s",
                len(entry_points),
                [entry_point.name for entry_point in entry_points],
            )
        DISCOVERY_DIAGNOSTICS.extend(
            f"blocked external controller plugin {entry_point.name!r}: trust is disabled"
            for entry_point in entry_points
        )
        return
    for entry_point in entry_points:
        try:
            entry_point.load()
        except Exception as exc:
            _LOGGER.warning("Failed to load external controller plugin %r", entry_point.name, exc_info=True)
            DISCOVERY_DIAGNOSTICS.append(
                f"failed external controller plugin {entry_point.name!r}: {exc}"
            )
        else:
            _LOGGER.info("Loaded external controller plugin %r", entry_point.name)
    _EXTERNAL_DISCOVERED = True


discover_plugins()


def __getattr__(name: str) -> object:
    # PEP 562: computed fresh from the live registry on every access (not a
    # snapshot taken at import time), so a controller registered after this
    # package was imported — e.g. interactively, or by a future plugin
    # mechanism — is still picked up by every consumer of these two names.
    if name == "CONTROLLER_NAMES":
        return active_controller_names()
    if name == "PAD_COUNTS":
        return {n: get_definition(n).pad_count for n in active_controller_names()}
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def static_entries(controller: str) -> list[ControlInfo]:
    return list(get_definition(controller).static_entries)


def lookup(channel: str | None, event_type: str | None, data1: str | None) -> list[ControlInfo]:
    """Returns every known physical control matching this (channel, event_type, data1)
    triple, across *every registered controller* (a config file mixing controllers
    doesn't self-identify which one sent a given message, so all are always checked)."""
    if not channel or not data1:
        return []
    kind = _event_kind(event_type)
    if kind is None:
        return []
    results: list[ControlInfo] = []
    for name in active_controller_names():
        definition = get_definition(name)
        results.extend(
            entry
            for entry in definition.static_entries
            if entry.note_or_cc == kind and channel in entry.channels and entry.data1 == data1
        )
        if definition.pad_lookup is not None:
            found = definition.pad_lookup(channel, kind, data1)
            if found is not None:
                results.append(found)
    return results


__all__ = [
    "CONTROLLER_NAMES",
    "DISCOVERY_DIAGNOSTICS",
    "PAD_COUNTS",
    "ControlInfo",
    "ControllerDefinition",
    "ControllerMatch",
    "NoteOrCC",
    "active_controller_definitions",
    "active_controller_names",
    "all_controller_definitions",
    "detect_controller",
    "discover_plugins",
    "get_definition",
    "lookup",
    "make_sequential_pad_lookup",
    "register",
    "set_enabled_plugin_ids",
    "static_entries",
]
