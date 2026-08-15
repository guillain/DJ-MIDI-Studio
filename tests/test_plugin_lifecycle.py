from djmidi.plugins import PluginManager, PluginManifest


def _manifest(plugin_id: str = "example.controller") -> PluginManifest:
    return PluginManifest(
        plugin_id=plugin_id,
        kind="controller",
        name="Example",
        version="1.0.0",
        api_version="1",
        vendor="Example",
        license="MIT",
    )


def test_plugin_manager_discovers_and_toggles_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(_manifest().to_json(), encoding="utf-8")
    manager = PluginManager()
    assert len(manager.discover([path])) == 1
    manager.disable("example.controller")
    assert manager.enabled_manifests() == ()
    manager.enable("example.controller")
    assert len(manager.enabled_manifests()) == 1


def test_plugin_manager_reports_duplicate_ids():
    manager = PluginManager()
    assert manager.register(_manifest())
    assert not manager.register(_manifest(), source="external")
    assert "duplicate plugin_id" in manager.diagnostics[0].message


def test_plugin_manager_reports_api_and_application_compatibility():
    manager = PluginManager(application_version="1.0.0", api_version="2")
    assert not manager.register(_manifest(), source="api-plugin")
    assert "incompatible API version" in manager.diagnostics[0].message
    manager = PluginManager(application_version="1.0.0")
    assert not manager.register(
        PluginManifest(
            plugin_id="future.plugin",
            kind="software",
            name="Future",
            version="1.0.0",
            api_version="1",
            vendor="Example",
            license="MIT",
            min_app_version="2.0.0",
        ),
        source="future-plugin",
    )
    assert "requires application" in manager.diagnostics[0].message
