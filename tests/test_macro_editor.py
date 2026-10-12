from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog

from djmidi import midi_macros, user_paths
from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.gui import main_window as main_window_module
from djmidi.gui.macro_editor import MacroManagerDialog
from djmidi.gui.macro_player import MacroPlayer
from djmidi.gui.main_window import MainWindow
from djmidi.midi_macros import MacroStep, MidiMacro
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

        sent = []
        monkeypatch.setattr(main_window_module, "list_output_ports", lambda: [PORT])
        monkeypatch.setattr("djmidi.midi_io.send_midi_message", lambda **kw: sent.append(kw))
        window._macro_actions[0].trigger()
        assert len(sent) == 2
        assert window.statusBar().currentMessage().startswith('Macro "Loop": sent 2')
    finally:
        window.close()


def test_manage_macros_saves_files_and_rebuilds_menu(tmp_path, monkeypatch):
    window = _window(tmp_path)
    monkeypatch.setattr(main_window_module, "list_output_ports", list)

    class _Accepting:
        def __init__(self, macros, ports, sync_sets, reserved, parent=None):
            assert "Ctrl+S" in reserved

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
