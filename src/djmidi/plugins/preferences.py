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

from djmidi.controller_sync import (
    DEFAULT_SCENE,
    ControllerSyncSet,
    normalize_scene,
    sets_for_scene,
)

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
    auto_start_live_monitor: bool = True
    # Reopen the last mapping and Controller Setup draft at launch (issue #175).
    reopen_last_files: bool = True
    # Send every stored controller sync set once at launch (Record → auto-play).
    auto_sync_on_startup: bool = True
    # Send a controller its sync set when its output port appears (issue #183).
    auto_sync_on_plug_in: bool = True
    # Look for a newer GitHub release at launch, at most once a day (issue #193).
    check_for_updates: bool = True
    # Session JSON or Serato XML Controller Setup loads when first shown ("" = none).
    controller_setup_default_file: str = ""
    # One-click "Sync" sets, at most one per (controller, scene) (see controller_sync).
    controller_sync_sets: list[ControllerSyncSet] = field(default_factory=list)
    # The scene ⟳ Sync, launch and plug-in sync send (issue #188).
    active_sync_scene: str = DEFAULT_SCENE

    def sync_set_for(self, controller: str, scene: str = DEFAULT_SCENE) -> ControllerSyncSet | None:
        """The set stored for exactly that controller and scene (no fallback)."""
        key = (controller, normalize_scene(scene))
        return next((s for s in self.controller_sync_sets if s.key == key), None)

    def set_sync_set(self, sync_set: ControllerSyncSet) -> None:
        """Adds or replaces (keeping its position) the set for that controller and scene."""
        for index, existing in enumerate(self.controller_sync_sets):
            if existing.key == sync_set.key:
                self.controller_sync_sets[index] = sync_set
                return
        self.controller_sync_sets.append(sync_set)

    def remove_sync_set(self, controller: str, scene: str | None = None) -> None:
        """Removes that controller's set for ``scene``, or all its sets when ``scene`` is None."""
        self.controller_sync_sets = [
            s
            for s in self.controller_sync_sets
            if not (s.controller == controller and (scene is None or s.scene == normalize_scene(scene)))
        ]

    def active_sync_sets(self) -> list[ControllerSyncSet]:
        """What a Sync sends now: each controller's set for the active scene,
        else its default-scene set (``controller_sync.sets_for_scene``)."""
        return sets_for_scene(self.controller_sync_sets, self.active_sync_scene)

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
                "auto_start_live_monitor": self.auto_start_live_monitor,
                "reopen_last_files": self.reopen_last_files,
                "auto_sync_on_startup": self.auto_sync_on_startup,
                "auto_sync_on_plug_in": self.auto_sync_on_plug_in,
                "check_for_updates": self.check_for_updates,
                "controller_setup_default_file": self.controller_setup_default_file,
                "controller_sync_sets": [sync_set.to_dict() for sync_set in self.controller_sync_sets],
                "active_sync_scene": self.active_sync_scene,
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
        raw_sync_sets = raw.get("controller_sync_sets", [])
        if not isinstance(raw_sync_sets, list):
            raise TypeError("controller_sync_sets must be a list")
        sync_sets: dict[tuple[str, str], ControllerSyncSet] = {}
        for raw_set in raw_sync_sets:
            sync_set = ControllerSyncSet.from_dict(raw_set)
            sync_sets[sync_set.key] = sync_set  # one per (controller, scene): last wins
        return cls(
            enabled=dict(raw["enabled"]),
            detection_policy=detection_policy,
            routing_enabled=bool(raw.get("routing_enabled", False)),
            trust_external_plugins=bool(raw.get("trust_external_plugins", False)),
            log_level=log_level.upper(),
            log_path=str(raw.get("log_path", "")),
            theme=theme,
            auto_start_live_monitor=bool(raw.get("auto_start_live_monitor", True)),
            reopen_last_files=bool(raw.get("reopen_last_files", True)),
            auto_sync_on_startup=bool(raw.get("auto_sync_on_startup", True)),
            auto_sync_on_plug_in=bool(raw.get("auto_sync_on_plug_in", True)),
            check_for_updates=bool(raw.get("check_for_updates", True)),
            controller_setup_default_file=str(raw.get("controller_setup_default_file", "")),
            controller_sync_sets=list(sync_sets.values()),
            active_sync_scene=normalize_scene(raw.get("active_sync_scene")),
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
            "Saved preferences to %s (detection_policy=%s, routing_enabled=%s, trust_external_plugins=%s, "
            "log_level=%s, log_path=%s, theme=%s, auto_start_live_monitor=%s, controller_sync_sets=%d)",
            target,
            self.detection_policy,
            self.routing_enabled,
            self.trust_external_plugins,
            self.log_level,
            self.log_path or "(default)",
            self.theme,
            self.auto_start_live_monitor,
            len(self.controller_sync_sets),
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
