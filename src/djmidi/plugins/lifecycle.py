"""Manifest lifecycle and diagnostics independent of plugin execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from djmidi.plugins.manifest import PluginManifest, read_manifest
from djmidi.plugins.preferences import PluginPreferences


@dataclass(frozen=True)
class PluginDiagnostic:
    source: str
    message: str


class PluginManager:
    """Discovers and validates manifests before an integration is enabled.

    Actual Python entry-point loading remains owned by the controller/software
    registries.  This manager is the common policy layer they can consult and
    is deliberately safe to use in CLI and hardware-free tests.
    """

    def __init__(self, preferences: PluginPreferences | None = None) -> None:
        self.preferences = preferences or PluginPreferences()
        self._manifests: dict[str, PluginManifest] = {}
        self.diagnostics: list[PluginDiagnostic] = []

    def register(self, manifest: PluginManifest, *, source: str = "built-in") -> bool:
        if manifest.plugin_id in self._manifests:
            self.diagnostics.append(
                PluginDiagnostic(source, f"duplicate plugin_id: {manifest.plugin_id}")
            )
            return False
        self._manifests[manifest.plugin_id] = manifest
        return True

    def discover(self, paths: list[str | Path]) -> list[PluginManifest]:
        discovered: list[PluginManifest] = []
        for path in paths:
            source = str(path)
            try:
                manifest = read_manifest(path)
            except (OSError, TypeError, ValueError) as exc:
                self.diagnostics.append(PluginDiagnostic(source, str(exc)))
                continue
            if self.register(manifest, source=source):
                discovered.append(manifest)
        return discovered

    def enable(self, plugin_id: str) -> None:
        self._require(plugin_id)
        self.preferences.enable(plugin_id)

    def disable(self, plugin_id: str) -> None:
        self._require(plugin_id)
        self.preferences.disable(plugin_id)

    def reload(self, plugin_id: str) -> PluginManifest:
        manifest = self._require(plugin_id)
        self._manifests[plugin_id] = PluginManifest.from_json(manifest.to_json())
        return self._manifests[plugin_id]

    def all_manifests(self) -> tuple[PluginManifest, ...]:
        return tuple(self._manifests.values())

    def enabled_manifests(self) -> tuple[PluginManifest, ...]:
        return tuple(
            manifest
            for manifest in self._manifests.values()
            if self.preferences.is_enabled(manifest.plugin_id)
        )

    def _require(self, plugin_id: str) -> PluginManifest:
        try:
            return self._manifests[plugin_id]
        except KeyError:
            raise ValueError(f"Unknown plugin: {plugin_id}") from None


__all__ = ["PluginDiagnostic", "PluginManager"]
