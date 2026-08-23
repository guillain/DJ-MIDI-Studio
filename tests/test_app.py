"""Tests for gui/app.py – verifies the entry point wires QApplication correctly."""
from __future__ import annotations

from unittest.mock import patch

from djmidi.plugins.preferences import PluginPreferences


def test_run_creates_window_and_calls_exec():
    with patch("djmidi.gui.app.QApplication") as mock_qapp, \
         patch("djmidi.gui.app.MainWindow") as mock_window, \
         patch("djmidi.gui.app.configure_logging"):
        mock_qapp.return_value.exec.return_value = 0
        from djmidi.gui.app import run
        result = run()
    assert result == 0
    mock_window.return_value.show.assert_called_once()
    mock_qapp.return_value.exec.assert_called_once()


def test_main_entrypoint_calls_run_and_exits():
    import djmidi
    assert callable(djmidi.main)


def test_run_propagates_exec_return_code():
    with patch("djmidi.gui.app.QApplication") as mock_qapp, \
         patch("djmidi.gui.app.MainWindow"), \
         patch("djmidi.gui.app.configure_logging"):
        mock_qapp.return_value.exec.return_value = 42
        from djmidi.gui.app import run
        assert run() == 42


def test_djmidi_main_calls_gui_run():
    with patch("djmidi.gui.app.run", return_value=0) as mock_run:
        try:
            import djmidi
            djmidi.main()
        except SystemExit:
            pass
    mock_run.assert_called_once()


def test_run_prefers_explicit_log_file_over_saved_preference():
    saved = PluginPreferences(log_path="/saved/preference.log")
    with patch("djmidi.gui.app.QApplication") as mock_qapp, \
         patch("djmidi.gui.app.MainWindow"), \
         patch("djmidi.gui.app.configure_logging") as mock_configure, \
         patch("djmidi.gui.app.PluginPreferences.load", return_value=saved):
        mock_qapp.return_value.exec.return_value = 0
        from djmidi.gui.app import run
        run(["--log-file", "/explicit/cli.log"])
    mock_configure.assert_called_once_with("INFO", "/explicit/cli.log")


def test_run_falls_back_to_saved_preference_log_path_without_cli_override():
    saved = PluginPreferences(log_path="/saved/preference.log")
    with patch("djmidi.gui.app.QApplication") as mock_qapp, \
         patch("djmidi.gui.app.MainWindow"), \
         patch("djmidi.gui.app.configure_logging") as mock_configure, \
         patch("djmidi.gui.app.PluginPreferences.load", return_value=saved):
        mock_qapp.return_value.exec.return_value = 0
        from djmidi.gui.app import run
        run([])
    mock_configure.assert_called_once_with("INFO", "/saved/preference.log")


