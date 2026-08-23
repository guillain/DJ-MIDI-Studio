from unittest.mock import patch

from djmidi.catalog._registry import ControlInfo
from djmidi.gui.metronome_view import MetronomeView


def _view_with_entries(entries):
    return MetronomeView(
        all_rows_provider=lambda: entries,
        selected_rows_provider=lambda: entries,
        session_name_provider=lambda: "Test session",
    )


def test_metronome_view_refreshes_session_summary():
    entries = [ControlInfo("Test", "PAD", "Pad 1", "NOTE", ("1",), "10")]
    view = _view_with_entries(entries)
    view.refresh_session_summary()
    assert "Test session" in view._session_summary.text()
    assert "All rows: 1" in view._session_summary.text()


def test_metronome_view_starts_and_stops_loop():
    entries = [ControlInfo("Test", "PAD", "Pad 1", "NOTE", ("1",), "10")]
    view = _view_with_entries(entries)
    view._output_port_list.addItem("Out A")
    view._output_port_list.setCurrentRow(0)
    view._hz_edit.setText("4")
    with patch("djmidi.gui.metronome_view.play_control_info_entries") as mock_play:
        mock_play.return_value.sent_messages = 1
        mock_play.return_value.skipped_entries = 0
        view._start_loop("selected")
        assert view._loop_timer.isActive()
        view._on_loop_tick()
    view._stop_loop()
    assert not view._loop_timer.isActive()


def test_metronome_view_start_loop_rejects_invalid_frequency():
    entries = [ControlInfo("Test", "PAD", "Pad 1", "NOTE", ("1",), "10")]
    view = _view_with_entries(entries)
    view._hz_edit.setText("not-a-number")
    with patch("djmidi.gui.metronome_view.QMessageBox.critical") as mock_critical:
        view._start_loop("selected")
    mock_critical.assert_called_once()
    assert not view._loop_timer.isActive()


def test_metronome_view_start_loop_warns_when_no_rows_for_scope():
    view = _view_with_entries([])
    with patch("djmidi.gui.metronome_view.QMessageBox.warning") as mock_warning:
        view._start_loop("selected")
    mock_warning.assert_called_once()
    assert not view._loop_timer.isActive()


def test_metronome_view_play_once_shows_error_without_output_port():
    entries = [ControlInfo("Test", "PAD", "Pad 1", "NOTE", ("1",), "10")]
    view = _view_with_entries(entries)
    with patch("djmidi.gui.metronome_view.QMessageBox.critical") as mock_critical:
        view._on_play_selected_once_clicked()
    mock_critical.assert_called_once()
