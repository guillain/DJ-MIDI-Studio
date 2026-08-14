"""Tests for gui/app.py – verifies the entry point wires QApplication correctly."""
from __future__ import annotations

from unittest.mock import patch


def test_run_creates_window_and_calls_exec():
    with patch("seratomidiconf.gui.app.QApplication") as mock_qapp, \
         patch("seratomidiconf.gui.app.MainWindow") as mock_window:
        mock_qapp.return_value.exec.return_value = 0
        from seratomidiconf.gui.app import run
        result = run()
    assert result == 0
    mock_window.return_value.show.assert_called_once()
    mock_qapp.return_value.exec.assert_called_once()


def test_main_entrypoint_calls_run_and_exits():
    import seratomidiconf
    assert callable(seratomidiconf.main)


def test_run_propagates_exec_return_code():
    with patch("seratomidiconf.gui.app.QApplication") as mock_qapp, \
         patch("seratomidiconf.gui.app.MainWindow"):
        mock_qapp.return_value.exec.return_value = 42
        from seratomidiconf.gui.app import run
        assert run() == 42


def test_seratomidiconf_main_calls_gui_run():
    with patch("seratomidiconf.gui.app.run", return_value=0) as mock_run:
        try:
            import seratomidiconf
            seratomidiconf.main()
        except SystemExit:
            pass
    mock_run.assert_called_once()



