from contextlib import contextmanager

import pytest
import shiboken6
from PySide6.QtCore import QEventLoop, QObject, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog

from djmidi import midi_macros, user_paths
from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.gui import main_window as main_window_module
from djmidi.gui.macro_editor import MacroManagerDialog
from djmidi.gui.macro_player import MacroPlayer
from djmidi.gui.main_window import MainWindow
from djmidi.midi_io import MidiEvent
from djmidi.midi_macros import MacroStep, MacroTrigger, MidiMacro
from djmidi.plugins import PluginPreferences

PRESS = SyncMessage("Note On", 1, 11, 127)
RELEASE = SyncMessage("Note Off", 1, 11, 0)
PORT = "PIONEER DDJ-XP2"


def _macro(name="Loop", shortcut="Ctrl+Shift+1", delay=0):
    return MidiMacro(name, PORT, (MacroStep(PRESS), MacroStep(RELEASE, delay)), shortcut)


def _wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# --- player -------------------------------------------------------------------


def test_player_plays_undelayed_macro_synchronously():
    sent, finished = [], []
    player = MacroPlayer(sender=lambda **kw: sent.append(kw))
    player.finished.connect(finished.append)
    result = player.play(_macro(), [PORT])
    assert result is not None and result.ok and result.sent == 2
    assert finished == [result]
    assert player.running == 0


def test_player_waits_delays_on_timers_without_blocking():
    sent, finished = [], []
    player = MacroPlayer(sender=lambda **kw: sent.append(kw["event_type"]))
    player.finished.connect(finished.append)
    assert player.play(_macro(delay=30), [PORT]) is None
    assert sent == ["Note On"] and player.running == 1
    for _ in range(50):
        if finished:
            break
        _wait(20)
    assert sent == ["Note On", "Note Off"]
    assert finished and finished[0].ok and player.running == 0


def test_player_reports_unconnected_port():
    finished = []
    player = MacroPlayer(sender=lambda **kw: None)
    player.finished.connect(finished.append)
    result = player.play(_macro(), ["IAC Bus"])
    assert not result.ok and finished == [result]


class _FakeOutput:
    """Counts how often a port is opened and closed (issue #308)."""

    def __init__(self, fail_on=None):
        self.opened, self.closed, self.sent = [], 0, []
        self._fail_on = fail_on

    @contextmanager
    def __call__(self, port):
        self.opened.append(port)
        try:

            def send(**kw):
                if len(self.sent) + 1 == self._fail_on:
                    raise OSError("port vanished")
                self.sent.append(kw["event_type"])

            yield send
        finally:
            self.closed += 1


def _wait_until(condition):
    for _ in range(50):
        if condition():
            return
        _wait(20)


def test_player_keeps_one_port_open_across_delays():
    output, finished = _FakeOutput(), []
    player = MacroPlayer(port_opener=output)
    player.finished.connect(finished.append)
    assert player.play(_macro(delay=30), [PORT]) is None
    assert output.opened == [PORT] and output.closed == 0  # held across the delay
    _wait_until(lambda: finished)
    assert output.sent == ["Note On", "Note Off"]
    assert output.opened == [PORT] and output.closed == 1
    assert finished[0].ok


def test_player_closes_the_port_when_a_delayed_send_fails():
    output, finished = _FakeOutput(fail_on=2), []
    player = MacroPlayer(port_opener=output)
    player.finished.connect(finished.append)
    player.play(_macro(delay=30), [PORT])
    _wait_until(lambda: finished)
    assert (finished[0].sent, finished[0].error) == (1, "port vanished")
    assert output.closed == 1 and player.running == 0


def test_player_reports_a_port_that_will_not_open():
    def opener(port):
        raise OSError("cannot open")

    finished = []
    player = MacroPlayer(port_opener=opener)
    player.finished.connect(finished.append)
    result = player.play(_macro(delay=30), [PORT])
    assert (result.ok, result.error) == (False, "cannot open") and finished == [result]
    assert player.running == 0


def test_player_stop_all_closes_waiting_ports_and_cancels_their_timers():
    output, finished = _FakeOutput(), []
    player = MacroPlayer(port_opener=output)
    player.finished.connect(finished.append)
    player.play(_macro(delay=30), [PORT])
    player.stop_all()
    assert output.closed == 1 and player.running == 0
    assert finished[0].error == "cancelled" and finished[0].sent == 1
    _wait(80)  # the pending timer must not send on a closed port
    assert output.sent == ["Note On"] and len(finished) == 1


def test_destroying_the_player_closes_a_waiting_port():
    output = _FakeOutput()
    parent = QObject()
    player = MacroPlayer(parent=parent, port_opener=output)
    player.play(_macro(delay=5000), [PORT])
    assert output.closed == 0
    shiboken6.delete(parent)
    assert output.closed == 1


# --- editor dialog --------------------------------------------------------------


def test_dialog_returns_macros_unchanged_on_ok():
    dialog = MacroManagerDialog([_macro("A"), _macro("B", shortcut="")], [PORT])
    assert dialog.macro_list.count() == 2
    assert dialog.table.rowCount() == 2
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.edited_macros() == [_macro("A"), _macro("B", shortcut="")]


def test_dialog_creates_edits_and_deletes_macros():
    dialog = MacroManagerDialog([], [PORT])
    assert not dialog.editor.isEnabled()
    dialog._new_macro()
    dialog.name_edit.setText("Echo out")
    dialog._add_step()
    dialog._add_step()
    dialog.table.item(1, 4).setText("250")
    dialog.table.cellWidget(1, 0).setCurrentText("Note Off")
    dialog.table.item(1, 3).setText("0")
    dialog.shortcut_edit.setKeySequence(QKeySequence("Ctrl+Alt+E"))
    dialog._new_macro()
    dialog._delete_macro()
    dialog.accept()
    (macro,) = dialog.edited_macros()
    assert macro.name == "Echo out" and macro.output_port == PORT
    assert macro.shortcut == "Ctrl+Alt+E"
    assert [(step.message.event_type, step.message.data2, step.delay_ms) for step in macro.steps] == [
        ("Note On", 127, 0),
        ("Note Off", 0, 250),
    ]


def test_dialog_refuses_invalid_rows_reserved_and_duplicate_shortcuts():
    dialog = MacroManagerDialog([_macro("A"), _macro("B", shortcut="")], [PORT], reserved_shortcuts=["Ctrl+O"])
    dialog.table.item(0, 1).setText("17")
    dialog.macro_list.setCurrentRow(1)
    assert dialog.macro_list.currentRow() == 0  # stays on the invalid macro
    assert "Step 1" in dialog.status.text()
    dialog.table.item(0, 1).setText("1")
    dialog.shortcut_edit.setKeySequence(QKeySequence("Ctrl+O"))
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "already used" in dialog.status.text()
    dialog.shortcut_edit.setKeySequence(QKeySequence("Ctrl+Shift+1"))
    dialog.macro_list.setCurrentRow(1)
    dialog.shortcut_edit.setKeySequence(QKeySequence("Ctrl+Shift+1"))
    dialog.accept()
    assert "same shortcut" in dialog.status.text()
    assert dialog.edited_macros() == [_macro("A"), _macro("B", shortcut="")]


def test_dialog_reorders_appends_sync_set_and_tests():
    sent = []
    sync_set = ControllerSyncSet("XDJ-XZ", "", (SyncMessage("Control Change", 3, 9, 1),))
    dialog = MacroManagerDialog(
        [_macro()], [PORT], sync_sets=[sync_set], sender=lambda **kw: sent.append(kw["data1"])
    )
    dialog.table.selectRow(1)
    dialog._move_step(-1)
    dialog.append_sync_set(sync_set)
    dialog._test_macro()
    assert sent == [11, 11, 9]
    assert "sent 3" in dialog.status.text()
    dialog.accept()
    assert [step.message.event_type for step in dialog.edited_macros()[0].steps] == [
        "Note Off",
        "Note On",
        "Control Change",
    ]


@pytest.mark.parametrize("close", ["accept", "reject", "close"])
def test_closing_the_dialog_stops_its_test_player(close):
    """Issue #314: a Test run waiting on a delay releases its port when the
    editor closes, however it closes."""
    output, finished = _FakeOutput(), []
    dialog = MacroManagerDialog([_macro(delay=5000)], [PORT], port_opener=output)
    dialog._player.finished.connect(finished.append)
    dialog.show()  # QDialog.closeEvent only rejects a visible dialog
    dialog._test_macro()
    assert output.opened == [PORT] and output.closed == 0 and dialog._player.running == 1
    getattr(dialog, close)()
    assert output.closed == 1 and dialog._player.running == 0
    assert finished[0].error == "cancelled"


# --- main window ------------------------------------------------------------------


def _window(tmp_path):
    window = MainWindow()
    window.preferences = PluginPreferences()
    window.preferences_path = tmp_path / "preferences.json"
    return window


def test_macros_load_from_folder_into_menu_with_shortcuts(tmp_path, monkeypatch):
    midi_macros.save_macros(user_paths.macros_dir(), [_macro("Loop"), _macro("Plain", shortcut="")])
    window = _window(tmp_path)
    try:
        assert [action.text() for action in window._macro_actions] == ["Loop", "Plain"]
        assert window._macro_actions[0].shortcut().toString() == "Ctrl+Shift+1"
        reserved = window._reserved_shortcuts()
        assert "Ctrl+O" in reserved and "Ctrl+Shift+1" not in reserved

        monkeypatch.setattr(main_window_module, "list_output_ports", lambda: [PORT])
        output = _FakeOutput()
        monkeypatch.setattr("djmidi.midi_io.open_midi_output", output)
        monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kw: pytest.fail("must not reopen per step"))
        window._macro_actions[0].trigger()
        sent = output.sent
        assert len(sent) == 2 and output.opened == [PORT] and output.closed == 1
        assert window.statusBar().currentMessage().startswith('Macro "Loop": sent 2')
    finally:
        window.close()


def test_manage_macros_saves_files_and_rebuilds_menu(tmp_path, monkeypatch):
    window = _window(tmp_path)
    monkeypatch.setattr(main_window_module, "list_output_ports", list)

    class _Accepting:
        def __init__(self, macros, ports, sync_sets, reserved, parent=None, ensure_listening=None):
            assert "Ctrl+S" in reserved
            assert ensure_listening is not None

        def exec(self):
            return QDialog.DialogCode.Accepted

        def edited_macros(self):
            return [_macro("New one")]

    try:
        assert window._macro_actions == []
        assert window._on_manage_macros(_Accepting)
        assert [action.text() for action in window._macro_actions] == ["New one"]
        assert midi_macros.load_macros(user_paths.macros_dir()) == [_macro("New one")]
    finally:
        window.close()


# --- MIDI Learn (issue #252) ------------------------------------------------------


def _press(data1="40", data2="127", port="DDJ-XP2", event_type="Note On"):
    return MidiEvent("in", "1", event_type, data1, data2, 0.0, port)


def test_dialog_learns_a_trigger_from_the_next_press():
    dialog = MacroManagerDialog([_macro("A")], [PORT], ensure_listening=lambda: True)
    assert dialog.trigger_label.text() == "None" and not dialog.clear_trigger_button.isEnabled()
    assert not dialog.feed_learn_event(_press())  # not learning: ignored
    dialog.learn_button.click()
    assert dialog.is_learning and dialog.learn_button.text() == "Cancel"
    assert not dialog.feed_learn_event(_press(data2="0"))  # a release doesn't count
    assert dialog.feed_learn_event(_press())
    assert not dialog.is_learning
    assert dialog.trigger_label.text() == "Note 40, ch 1 on DDJ-XP2"
    dialog.accept()
    assert dialog.edited_macros()[0].trigger == MacroTrigger("Note On", 1, 40, "DDJ-XP2")


def test_dialog_learn_reports_no_input_cancels_and_clears():
    trigger = MacroTrigger("Note On", 1, 40, "DDJ-XP2")
    dialog = MacroManagerDialog([MidiMacro("A", PORT, (), "", trigger)], [PORT], ensure_listening=lambda: False)
    assert not dialog.start_learn()
    assert "No MIDI input" in dialog.status.text()
    dialog.clear_trigger_button.click()
    dialog.accept()
    assert dialog.edited_macros()[0].trigger is None

    unavailable = MacroManagerDialog([_macro("A")], [PORT])
    assert not unavailable.learn_button.isEnabled()

    learning = MacroManagerDialog([_macro("A"), _macro("B", shortcut="")], [PORT], ensure_listening=lambda: True)
    learning.start_learn()
    learning.learn_button.click()
    assert not learning.is_learning and learning.status.text() == "Learn cancelled."
    learning.start_learn()
    learning.macro_list.setCurrentRow(1)  # switching macro stops listening
    assert not learning.is_learning


def test_controller_press_plays_its_macro_unless_the_editor_is_open(tmp_path, monkeypatch):
    bound = MidiMacro("Bound", PORT, (MacroStep(PRESS),), trigger=MacroTrigger("Note On", 1, 40, "DDJ-XP2"))
    midi_macros.save_macros(user_paths.macros_dir(), [bound])
    window = _window(tmp_path)
    output = _FakeOutput()
    sent = output.sent
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: [PORT])
    monkeypatch.setattr("djmidi.midi_io.open_midi_output", output)
    try:
        window._on_live_midi_event(_press(data2="0"))
        assert sent == []
        window._on_live_midi_event(_press())
        assert len(sent) == 1
        assert window.statusBar().currentMessage().startswith('Macro "Bound": sent 1')

        class _Learning:
            def __init__(self, *args, **kwargs):
                self.fed = []

            def exec(self):
                window._on_live_midi_event(_press())
                return QDialog.DialogCode.Rejected

            def feed_learn_event(self, event):
                self.fed.append(event)
                return True

        dialogs = []
        assert not window._on_manage_macros(lambda *a, **kw: dialogs.append(_Learning()) or dialogs[-1])
        assert len(dialogs[0].fed) == 1 and len(sent) == 1  # routed to the editor, not played
        assert window._macro_dialog is None
    finally:
        window.close()


def test_closing_the_main_window_stops_waiting_macros(tmp_path, monkeypatch):
    """Issue #314: a macro waiting between steps releases its port when the
    main window closes, not only when the process exits."""
    output = _FakeOutput()
    monkeypatch.setattr(main_window_module, "list_output_ports", lambda: [PORT])
    window = _window(tmp_path)
    window._macro_player._port_opener = output
    window.macros = [_macro(delay=5000)]
    assert window._play_macro("Loop") is None
    assert output.closed == 0 and window._macro_player.running == 1
    window.close()
    assert output.closed == 1 and window._macro_player.running == 0
