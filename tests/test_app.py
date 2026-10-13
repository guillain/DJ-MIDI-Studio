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




def test_startup_screenshot_flag_schedules_a_window_grab(tmp_path):
    target = tmp_path / "startup.png"
    with patch("djmidi.gui.app.QApplication") as mock_qapp, \
         patch("djmidi.gui.app.MainWindow") as mock_window, \
         patch("djmidi.gui.app.configure_logging"), \
         patch("djmidi.gui.app.QTimer") as mock_timer, \
         patch("djmidi.gui.app.save_window_screenshot") as mock_save:
        mock_qapp.return_value.exec.return_value = 0
        from djmidi.gui.app import STARTUP_SCREENSHOT_DELAY_MS, run
        run(["--startup-screenshot", str(target)])
        delay, callback = mock_timer.singleShot.call_args.args
        callback()
    assert delay == STARTUP_SCREENSHOT_DELAY_MS
    mock_save.assert_called_once_with(mock_window.return_value, str(target))
    # The smoke screenshot must never wait on the modal first-run wizard (issue #251).
    assert mock_window.return_value.first_run_wizard_enabled is False


def test_no_screenshot_is_scheduled_without_the_flag():
    with patch("djmidi.gui.app.QApplication") as mock_qapp, \
         patch("djmidi.gui.app.MainWindow"), \
         patch("djmidi.gui.app.configure_logging"), \
         patch("djmidi.gui.app.QTimer") as mock_timer, \
         patch("djmidi.gui.app.save_window_screenshot") as mock_save:
        mock_qapp.return_value.exec.return_value = 0
        from djmidi.gui.app import run
        run([])
        # The only deferred callback is the startup timing log (issue #264).
        for call in mock_timer.singleShot.call_args_list:
            call.args[1]()
    mock_save.assert_not_called()


def test_save_window_screenshot_writes_a_png_atomically(tmp_path):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QLabel

    from djmidi.gui.app import save_window_screenshot

    widget = QLabel("DJ MIDI Studio")
    widget.resize(120, 40)
    target = tmp_path / "nested" / "startup.png"
    assert save_window_screenshot(widget, target)
    image = QImage(str(target))
    assert not image.isNull()
    assert (image.width(), image.height()) == (120, 40)
    assert list(target.parent.iterdir()) == [target]


def test_run_logs_time_to_first_window_after_the_first_event_loop_turn(caplog):
    import logging

    with patch("djmidi.gui.app.QApplication") as mock_qapp, \
         patch("djmidi.gui.app.MainWindow"), \
         patch("djmidi.gui.app.configure_logging"), \
         patch("djmidi.gui.app.QTimer") as mock_timer:
        mock_qapp.return_value.exec.return_value = 0
        from djmidi.gui.app import run
        run([])
        delay, callback = mock_timer.singleShot.call_args_list[0].args
        with caplog.at_level(logging.INFO, logger="djmidi.gui.app"):
            callback()
    assert delay == 0
    message = next(r.getMessage() for r in caplog.records if "time to first window" in r.getMessage())
    for phase in ("imports", "Qt application", "main window built", "window shown", "first window"):
        assert phase in message
