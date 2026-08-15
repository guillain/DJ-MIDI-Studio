from djmidi.plugins import PluginPreferences


def test_plugin_preferences_default_to_enabled_and_round_trip(tmp_path):
    preferences = PluginPreferences()
    assert preferences.is_enabled("new.plugin")
    preferences.disable("new.plugin")
    path = tmp_path / "plugins.json"
    preferences.save(path)
    restored = PluginPreferences.load(path)
    assert not restored.is_enabled("new.plugin")
    restored.enable("new.plugin")
    assert restored.is_enabled("new.plugin")


def test_plugin_preferences_round_trip_integration_policies(tmp_path):
    preferences = PluginPreferences(
        detection_policy="suggest",
        routing_enabled=True,
        trust_external_plugins=True,
        log_level="DEBUG",
    )
    path = tmp_path / "policies.json"
    preferences.save(path)
    restored = PluginPreferences.load(path)
    assert restored.detection_policy == "suggest"
    assert restored.routing_enabled
    assert restored.trust_external_plugins
    assert restored.log_level == "DEBUG"
