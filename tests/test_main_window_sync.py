from PySide6.QtWidgets import QMessageBox

from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.gui import main_window as main_window_module
from djmidi.gui.main_window import MainWindow
from djmidi.plugins import PluginPreferences


def _window(tmp_path):
    window = MainWindow()
    window.preferences = PluginPreferences()
    window.preferences_path = tmp_path / "preferences.json"
    return window


def test_sync_without_sets_explains_how_to_record(tmp_path, monkeypatch):
    window = _window(tmp_path)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[2]))
    assert window._on_sync_controllers() == []
    assert "Controller Setup" in shown[0]


def test_sync_sends_stored_sets_to_connected_ports(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127),)))
    window.preferences.set_sync_set(ControllerSyncSet("XDJ-XZ", "", ()))
    sent = []
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: ["PIONEER DDJ-XP2"])
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs))

    results = window._on_sync_controllers()

    assert [(r.controller, r.ok) for r in results] == [("DDJ-XP2", True), ("XDJ-XZ", False)]
    assert sent[0]["output_port_name"] == "PIONEER DDJ-XP2"
    assert window.statusBar().currentMessage().startswith("Synced 1/2 controller(s)")


def test_live_monitor_sync_button_triggers_main_window_sync(tmp_path, monkeypatch):
    window = _window(tmp_path)
    calls = []
    monkeypatch.setattr(main_window_module, "run_sync", lambda sets, ports: calls.append(sets) or [])
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", ()))
    window.live_monitor_view._sync_button.click()
    assert len(calls) == 1


def test_saving_a_sync_set_persists_it_and_confirms_replacement(tmp_path, monkeypatch):
    window = _window(tmp_path)
    first = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127),))
    window.controller_setup_view.syncSetSaveRequested.emit(first)
    assert PluginPreferences.load(window.preferences_path).controller_sync_sets == [first]

    replacement = ControllerSyncSet("DDJ-XP2", "", ())
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    window._on_sync_set_save_requested(replacement)
    assert window.preferences.sync_set_for("DDJ-XP2") == first

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window._on_sync_set_save_requested(replacement)
    assert PluginPreferences.load(window.preferences_path).sync_set_for("DDJ-XP2") == replacement
