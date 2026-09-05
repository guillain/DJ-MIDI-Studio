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


def test_plugin_preferences_log_path_defaults_empty_and_round_trips(tmp_path):
    preferences = PluginPreferences()
    assert preferences.log_path == ""
    preferences.log_path = str(tmp_path / "custom.log")
    path = tmp_path / "prefs.json"
    preferences.save(path)
    restored = PluginPreferences.load(path)
    assert restored.log_path == str(tmp_path / "custom.log")


def test_plugin_preferences_from_json_defaults_missing_log_path_to_empty():
    restored = PluginPreferences.from_json('{"enabled": {}}')
    assert restored.log_path == ""


def test_plugin_preferences_theme_defaults_to_system_and_round_trips(tmp_path):
    preferences = PluginPreferences()
    assert preferences.theme == "system"
    preferences.theme = "light"
    path = tmp_path / "theme.json"
    preferences.save(path)
    assert PluginPreferences.load(path).theme == "light"


def test_plugin_preferences_from_json_defaults_missing_theme_to_system():
    assert PluginPreferences.from_json('{"enabled": {}}').theme == "system"


def test_plugin_preferences_from_json_rejects_unknown_theme():
    import pytest

    with pytest.raises(ValueError, match="theme"):
        PluginPreferences.from_json('{"enabled": {}, "theme": "neon"}')


def test_plugin_preferences_auto_start_live_monitor_defaults_true_and_round_trips(tmp_path):
    preferences = PluginPreferences()
    assert preferences.auto_start_live_monitor is True
    preferences.auto_start_live_monitor = False
    path = tmp_path / "auto_start.json"
    preferences.save(path)
    assert PluginPreferences.load(path).auto_start_live_monitor is False


def test_plugin_preferences_from_json_defaults_missing_auto_start_live_monitor_to_true():
    assert PluginPreferences.from_json('{"enabled": {}}').auto_start_live_monitor is True
