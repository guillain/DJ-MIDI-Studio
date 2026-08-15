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
