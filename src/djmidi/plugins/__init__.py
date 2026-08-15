"""Shared primitives for discoverable DJ MIDI Studio plugins."""

from djmidi.plugins.manifest import (
    MANIFEST_SCHEMA_VERSION,
    PluginManifest,
    read_manifest,
)

__all__ = ["MANIFEST_SCHEMA_VERSION", "PluginManifest", "read_manifest"]
