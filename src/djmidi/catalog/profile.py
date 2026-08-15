"""Load declarative controller plugins from validated JSON profiles."""

from __future__ import annotations

import json
from pathlib import Path

from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register
from djmidi.plugins import PluginManifest


def load_controller_profile(path: str | Path, *, replace: bool = False) -> ControllerDefinition:
    """Validate and register a controller profile stored as JSON.

    The profile format deliberately covers static NOTE/CC entries only. Pad
    formulas and software-specific behavior remain Python plugin capabilities.
    """
    profile_path = Path(path)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid controller profile JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise TypeError("Controller profile must be a JSON object")
    manifest = PluginManifest.from_mapping(raw.get("manifest"))
    if manifest.kind != "controller":
        raise ValueError(f"Profile manifest kind must be 'controller', got {manifest.kind!r}")
    controller = raw.get("controller")
    if not isinstance(controller, dict):
        raise TypeError("Controller profile must contain a 'controller' object")
    name = _required_text(controller, "name")
    if name != manifest.name:
        raise ValueError("Controller profile name must match manifest name")
    entries_raw = controller.get("entries")
    if not isinstance(entries_raw, list):
        raise TypeError("Controller profile 'entries' must be a list")
    entries = [_entry_from_mapping(name, entry) for entry in entries_raw]
    definition = ControllerDefinition(
        name=name,
        plugin_id=manifest.plugin_id,
        manufacturer=manifest.vendor,
        supported_software=tuple(_string_list(controller.get("supported_software", ()), "supported_software")),
        reference_image=controller.get("reference_image"),
        display_order=int(controller.get("display_order", 100)),
        static_entries=entries,
        section_order=tuple(dict.fromkeys(entry.section for entry in entries)),
    )
    register(definition, replace=replace)
    return definition


def _entry_from_mapping(controller: str, raw: object) -> ControlInfo:
    if not isinstance(raw, dict):
        raise TypeError("Each controller profile entry must be a JSON object")
    section = _required_text(raw, "section")
    name = _required_text(raw, "name")
    note_or_cc = _required_text(raw, "note_or_cc")
    if note_or_cc not in ("NOTE", "CC"):
        raise ValueError(f"Entry note_or_cc must be NOTE or CC, got {note_or_cc!r}")
    data1 = _required_text(raw, "data1")
    channels = _string_list(raw.get("channels"), "channels")
    if not channels:
        raise ValueError("Entry channels must not be empty")
    return ControlInfo(controller, section, name, note_or_cc, tuple(channels), data1)


def _required_text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Profile field {key!r} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"Profile field {field_name!r} must be a list of non-empty strings")
    return [item.strip() for item in value]


__all__ = ["load_controller_profile"]
