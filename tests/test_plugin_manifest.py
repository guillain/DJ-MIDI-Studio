import pytest

from djmidi.plugins import PluginManifest


def test_manifest_round_trips_as_json():
    manifest = PluginManifest(
        plugin_id="example.controller",
        kind="controller",
        name="Example Controller",
        version="1.2.0",
        api_version="1",
        vendor="Example",
        license="MIT",
        capabilities=("midi.input", "catalog.lookup"),
        permissions=("midi.read",),
    )
    restored = PluginManifest.from_json(manifest.to_json())
    assert restored == manifest


def test_manifest_rejects_unknown_schema_and_invalid_id():
    with pytest.raises(ValueError, match="schema version"):
        PluginManifest.from_mapping(
            {
                "schema_version": 99,
                "plugin_id": "example.controller",
                "kind": "controller",
                "name": "Example",
                "version": "1.0.0",
                "api_version": "1",
                "vendor": "Example",
                "license": "MIT",
            }
        )
    with pytest.raises(ValueError, match="plugin_id"):
        PluginManifest.from_mapping(
            {
                "plugin_id": "Not A Valid ID",
                "kind": "controller",
                "name": "Example",
                "version": "1.0.0",
                "api_version": "1",
                "vendor": "Example",
                "license": "MIT",
            }
        )
