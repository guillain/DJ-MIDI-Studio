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


def test_plug_in_poll_syncs_a_controller_once_when_it_appears(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127),)))
    ports = []
    sent = []
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: list(ports))
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs))

    window._update_plug_in_watch()  # seeds with nothing connected
    assert window._plug_in_timer.isActive()
    assert window._poll_plugged_controllers() == []

    ports.append("PIONEER DDJ-XP2")
    assert [result.ok for result in window._poll_plugged_controllers()] == [True]
    assert window._poll_plugged_controllers() == []
    assert len(sent) == 1
    assert window.statusBar().currentMessage().startswith("Plugged in")

    ports.clear()
    window._poll_plugged_controllers()
    ports.append("PIONEER DDJ-XP2")
    window._poll_plugged_controllers()
    assert len(sent) == 2
    window.close()


def test_startup_sync_seeds_plug_in_tracker_so_nothing_is_sent_twice(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127),)))
    sent = []
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: ["PIONEER DDJ-XP2"])
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs))

    window._start_controller_sync()
    assert window._poll_plugged_controllers() == []
    assert len(sent) == 1
    window.close()


def test_plug_in_watch_follows_the_preference(tmp_path, monkeypatch):
    window = _window(tmp_path)
    monkeypatch.setattr(main_window_module, "list_output_ports", list)
    window.preferences.auto_sync_on_startup = False
    window.preferences.auto_sync_on_plug_in = False
    window._start_controller_sync()
    assert not window._plug_in_timer.isActive()
    window.preferences.auto_sync_on_plug_in = True
    window._update_plug_in_watch()
    assert window._plug_in_timer.isActive()
    window.preferences.auto_sync_on_plug_in = False
    window._update_plug_in_watch()
    assert not window._plug_in_timer.isActive()
    assert not window._plug_in_tracker.seeded


# --- Scenes (issue #188) ----------------------------------------------------


def _combo_items(window):
    combo = window._sync_scene_combo
    return [combo.itemText(index) for index in range(combo.count()) if combo.itemText(index)]


def test_scene_combo_lists_scenes_and_switching_persists_the_active_scene(tmp_path):
    window = _window(tmp_path)
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (), scene="Tek"))
    window._refresh_sync_scene_combo()
    assert _combo_items(window) == ["Default", "Tek", "New scene…"]
    assert window._sync_scene_combo.currentText() == "Default"

    window._on_sync_scene_activated(window._sync_scene_combo.findText("Tek"))
    assert PluginPreferences.load(window.preferences_path).active_sync_scene == "Tek"
    assert window._sync_scene_combo.currentText() == "Tek"


def test_new_scene_entry_asks_for_a_name_and_cancel_keeps_the_active_one(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window = _window(tmp_path)
    window._refresh_sync_scene_combo()
    new_index = window._sync_scene_combo.findText("New scene…")

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("", False))
    window._sync_scene_combo.setCurrentIndex(new_index)
    window._on_sync_scene_activated(new_index)
    assert window.preferences.active_sync_scene == "Default"
    assert window._sync_scene_combo.currentText() == "Default"

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("  Warm-up ", True))
    window._on_sync_scene_activated(new_index)
    assert window.preferences.active_sync_scene == "Warm-up"
    # Listed although no set is recorded for it yet.
    assert _combo_items(window) == ["Default", "Warm-up", "New scene…"]
    assert window._sync_scene_combo.currentText() == "Warm-up"


def test_sync_sends_the_active_scene_and_falls_back_to_default(tmp_path, monkeypatch):
    window = _window(tmp_path)
    xp2_default = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 1, 127),))
    xp2_tek = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 2, 127),), scene="Tek")
    xz_default = ControllerSyncSet("XDJ-XZ", "", (SyncMessage("Note On", 1, 3, 127),))
    for sync_set in (xp2_default, xp2_tek, xz_default):
        window.preferences.set_sync_set(sync_set)
    window.preferences.active_sync_scene = "Tek"
    sent = []
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: ["PIONEER DDJ-XP2", "XDJ-XZ"])
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs["data1"]))

    window._on_sync_controllers()
    window._sync_at_startup()

    assert sent == [2, 3, 2, 3]


def test_sync_explains_when_the_active_scene_has_nothing_to_send(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (), scene="Tek"))
    window.preferences.active_sync_scene = "DnB"
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[2]))
    assert window._on_sync_controllers() == []
    assert '"DnB"' in shown[0]


def test_record_and_controller_setup_save_into_the_active_scene(tmp_path, monkeypatch):
    window = _window(tmp_path)
    default = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 1, 127),))
    window.preferences.set_sync_set(default)
    window.preferences.active_sync_scene = "Tek"
    window._record_monitor = _FakeMonitor([_event("PIONEER DDJ-XP2", 11)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2"])
    # The Default set isn't replaced, so nothing is asked.
    monkeypatch.setattr(QMessageBox, "question", lambda *args: (_ for _ in ()).throw(AssertionError))

    window._record_button.click()
    window._record_button.click()

    stored = PluginPreferences.load(window.preferences_path)
    assert stored.sync_set_for("DDJ-XP2") == default
    assert [m.data1 for m in stored.sync_set_for("DDJ-XP2", "Tek").messages] == [11]
    assert _combo_items(window) == ["Default", "Tek", "New scene…"]

    window._on_sync_set_save_requested(ControllerSyncSet("XDJ-XZ", "", ()))
    assert window.preferences.sync_set_for("XDJ-XZ", "Tek") is not None
    assert window.preferences.sync_set_for("XDJ-XZ") is None


def test_menu_corner_fits_at_1100_px(tmp_path):
    window = _window(tmp_path)
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (), scene="A rather long scene name"))
    window.preferences.active_sync_scene = "A rather long scene name"
    window._refresh_sync_scene_combo()
    window.resize(1100, 700)
    window.show()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    corner = window._menu_corner
    right_edge = corner.mapTo(window, corner.rect().topRight()).x()
    assert corner.isVisible()
    assert right_edge <= window.width()
    assert window._sync_scene_combo.width() <= 140
    for button in (window._record_button, window._sync_button, window._preferences_button):
        assert button.isVisible() and button.width() >= button.minimumSizeHint().width()
    window.close()
