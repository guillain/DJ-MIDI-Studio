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


def test_record_button_saves_one_sync_set_per_recognized_controller(tmp_path, monkeypatch):
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
    # An unrecognized port (a loopback bus, another program) is never saved:
    # it would be replayed at every launch.
    assert stored.sync_set_for("Some Unknown Box") is None
    assert "Some Unknown Box" in window.statusBar().currentMessage()
    assert monitor.opened == []
    assert window._record_button.text() == "● Rec"


def test_record_asks_before_replacing_and_keeps_old_set_on_no(tmp_path, monkeypatch):
    window = _window(tmp_path)
    old = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 1, 127),))
    window.preferences.set_sync_set(old)
    window._record_monitor = _FakeMonitor([_event("PIONEER DDJ-XP2", 11)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2"])
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: asked.append(args[2]) or QMessageBox.StandardButton.No
    )

    window._record_button.click()
    window._record_button.click()

    assert len(asked) == 1 and "DDJ-XP2" in asked[0]
    assert window.preferences.controller_sync_sets == [old]  # nothing else stored either


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


def _scene_switch_window(tmp_path, monkeypatch, *, enabled):
    window = _window(tmp_path)
    window.preferences.sync_on_scene_switch = enabled
    window.preferences.set_sync_set(ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 1, 127),)))
    window.preferences.set_sync_set(
        ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 2, 127),), scene="Tek")
    )
    window._refresh_sync_scene_combo()
    sent = []
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: ["PIONEER DDJ-XP2"])
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs["data1"]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: (_ for _ in ()).throw(AssertionError))
    return window, sent


def test_switching_scene_sends_nothing_by_default(tmp_path, monkeypatch):
    window, sent = _scene_switch_window(tmp_path, monkeypatch, enabled=False)
    window._on_sync_scene_activated(window._sync_scene_combo.findText("Tek"))
    assert window.preferences.active_sync_scene == "Tek"
    assert sent == []


def test_switching_scene_syncs_the_new_scene_when_enabled(tmp_path, monkeypatch):
    window, sent = _scene_switch_window(tmp_path, monkeypatch, enabled=True)
    window._on_sync_scene_activated(window._sync_scene_combo.findText("Tek"))
    assert sent == [2]
    assert "Synced 1/1 controller(s)" in window.statusBar().currentMessage()

    # Re-picking the active scene doesn't resend; switching back does.
    window._on_sync_scene_activated(window._sync_scene_combo.findText("Tek"))
    assert sent == [2]
    window._on_sync_scene_activated(window._sync_scene_combo.findText("Default"))
    assert sent == [2, 1]


def test_switching_to_a_scene_with_nothing_to_send_stays_silent(tmp_path, monkeypatch):
    window, sent = _scene_switch_window(tmp_path, monkeypatch, enabled=True)
    window.preferences.controller_sync_sets = [
        s for s in window.preferences.controller_sync_sets if s.scene == "Tek"
    ]
    monkeypatch.setattr(main_window_module.QInputDialog, "getText", lambda *args: ("DnB", True))
    window._on_sync_scene_activated(window._sync_scene_combo.findText("New scene…"))
    assert window.preferences.active_sync_scene == "DnB"
    assert sent == []
    assert window.statusBar().currentMessage() == "Sync scene: DnB"


def test_saving_pad_colours_merges_them_into_the_active_scene_set(tmp_path):
    from djmidi import pad_colours
    from djmidi.pad_colours import PadSlot

    controller = "Hercules DJControl Inpulse 500"
    window = _window(tmp_path)
    window.preferences.active_sync_scene = "Tek"
    keep = SyncMessage("Control Change", 1, 14, 64)
    window.preferences.set_sync_set(
        ControllerSyncSet(controller, "", (keep, SyncMessage("Note On", 7, 0, 0x60)), "Tek")
    )
    palette = pad_colours.palette_for(controller)

    saved = window._on_pad_colours_save_requested(controller, {PadSlot(1, 1): palette.colour_named("Blue")})

    assert saved.messages == (keep, SyncMessage("Note On", 7, 0, 0x03))
    assert PluginPreferences.load(window.preferences_path).sync_set_for(controller, "Tek") == saved
    assert window._on_pad_colours_save_requested("DDJ-XP2", {PadSlot(1, 1): palette.colours[0]}) is None


def test_record_declining_a_replacement_still_saves_the_other_controllers(tmp_path, monkeypatch):
    window = _window(tmp_path)
    old = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 1, 127),))
    window.preferences.set_sync_set(old)
    window._record_monitor = _FakeMonitor([_event("PIONEER DDJ-XP2", 11), _event("XDJ-XZ", 7)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2", "XDJ-XZ"])
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: asked.append(args[2]) or QMessageBox.StandardButton.No
    )

    window._record_button.click()
    window._record_button.click()

    # No keeps the stored DDJ-XP2 set; the XDJ-XZ, which had none, is saved.
    assert len(asked) == 1 and "DDJ-XP2" in asked[0] and "XDJ-XZ" not in asked[0]
    stored = PluginPreferences.load(window.preferences_path)
    assert stored.sync_set_for("DDJ-XP2") == old
    assert [message.data1 for message in stored.sync_set_for("XDJ-XZ").messages] == [7]


def test_record_ignores_a_port_with_only_a_manufacturer_match(tmp_path, monkeypatch):
    # "Pioneer DJ" is every Pioneer profile's manufacturer: it says who made the
    # device, not that it is the DDJ-XP2, whose set must stay untouched.
    window = _window(tmp_path)
    xp2 = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 1, 127),))
    window.preferences.set_sync_set(xp2)
    window._record_monitor = _FakeMonitor([_event("Pioneer DJ Mystery Unit", 5)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["Pioneer DJ Mystery Unit"])
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: asked.append(args) or QMessageBox.StandardButton.Yes)

    window._record_button.click()
    window._record_button.click()

    assert asked == []
    assert window.preferences.sync_set_for("DDJ-XP2") == xp2
    assert window.preferences.sync_set_for("Pioneer DJ Mystery Unit") is None


def test_controller_name_for_port_needs_an_exact_match_and_ignores_plugin_enablement():
    from djmidi import catalog

    assert MainWindow._controller_name_for_port("PIONEER DDJ-XP2") == "DDJ-XP2"
    assert MainWindow._controller_name_for_port("Pioneer DJ Mystery Unit") == ""
    # A plugin switched off in Preferences must not rename the device's set
    # (conftest restores the enablement filter).
    catalog.set_enabled_plugin_ids(set())
    assert MainWindow._controller_name_for_port("PIONEER DDJ-XP2") == "DDJ-XP2"


def test_record_keeps_both_recordings_when_two_ports_are_the_same_controller(tmp_path, monkeypatch):
    # Two identical units: both ports detect as "DDJ-XP2", but sets are stored
    # one per controller name, so the second is named after its port.
    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([_event("DDJ-XP2 0", 11), _event("DDJ-XP2 1", 12)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["DDJ-XP2 0", "DDJ-XP2 1"])

    window._record_button.click()
    window._record_button.click()

    stored = PluginPreferences.load(window.preferences_path)
    assert [(s.controller, [m.data1 for m in s.messages]) for s in stored.controller_sync_sets] == [
        ("DDJ-XP2", [11]),
        ("DDJ-XP2 1", [12]),
    ]


def test_sync_finds_a_controller_whose_port_name_changed(tmp_path, monkeypatch):
    # Windows numbers the input and output lists separately and renumbers them
    # as devices come and go: a CMD Micro recorded on "CMD Micro 0" now listens
    # on "CMD Micro 2", and "Behringer CMD Micro" isn't in the port name.
    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([_event("CMD Micro 0", 5)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["CMD Micro 0"])
    window._record_button.click()
    window._record_button.click()
    # An unknown device's set comes from Controller Setup, never from ● Rec.
    window.preferences.set_sync_set(ControllerSyncSet("Some Box 0", "Some Box 0", (SyncMessage("Note On", 1, 3, 127),)))
    assert window.preferences.sync_set_for("Behringer CMD Micro").output_port == "CMD Micro 0"  # as recorded

    outputs = ["Microsoft GS Wavetable Synth 0", "DDJ-XP2 1", "CMD Micro 2", "Some Box 3"]
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: outputs)
    sent = []
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs["output_port_name"]))

    results = {result.controller: result.port for result in window._on_sync_controllers()}

    assert results["Behringer CMD Micro"] == "CMD Micro 2"
    assert sent == ["CMD Micro 2"]
    # An unrecognized device has no catalog identity to find its output by.
    assert results["Some Box 0"] is None


def test_plug_in_sync_finds_a_controller_whose_port_name_changed(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window.preferences.set_sync_set(
        ControllerSyncSet("Behringer CMD Micro", "CMD Micro 0", (SyncMessage("Note On", 1, 5, 127),))
    )
    ports = ["Microsoft GS Wavetable Synth 0"]
    sent = []
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: list(ports))
    monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kwargs: sent.append(kwargs["output_port_name"]))

    window._update_plug_in_watch()  # seeds with the synth only
    ports.append("CMD Micro 2")
    assert [(result.controller, result.port) for result in window._poll_plugged_controllers()] == [
        ("Behringer CMD Micro", "CMD Micro 2")
    ]
    assert sent == ["CMD Micro 2"]
    window.close()


def test_record_names_the_inputs_it_could_not_open(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2", "Busy port"])
    window._record_button.click()
    assert "Busy port" in window.statusBar().currentMessage()
    window._record_button.click()

    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["Busy port"])
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args[2]))
    window._record_button.click()
    assert "Busy port" in warned[0]
    assert not window._record_button.isChecked()


def test_record_refreshes_the_dashboard_files_card(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([_event("PIONEER DDJ-XP2", 11)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2"])
    assert "DDJ-XP2" not in window.introduction_view._files_sync_label.text()

    window._record_button.click()
    window._record_button.click()

    assert "DDJ-XP2" in window.introduction_view._files_sync_label.text()


def test_rec_label_change_does_not_squeeze_the_menu_corner(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2"])
    window.resize(1280, 800)
    window.show()
    QApplication.processEvents()

    window._record_button.click()  # "● Rec" becomes the wider "■ Stop"
    QApplication.processEvents()

    # QMenuBar only re-lays its corner out when told to: without that, the
    # corner kept its old width and squeezed the scene combo below its minimum.
    corner = window._menu_corner
    assert corner.width() >= corner.sizeHint().width()
    for widget in (window._record_button, window._sync_scene_combo, window._sync_button, window._preferences_button):
        assert widget.width() >= widget.minimumSizeHint().width(), widget
    window._record_button.click()
    window.close()


def test_record_ignores_a_loopback_bus(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([_event("IAC Driver Bus 1", 7)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["IAC Driver Bus 1"])

    window._record_button.click()
    window._record_button.click()

    assert window.preferences.controller_sync_sets == []
    assert "IAC Driver Bus 1" in window.statusBar().currentMessage()


def _recording_window(tmp_path, monkeypatch, reply):
    window = _window(tmp_path)
    window._record_monitor = _FakeMonitor([_event("PIONEER DDJ-XP2", 11)])
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["PIONEER DDJ-XP2"])
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: asked.append(args[1]) or reply)
    window._record_button.click()
    assert window._record_button.isChecked()
    return window, asked


def test_quitting_while_recording_asks_and_saves(tmp_path, monkeypatch):
    window, asked = _recording_window(tmp_path, monkeypatch, QMessageBox.StandardButton.Save)

    assert window.close()

    assert asked == ["Recording in progress"]
    assert [m.data1 for m in window.preferences.sync_set_for("DDJ-XP2").messages] == [11]


def test_quitting_while_recording_can_discard(tmp_path, monkeypatch):
    window, asked = _recording_window(tmp_path, monkeypatch, QMessageBox.StandardButton.Discard)

    assert window.close()

    assert asked == ["Recording in progress"]
    assert window.preferences.controller_sync_sets == []
    assert window._record_monitor.opened == []


def test_quitting_while_recording_can_be_cancelled(tmp_path, monkeypatch):
    window, asked = _recording_window(tmp_path, monkeypatch, QMessageBox.StandardButton.Cancel)

    assert not window.close()

    assert asked == ["Recording in progress"]
    assert window._record_button.isChecked()
    window._record_button.click()  # still recording: Stop saves it
    assert [m.data1 for m in window.preferences.sync_set_for("DDJ-XP2").messages] == [11]
