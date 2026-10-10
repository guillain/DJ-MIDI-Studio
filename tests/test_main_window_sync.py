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


class _FakeMonitor:
    def __init__(self, events):
        self.events = list(events)
        self.opened = []

    def open_input(self, name):
        if name == "Busy port":
            raise OSError("busy")
        self.opened.append(name)

    def poll(self):
        events, self.events = self.events, []
        return events

    def close_all(self):
        self.opened = []


def _event(port, data1, event_type="Note On"):
    from djmidi.midi_io import MidiEvent

    return MidiEvent("in", "1", event_type, str(data1), "127", 0.0, port)


def test_record_button_saves_one_sync_set_per_controller(tmp_path, monkeypatch):
    window = _window(tmp_path)
    monitor = _FakeMonitor([_event("PIONEER DDJ-XP2", 11), _event("Some Unknown Box", 3), _event("PIONEER DDJ-XP2", 12)])
    window._record_monitor = monitor
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2", "Busy port", "Some Unknown Box"])

    window._record_button.click()
    assert window._record_button.isChecked()
    assert monitor.opened == ["PIONEER DDJ-XP2", "Some Unknown Box"]
    window._record_button.click()

    stored = PluginPreferences.load(window.preferences_path)
    xp2 = stored.sync_set_for("DDJ-XP2")
    assert xp2.output_port == "PIONEER DDJ-XP2"
    assert [message.data1 for message in xp2.messages] == [11, 12]
    assert stored.sync_set_for("Some Unknown Box").messages[0].data1 == 3
    assert monitor.opened == []
    assert window._record_button.text() == "● Rec"


def test_record_asks_before_replacing_and_keeps_old_set_on_no(tmp_path, monkeypatch):
    window = _window(tmp_path)
    old = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 1, 127),))
    window.preferences.set_sync_set(old)
    window._record_monitor = _FakeMonitor([_event("PIONEER DDJ-XP2", 11)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2"])
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)

    window._record_button.click()
    window._record_button.click()

    assert window.preferences.sync_set_for("DDJ-XP2") == old


def test_record_without_any_input_unchecks_the_button(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([])
    monkeypatch.setattr(main_window_module, "list_input_ports", list)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args[1]))
    window._record_button.click()
    assert warned == ["Cannot record"]
    assert not window._record_button.isChecked()


def test_startup_sync_is_silent_without_sets_and_sends_stored_ones(tmp_path, monkeypatch):
    window = _window(tmp_path)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: (_ for _ in ()).throw(AssertionError))
    assert window._sync_at_startup() == []

    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127),)))
    sent = []
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: ["PIONEER DDJ-XP2"])
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs))
    assert [result.ok for result in window._sync_at_startup()] == [True]
    assert len(sent) == 1
