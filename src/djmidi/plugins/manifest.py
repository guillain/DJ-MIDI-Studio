"""Versioned, JSON-serializable plugin manifest contract."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

MANIFEST_SCHEMA_VERSION = 1
_PLUGIN_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
PluginKind = Literal["controller", "software"]


@dataclass(frozen=True)
class PluginManifest:
    """Metadata required before a plugin is allowed to load."""

    plugin_id: str
    kind: PluginKind
    name: str
    version: str
    api_version: str
    vendor: str
    license: str
    min_app_version: str = "0.1.0"
    capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    schema_version: int = MANIFEST_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, raw: object) -> PluginManifest:
        if not isinstance(raw, dict):
            raise TypeError("Plugin manifest must be a JSON object")
        required = ("plugin_id", "kind", "name", "version", "api_version", "vendor", "license")
        missing = [key for key in required if not isinstance(raw.get(key), str) or not raw[key].strip()]
        if missing:
            raise ValueError(f"Plugin manifest missing required fields: {', '.join(missing)}")
        schema_version = raw.get("schema_version", MANIFEST_SCHEMA_VERSION)
        if schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported plugin manifest schema version: {schema_version!r}")
        plugin_id = raw["plugin_id"]
        if not _PLUGIN_ID.fullmatch(plugin_id):
            raise ValueError(f"Invalid plugin_id: {plugin_id!r}")
        if raw["kind"] not in ("controller", "software"):
            raise ValueError(f"Invalid plugin kind: {raw['kind']!r}")
        capabilities = _string_tuple(raw.get("capabilities", ()), "capabilities")
        permissions = _string_tuple(raw.get("permissions", ()), "permissions")
        return cls(
            plugin_id=plugin_id,
            kind=raw["kind"],
            name=raw["name"].strip(),
            version=raw["version"].strip(),
            api_version=raw["api_version"].strip(),
            vendor=raw["vendor"].strip(),
            license=raw["license"].strip(),
            min_app_version=str(raw.get("min_app_version", "0.1.0")).strip(),
            capabilities=capabilities,
            permissions=permissions,
            schema_version=schema_version,
        )

    @classmethod
    def from_json(cls, text: str) -> PluginManifest:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid plugin manifest JSON: {exc.msg}") from exc
        return cls.from_mapping(raw)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"Plugin manifest field {field_name!r} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def read_manifest(path: str | Path) -> PluginManifest:
    return PluginManifest.from_json(Path(path).read_text(encoding="utf-8"))


__all__ = ["MANIFEST_SCHEMA_VERSION", "PluginKind", "PluginManifest", "read_manifest"]
