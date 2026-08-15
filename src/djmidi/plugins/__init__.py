"""Shared primitives for discoverable DJ MIDI Studio plugins."""

from djmidi.plugins.lifecycle import PluginDiagnostic, PluginManager
from djmidi.plugins.manifest import (
    MANIFEST_SCHEMA_VERSION,
    PluginManifest,
    read_manifest,
)
from djmidi.plugins.preferences import (
    DetectionPolicy,
    PluginPreferences,
    default_preferences_path,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "DetectionPolicy",
    "PluginDiagnostic",
    "PluginManager",
    "PluginManifest",
    "PluginPreferences",
    "default_preferences_path",
    "read_manifest",
]
