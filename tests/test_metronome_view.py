from unittest.mock import patch

from PySide6.QtCore import QSettings

from djmidi.catalog._registry import ControlInfo
from djmidi.gui.metronome_view import MetronomeView


def _view_with_entries(entries):
    return MetronomeView(
        all_rows_provider=lambda: entries,
        selected_rows_provider=lambda: entries,
        session_name_provider=lambda: "Test session",
    )


def _ini_settings(tmp_path):
    """A throwaway file-backed QSettings, isolated from the user's real one."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


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


def test_save_state_and_restore_state_round_trip(tmp_path):
    settings = _ini_settings(tmp_path)
    view = _view_with_entries([])
    view._output_port_list.clear()
    view._output_port_list.addItems(["Out A", "Out B"])
    view._output_port_list.setCurrentRow(1)
    view._value_edit.setText("64")
    view._hz_edit.setText("3.5")
    view.save_state(settings)

    restored = _view_with_entries([])
    restored._output_port_list.clear()
    restored._output_port_list.addItems(["Out A", "Out B"])
    restored.restore_state(settings)

    assert restored._output_port_list.currentItem().text() == "Out B"
    assert restored._value_edit.text() == "64"
    assert restored._hz_edit.text() == "3.5"


def test_save_state_with_no_selected_output_port(tmp_path):
    settings = _ini_settings(tmp_path)
    view = _view_with_entries([])
    view._output_port_list.clear()
    view.save_state(settings)
    settings.beginGroup("metronome")
    assert settings.value("outputPort") == ""
    settings.endGroup()


def test_restore_state_leaves_defaults_when_nothing_saved(tmp_path):
    settings = _ini_settings(tmp_path)
    view = _view_with_entries([])
    view.restore_state(settings)
    assert view._value_edit.text() == "127"
    assert view._hz_edit.text() == "2.0"
