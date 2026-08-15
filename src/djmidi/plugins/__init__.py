"""Shared primitives for discoverable DJ MIDI Studio plugins."""

from djmidi.plugins.lifecycle import PluginDiagnostic, PluginManager
from djmidi.plugins.manifest import (
    MANIFEST_SCHEMA_VERSION,
    PluginManifest,
    read_manifest,
)
from djmidi.plugins.preferences import PluginPreferences

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "PluginDiagnostic",
    "PluginManager",
    "PluginManifest",
    "PluginPreferences",
    "read_manifest",
]
