"""Extended live monitor tests: port refresh, start/stop cycle, event routing."""
from __future__ import annotations

from unittest.mock import patch

from seratomidiconf.gui.live_monitor import LiveMonitorView
from seratomidiconf.midi_io import MidiEvent


def _view() -> LiveMonitorView:
    return LiveMonitorView()


# ─── _refresh_ports ───────────────────────────────────────────────────────────

def test_refresh_ports_populates_list():
    view = _view()
    with patch("seratomidiconf.gui.live_monitor.list_input_ports", return_value=["Port A", "Port B"]):
        view._refresh_ports()
    assert view._port_list.count() == 2


def test_refresh_ports_restores_checked_state():
    view = _view()
    with patch("seratomidiconf.gui.live_monitor.list_input_ports", return_value=["Port A"]):
        view._refresh_ports()
    # Manually check port A
    from PySide6.QtCore import Qt
    view._port_list.item(0).setCheckState(Qt.CheckState.Checked)
    with patch("seratomidiconf.gui.live_monitor.list_input_ports", return_value=["Port A", "Port B"]):
        view._refresh_ports()
    assert view._port_list.item(0).checkState() == Qt.CheckState.Checked


def test_refresh_ports_empty_when_no_ports():
    view = _view()
    with patch("seratomidiconf.gui.live_monitor.list_input_ports", return_value=[]):
        view._refresh_ports()
    assert view._port_list.count() == 0


# ─── _start / _stop / _toggle_running ─────────────────────────────────────────

def test_start_sets_running_flag_and_updates_label():
    view = _view()
    with patch("seratomidiconf.gui.live_monitor.list_input_ports", return_value=["Port A"]):
        view._refresh_ports()
    with patch.object(view._monitor, "open_input"):
        view._start()
    assert view._running is True
    assert "Running" in view._status_label.text()


def test_stop_clears_running_flag_and_updates_label():
    view = _view()
    with patch.object(view._monitor, "open_input"), \
         patch.object(view._monitor, "close_all"):
        view._running = True
        view._stop()
    assert view._running is False
    assert "Stopped" in view._status_label.text()


def test_toggle_running_starts_when_stopped():
    view = _view()
    with patch("seratomidiconf.gui.live_monitor.list_input_ports", return_value=[]):
        view._refresh_ports()
    with patch.object(view._monitor, "open_input"):
        view._toggle_running()
    assert view._running is True


def test_toggle_running_stops_when_running():
    view = _view()
    with patch.object(view._monitor, "open_input"), \
         patch.object(view._monitor, "close_all"):
        view._running = True
        view._toggle_running()
    assert view._running is False


def test_shutdown_when_running_calls_stop():
    view = _view()
    with patch.object(view, "_stop") as mock_stop:
        view._running = True
        view.shutdown()
    mock_stop.assert_called_once()


# ─── _poll ────────────────────────────────────────────────────────────────────

def test_poll_appends_event_and_emits_signal():
    view = _view()
    received: list[MidiEvent] = []
    view.eventReceived.connect(received.append)
    event = MidiEvent(direction="in", channel="1", event_type="Note On", data1="64", data2="100", timestamp=0.0)
    with patch.object(view._monitor, "poll", return_value=[event]):
        view._poll()
    assert len(received) == 1
    assert view._log.rowCount() == 1


def test_poll_with_virtual_checkbox_start():
    view = _view()
    view._virtual_checkbox.setChecked(True)
    with patch("seratomidiconf.gui.live_monitor.list_input_ports", return_value=[]):
        view._refresh_ports()
    with patch.object(view._monitor, "open_virtual_monitor") as mock_virtual, \
         patch.object(view._monitor, "open_input"):
        view._start()
    mock_virtual.assert_called_once()

