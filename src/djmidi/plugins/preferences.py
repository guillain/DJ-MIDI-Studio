"""Small persistent preference store for plugin enablement.

The store is intentionally independent of Qt so discovery, CLI tools and GUI
tests use the same contract.  Registries can consult ``is_enabled`` before
activating an integration; unknown IDs are retained so preferences survive a
plugin update or temporary uninstall.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PluginPreferences:
    enabled: dict[str, bool] = field(default_factory=dict)

    def is_enabled(self, plugin_id: str) -> bool:
        return self.enabled.get(plugin_id, True)

    def set_enabled(self, plugin_id: str, value: bool) -> None:
        if not plugin_id.strip():
            raise ValueError("plugin_id cannot be empty")
        self.enabled[plugin_id] = bool(value)

    def disable(self, plugin_id: str) -> None:
        self.set_enabled(plugin_id, False)

    def enable(self, plugin_id: str) -> None:
        self.set_enabled(plugin_id, True)

    def to_json(self) -> str:
        return json.dumps({"enabled": self.enabled}, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> PluginPreferences:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid plugin preferences JSON: {exc.msg}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("enabled", {}), dict):
            raise TypeError("Plugin preferences must contain an 'enabled' object")
        if not all(isinstance(key, str) and isinstance(value, bool) for key, value in raw["enabled"].items()):
            raise ValueError("Plugin preference values must be booleans")
        return cls(enabled=dict(raw["enabled"]))

    @classmethod
    def load(cls, path: str | Path) -> PluginPreferences:
        target = Path(path)
        if not target.exists():
            return cls()
        return cls.from_json(target.read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")


__all__ = ["PluginPreferences"]
