from PySide6.QtWidgets import QDialog

from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.gui.sync_set_editor import SyncSetEditorDialog

A = SyncMessage("Note On", 1, 11, 127)
B = SyncMessage("Control Change", 2, 7, 64)
C = SyncMessage("Note Off", 3, 20, 0)


def _set(*messages, port="PIONEER DDJ-XP2"):
    return ControllerSyncSet("DDJ-XP2", port, tuple(messages))


def test_editor_lists_messages_and_returns_them_unchanged_on_ok():
    dialog = SyncSetEditorDialog(_set(A, B))
    assert dialog.table.rowCount() == 2
    assert dialog.table.cellWidget(1, 0).currentText() == "Control Change"
    assert [dialog.table.item(1, c).text() for c in (1, 2, 3)] == ["2", "7", "64"]
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.edited_sync_set() == _set(A, B)


def test_editor_edits_deletes_and_reorders():
    dialog = SyncSetEditorDialog(_set(A, B, C))
    dialog.table.item(0, 3).setText("0")
    dialog.table.cellWidget(0, 0).setCurrentText("Note Off")
    dialog.table.selectRow(1)
    dialog._delete_selected()
    dialog.table.selectRow(1)
    dialog._move_selected(-1)
    dialog.accept()
    assert dialog.edited_sync_set().messages == (C, SyncMessage("Note Off", 1, 11, 0))
    assert dialog.edited_sync_set().output_port == "PIONEER DDJ-XP2"


def test_editor_refuses_invalid_value_and_keeps_original():
    dialog = SyncSetEditorDialog(_set(A))
    dialog.table.item(0, 1).setText("17")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "Message 1" in dialog.status.text()
    assert dialog.edited_sync_set() == _set(A)


def test_send_selected_uses_resolved_port():
    calls = []
    dialog = SyncSetEditorDialog(
        _set(A, B, port=""), ["PIONEER DDJ-XP2 MIDI 1"], sender=lambda **kw: calls.append(kw)
    )
    assert dialog.send_button.isEnabled()
    dialog.table.selectRow(1)
    dialog._send_selected()
    assert calls == [
        {
            "output_port_name": "PIONEER DDJ-XP2 MIDI 1",
            "event_type": "Control Change",
            "channel_1_based": 2,
            "data1": 7,
            "data2": 64,
        }
    ]
    assert "Sent message 2" in dialog.status.text()


def test_send_disabled_when_controller_not_connected_and_failures_are_reported():
    assert not SyncSetEditorDialog(_set(A), ["XDJ-XZ"]).send_button.isEnabled()

    def boom(**_kw):
        raise OSError("port vanished")

    dialog = SyncSetEditorDialog(_set(A), ["PIONEER DDJ-XP2"], sender=boom)
    dialog.table.selectRow(0)
    dialog._send_selected()
    assert "port vanished" in dialog.status.text()
