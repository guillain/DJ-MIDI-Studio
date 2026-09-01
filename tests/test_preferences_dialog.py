from PySide6.QtWidgets import QDialog

from djmidi.gui.preferences_dialog import PreferencesDialog
from djmidi.plugins import PluginPreferences


def test_preferences_dialog_saves_policy_and_dynamic_plugins():
    preferences = PluginPreferences()
    dialog = PreferencesDialog(preferences)
    dialog._detection.setCurrentIndex(1)
    dialog._routing.setChecked(True)
    dialog._log_level.setCurrentText("DEBUG")
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert preferences.detection_policy == "suggest"
    assert preferences.routing_enabled
    assert preferences.log_level == "DEBUG"
    assert "serato" in preferences.enabled


def test_disable_all_controllers_button_unchecks_only_controllers():
    from djmidi import catalog

    preferences = PluginPreferences()
    dialog = PreferencesDialog(preferences)
    dialog._set_all_controllers(False)
    dialog._save()

    controller_ids = {
        definition.plugin_id or definition.name
        for definition in catalog.all_controller_definitions()
    }
    assert controller_ids, "expected at least one built-in controller"
    assert all(preferences.is_enabled(cid) is False for cid in controller_ids)
    # Software plugins are untouched by the controller-only button.
    assert preferences.is_enabled("serato") is True


def test_enable_all_controllers_button_rechecks_them():
    from djmidi import catalog

    preferences = PluginPreferences()
    dialog = PreferencesDialog(preferences)
    dialog._set_all_controllers(False)
    dialog._set_all_controllers(True)
    dialog._save()

    controller_ids = {
        definition.plugin_id or definition.name
        for definition in catalog.all_controller_definitions()
    }
    assert all(preferences.is_enabled(cid) for cid in controller_ids)
