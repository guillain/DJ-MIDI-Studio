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
