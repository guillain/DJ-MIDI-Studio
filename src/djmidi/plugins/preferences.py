"""Small persistent preference store for plugin enablement.

The store is intentionally independent of Qt so discovery, CLI tools and GUI
tests use the same contract.  Registries can consult ``is_enabled`` before
activating an integration; unknown IDs are retained so preferences survive a
plugin update or temporary uninstall.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_LOGGER = logging.getLogger(__name__)

DetectionPolicy = Literal["ask", "suggest"]
ThemeMode = Literal["system", "light", "dark"]
_THEME_MODES = ("system", "light", "dark")


@dataclass
class PluginPreferences:
    enabled: dict[str, bool] = field(default_factory=dict)
    detection_policy: DetectionPolicy = "ask"
    routing_enabled: bool = False
    trust_external_plugins: bool = False
    log_level: str = "INFO"
    log_path: str = ""
    theme: ThemeMode = "system"

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
        return json.dumps(
            {
                "enabled": self.enabled,
                "detection_policy": self.detection_policy,
                "routing_enabled": self.routing_enabled,
                "trust_external_plugins": self.trust_external_plugins,
                "log_level": self.log_level,
                "log_path": self.log_path,
                "theme": self.theme,
            },
            indent=2,
            sort_keys=True,
        ) + "\n"

    @classmethod
    def from_json(cls, text: str) -> PluginPreferences:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            _LOGGER.warning("Invalid plugin preferences JSON: %s", exc.msg)
            raise ValueError(f"Invalid plugin preferences JSON: {exc.msg}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("enabled", {}), dict):
            raise TypeError("Plugin preferences must contain an 'enabled' object")
        if not all(isinstance(key, str) and isinstance(value, bool) for key, value in raw["enabled"].items()):
            raise ValueError("Plugin preference values must be booleans")
        detection_policy = raw.get("detection_policy", "ask")
        if detection_policy not in ("ask", "suggest"):
            raise ValueError("detection_policy must be 'ask' or 'suggest'")
        log_level = raw.get("log_level", "INFO")
        if not isinstance(log_level, str) or log_level.upper() not in {
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }:
            raise ValueError("log_level is not supported")
        theme = raw.get("theme", "system")
        if theme not in _THEME_MODES:
            raise ValueError("theme must be 'system', 'light', or 'dark'")
        return cls(
            enabled=dict(raw["enabled"]),
            detection_policy=detection_policy,
            routing_enabled=bool(raw.get("routing_enabled", False)),
            trust_external_plugins=bool(raw.get("trust_external_plugins", False)),
            log_level=log_level.upper(),
            log_path=str(raw.get("log_path", "")),
            theme=theme,
        )

    @classmethod
    def load(cls, path: str | Path) -> PluginPreferences:
        target = Path(path)
        if not target.exists():
            _LOGGER.info("No preferences file at %s; using defaults", target)
            return cls()
        _LOGGER.info("Loading preferences from %s", target)
        return cls.from_json(target.read_text(encoding="utf-8"))

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")
        _LOGGER.info(
            "Saved preferences to %s (detection_policy=%s, routing_enabled=%s, trust_external_plugins=%s, log_level=%s, log_path=%s, theme=%s)",
            target,
            self.detection_policy,
            self.routing_enabled,
            self.trust_external_plugins,
            self.log_level,
            self.log_path or "(default)",
            self.theme,
        )


def default_preferences_path() -> Path:
    override = os.environ.get("DJMIDI_PREFERENCES_FILE")
    if override:
        return Path(override)
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Preferences" / "DJ-MIDI-Studio" / "preferences.json"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "DJ-MIDI-Studio" / "preferences.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "djmidi" / "preferences.json"


__all__ = ["DetectionPolicy", "PluginPreferences", "ThemeMode", "default_preferences_path"]
