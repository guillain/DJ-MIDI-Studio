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


def test_preferences_dialog_saves_theme_choice():
    preferences = PluginPreferences()
    dialog = PreferencesDialog(preferences)
    dialog._theme.setCurrentIndex(dialog._theme.findData("light"))
    dialog._save()
    assert preferences.theme == "light"


def test_preferences_dialog_reflects_and_saves_auto_start_live_monitor():
    preferences = PluginPreferences(auto_start_live_monitor=True)
    dialog = PreferencesDialog(preferences)
    assert dialog._auto_start_live_monitor.isChecked() is True
    dialog._auto_start_live_monitor.setChecked(False)
    dialog._save()
    assert preferences.auto_start_live_monitor is False


def test_controller_sync_tab_edits_port_and_removes_sets(monkeypatch):
    from djmidi.controller_sync import ControllerSyncSet, SyncMessage
    from djmidi.gui import preferences_dialog

    monkeypatch.setattr(preferences_dialog, "list_output_ports", lambda: ["PIONEER DDJ-XP2", "XDJ-XZ"])
    preferences = PluginPreferences()
    preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127),)))
    preferences.set_sync_set(ControllerSyncSet("XDJ-XZ", "Old port", ()))
    dialog = PreferencesDialog(preferences)

    assert dialog._sync_table.rowCount() == 2
    assert dialog._sync_table.item(0, 2).text() == "1"
    xp2_combo = dialog._sync_table.cellWidget(0, 1)
    assert xp2_combo.currentData() == ""  # auto
    xz_combo = dialog._sync_table.cellWidget(1, 1)
    assert xz_combo.currentText() == "Old port (not connected)"

    xp2_combo.setCurrentIndex(xp2_combo.findData("PIONEER DDJ-XP2"))
    dialog._sync_table.selectRow(1)
    dialog._remove_selected_sync_set()
    dialog._save()

    assert [s.controller for s in preferences.controller_sync_sets] == ["DDJ-XP2"]
    assert preferences.controller_sync_sets[0].output_port == "PIONEER DDJ-XP2"
    assert len(preferences.controller_sync_sets[0].messages) == 1


def test_preferences_dialog_reflects_and_saves_controller_setup_default_file():
    preferences = PluginPreferences(controller_setup_default_file="/a/b.json")
    dialog = PreferencesDialog(preferences)
    assert dialog._setup_file.text() == "/a/b.json"
    dialog._setup_file.setText("  /c/d.xml  ")
    dialog._save()
    assert preferences.controller_setup_default_file == "/c/d.xml"
