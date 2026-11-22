"""Questions and reports over long lists show every row (a message box
showed 15, cut, and outgrew the screen)."""

from PySide6.QtWidgets import QDialogButtonBox

from djmidi.gui.list_dialog import ListDialog


def test_a_confirmation_lists_every_row_and_defaults_to_cancel():
    rows = [((f"{n}.mp3", "BPM 128"), (f"/music/{n}.mp3", "")) for n in range(69)]
    dialog = ListDialog("Apply", "Write tags into 69 track(s)?", ["Track", "Tags"], rows, accept_text="Write tags")
    assert dialog.table.topLevelItemCount() == 69
    first = dialog.table.topLevelItem(0)
    assert first.text(0) == "0.mp3" and first.toolTip(0) == "/music/0.mp3"
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons.button(QDialogButtonBox.StandardButton.Cancel).isDefault()
    assert dialog.accept_button.text() == "Write tags"


def test_a_report_only_closes_and_a_single_column_hides_its_header():
    dialog = ListDialog("Update playlists", "2 copies are in playlists:", ["Playlist"], [("Friday",), ("Warm-up",)])
    assert dialog.accept_button is None
    assert dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Close) is not None
    assert dialog.table.isHeaderHidden()
    assert dialog.table.topLevelItem(1).text(0) == "Warm-up" and dialog.table.topLevelItem(1).toolTip(0) == "Warm-up"


def test_a_plain_string_row_is_one_cell_and_the_check_box_is_offered():
    from djmidi.gui.list_dialog import ListDialog

    dialog = ListDialog("T", "M", ["Item"], ["/a/b.json"], accept_text="Go", check_text="Also", checked=True)
    assert dialog.table.topLevelItem(0).text(0) == "/a/b.json"
    assert dialog.check is not None and dialog.check.isChecked()
    empty = ListDialog("T", "M", ["Item"], [], accept_text="Go")
    assert empty.table.isHidden() and empty.check is None


def test_rows_can_be_unticked_one_by_one():
    from PySide6.QtCore import Qt

    from djmidi.gui.list_dialog import ListDialog

    dialog = ListDialog("T", "Pick", ["A", "B"], [("1", "x"), ("2", "y"), ("3", "z")], accept_text="Do",
                        checkable=[True, False, True])
    assert dialog.ticked_rows() == [0, 2]  # all ticked to start; row 1 has no box
    assert not dialog.table.topLevelItem(1).flags() & Qt.ItemFlag.ItemIsUserCheckable
    dialog.table.topLevelItem(0).setCheckState(0, Qt.CheckState.Unchecked)
    assert dialog.ticked_rows() == [2] and dialog.accept_button.isEnabled()
    dialog.table.topLevelItem(2).setCheckState(0, Qt.CheckState.Unchecked)
    assert not dialog.accept_button.isEnabled()  # nothing ticked, nothing to do
