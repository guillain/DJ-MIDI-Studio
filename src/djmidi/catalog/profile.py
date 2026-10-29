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
        port_names=tuple(_string_list(controller.get("port_names", ()), "port_names")),
        reference_image=controller.get("reference_image"),
        display_order=int(controller.get("display_order", 100)),
        static_entries=entries,
        section_order=tuple(dict.fromkeys(entry.section for entry in entries)),
        marker_geometry=_geometry_from_mapping(controller.get("geometry", {})),
    )
    register(definition, replace=replace)
    return definition


SHAPES = ("rect", "circle")


def _geometry_from_mapping(raw: object) -> tuple[tuple[str, float, float, float, float, str, str], ...]:
    """A profile's ``"geometry"``: ``{label: {x, y, w, h, shape, color}}``,
    x/y/w/h fractions of the reference image in [0, 1]."""
    if not isinstance(raw, dict):
        raise TypeError("Profile 'geometry' must be an object")
    markers = []
    for label, box in raw.items():
        if not isinstance(label, str) or not label.strip() or not isinstance(box, dict):
            raise ValueError("Each profile 'geometry' entry must be a label and an object")
        try:
            x, y, w, h = (float(box[key]) for key in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Geometry of {label!r} needs numeric x, y, w, h") from exc
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
            raise ValueError(f"Geometry of {label!r} must be fractions of the image")
        shape = str(box.get("shape", "rect"))
        if shape not in SHAPES:
            raise ValueError(f"Geometry shape must be one of {SHAPES}")
        markers.append((label.strip(), x, y, w, h, shape, str(box.get("color", "#4a90d9"))))
    return tuple(markers)


def geometry_mapping(markers) -> dict[str, dict[str, object]]:
    """The JSON ``"geometry"`` object for ``ControllerDefinition.marker_geometry``."""
    return {
        label: {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4), "shape": shape, "color": color}
        for label, x, y, w, h, shape, color in markers
    }


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


USER_PLUGIN_PREFIX = "user."


def profile_document(definition: ControllerDefinition, *, vendor: str = "User", version: str = "1.0.0") -> dict:
    """The JSON document load_controller_profile() reads back, for a
    controller with static entries only (what Controller Setup builds)."""
    if definition.pad_lookup is not None:
        raise ValueError("A JSON profile can only hold static entries, not a pad formula")
    plugin_id = definition.plugin_id or USER_PLUGIN_PREFIX + _slug(definition.name)
    controller: dict[str, object] = {
        "name": definition.name,
        "entries": [
            {
                "section": entry.section,
                "name": entry.name,
                "note_or_cc": entry.note_or_cc,
                "channels": list(entry.channels),
                "data1": entry.data1,
            }
            for entry in definition.static_entries
        ],
    }
    if definition.supported_software:
        controller["supported_software"] = list(definition.supported_software)
    if definition.port_names:
        controller["port_names"] = list(definition.port_names)
    if definition.reference_image:
        controller["reference_image"] = definition.reference_image
    if definition.marker_geometry:
        controller["geometry"] = geometry_mapping(definition.marker_geometry)
    return {
        "manifest": {
            "schema_version": 1,
            "plugin_id": plugin_id,
            "kind": "controller",
            "name": definition.name,
            "version": version,
            "api_version": "1",
            "vendor": definition.manufacturer or vendor,
            "license": "user",
        },
        "controller": controller,
    }


def save_controller_profile(definition: ControllerDefinition, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile_document(definition), indent=2) + "\n", encoding="utf-8")
    return target


def load_user_profiles(directory: str | Path) -> tuple[list[str], dict[str, str]]:
    """Register every installed profile in `directory` (``*.json``).

    Returns the names loaded and, per file, why it wasn't. A profile reusing
    a built-in controller's name is skipped rather than allowed to replace
    the built-in. Re-running replaces the user's own profiles in place."""
    from djmidi.catalog._registry import _REGISTRY

    loaded: list[str] = []
    errors: dict[str, str] = {}
    folder = Path(directory)
    if not folder.is_dir():
        return loaded, errors
    for path in sorted(folder.glob("*.json")):
        try:
            name = json.loads(path.read_text(encoding="utf-8"))["manifest"]["name"]
            existing = _REGISTRY.get(name)
            if existing is not None and not (existing.plugin_id or "").startswith(USER_PLUGIN_PREFIX):
                errors[str(path)] = f"'{name}' is a built-in controller; the profile was not loaded"
                continue
            loaded.append(load_controller_profile(path, replace=True).name)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the others
            errors[str(path)] = f"{type(exc).__name__}: {exc}"
    return loaded, errors


def find_user_profile_file(name: str, directory: str | Path) -> Path | None:
    """The installed profile file holding `name`, or None."""
    folder = Path(directory)
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            if json.loads(path.read_text(encoding="utf-8"))["manifest"]["name"] == name:
                return path
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def save_profile_layout(path: str | Path, reference_image: str | None, markers) -> ControllerDefinition:
    """Writes a picture and its marker positions into an installed profile
    file, keeping everything else in it as is, then re-registers it."""
    target = Path(path)
    raw = json.loads(target.read_text(encoding="utf-8"))
    controller = raw["controller"]
    if reference_image:
        controller["reference_image"] = reference_image
    else:
        controller.pop("reference_image", None)
    if markers:
        controller["geometry"] = geometry_mapping(markers)
    else:
        controller.pop("geometry", None)
    target.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return load_controller_profile(target, replace=True)


def uninstall_user_profile(name: str, directory: str | Path) -> list[Path]:
    """Removes an installed profile: unregisters it and deletes every
    profile file in `directory` holding that name (a picture it came with
    is left alone). Returns the files deleted. Raises ``ValueError`` for a
    built-in controller, which has no file to remove."""
    from djmidi.catalog._registry import _REGISTRY

    existing = _REGISTRY.get(name)
    if existing is not None and not (existing.plugin_id or "").startswith(USER_PLUGIN_PREFIX):
        raise ValueError(f"'{name}' is a built-in controller")
    removed: list[Path] = []
    folder = Path(directory)
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            if json.loads(path.read_text(encoding="utf-8"))["manifest"]["name"] != name:
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        path.unlink()
        removed.append(path)
    _REGISTRY.pop(name, None)
    return removed


def _slug(name: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in name.lower()).strip("-") or "controller"


__all__ = [
    "SHAPES",
    "USER_PLUGIN_PREFIX",
    "find_user_profile_file",
    "geometry_mapping",
    "load_controller_profile",
    "load_user_profiles",
    "profile_document",
    "save_controller_profile",
    "save_profile_layout",
    "uninstall_user_profile",
]
