"""Extended MidiMonitor tests – uses mocked mido ports to avoid requiring
physical hardware or a running MIDI driver."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import mido

from seratomidiconf.midi_io import (
    MidiMonitor,
    list_input_ports,
    list_output_ports,
    send_midi_message,
)

# ─── list_input_ports ─────────────────────────────────────────────────────────

def test_list_input_ports_returns_list():
    ports = list_input_ports()
    assert isinstance(ports, list)


# ─── MidiMonitor.open_input / close_input ─────────────────────────────────────

def test_open_input_stores_port():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    with patch("mido.open_input", return_value=mock_port):
        monitor.open_input("IAC Bus 1")
    assert "IAC Bus 1" in monitor._input_ports


def test_open_input_idempotent():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    with patch("mido.open_input", return_value=mock_port):
        monitor.open_input("IAC Bus 1")
        monitor.open_input("IAC Bus 1")  # second call should be no-op
    assert len(monitor._input_ports) == 1


def test_close_input_removes_and_closes_port():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    with patch("mido.open_input", return_value=mock_port):
        monitor.open_input("IAC Bus 1")
    monitor.close_input("IAC Bus 1")
    assert "IAC Bus 1" not in monitor._input_ports
    mock_port.close.assert_called_once()


def test_close_input_unknown_name_does_not_raise():
    monitor = MidiMonitor()
    monitor.close_input("nonexistent")  # must not raise


# ─── MidiMonitor.open_virtual_monitor / close_virtual_monitor ─────────────────

def test_open_virtual_monitor_creates_virtual_input():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    with patch("mido.open_input", return_value=mock_port) as mock_open:
        monitor.open_virtual_monitor()
        mock_open.assert_called_once_with(MidiMonitor.VIRTUAL_MONITOR_NAME, virtual=True)
    assert monitor._virtual_port is mock_port


def test_open_virtual_monitor_idempotent():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    with patch("mido.open_input", return_value=mock_port) as mock_open:
        monitor.open_virtual_monitor()
        monitor.open_virtual_monitor()
        assert mock_open.call_count == 1


def test_close_virtual_monitor_closes_and_clears():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    with patch("mido.open_input", return_value=mock_port):
        monitor.open_virtual_monitor()
    monitor.close_virtual_monitor()
    assert monitor._virtual_port is None
    mock_port.close.assert_called_once()


def test_close_virtual_monitor_when_none_does_not_raise():
    monitor = MidiMonitor()
    monitor.close_virtual_monitor()  # must not raise


# ─── MidiMonitor.close_all ────────────────────────────────────────────────────

def test_close_all_closes_inputs_and_virtual():
    monitor = MidiMonitor()
    port_a, port_b, virtual = MagicMock(), MagicMock(), MagicMock()
    with patch("mido.open_input", side_effect=[port_a, port_b, virtual]):
        monitor.open_input("Port A")
        monitor.open_input("Port B")
        monitor.open_virtual_monitor()
    monitor.close_all()
    port_a.close.assert_called_once()
    port_b.close.assert_called_once()
    virtual.close.assert_called_once()
    assert not monitor._input_ports
    assert monitor._virtual_port is None


# ─── MidiMonitor.poll ─────────────────────────────────────────────────────────

def test_poll_yields_events_from_input_port():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    note_msg = mido.Message("note_on", channel=0, note=64, velocity=100)
    mock_port.iter_pending.return_value = [note_msg]
    with patch("mido.open_input", return_value=mock_port):
        monitor.open_input("IAC Bus 1")
    events = monitor.poll()
    assert len(events) == 1
    assert events[0].event_type == "Note On"
    assert events[0].data1 == "64"
    assert events[0].direction == "in"
    assert events[0].port == "IAC Bus 1"


def test_poll_filters_unsupported_message_types():
    monitor = MidiMonitor()
    mock_port = MagicMock()
    mock_port.iter_pending.return_value = [mido.Message("clock"), mido.Message("pitchwheel", pitch=0)]
    with patch("mido.open_input", return_value=mock_port):
        monitor.open_input("IAC Bus 1")
    events = monitor.poll()
    assert events == []


def test_poll_yields_events_from_virtual_port():
    monitor = MidiMonitor()
    mock_virtual = MagicMock()
    cc_msg = mido.Message("control_change", channel=3, control=10, value=64)
    mock_virtual.iter_pending.return_value = [cc_msg]
    with patch("mido.open_input", return_value=mock_virtual):
        monitor.open_virtual_monitor()
    events = monitor.poll()
    assert len(events) == 1
    assert events[0].direction == "out"
    assert events[0].event_type == "Control Change"


def test_poll_empty_when_no_ports_open():
    monitor = MidiMonitor()
    assert monitor.poll() == []


# ─── MIDI output helpers ──────────────────────────────────────────────────────


def test_list_output_ports_returns_list():
    ports = list_output_ports()
    assert isinstance(ports, list)


def test_send_midi_message_sends_note_on_with_1_based_channel():
    output = MagicMock()
    output_ctx = MagicMock()
    output_ctx.__enter__.return_value = output
    with patch("mido.open_output", return_value=output_ctx), patch("mido.Message") as mock_message:
        send_midi_message(
            output_port_name="Port A",
            event_type="Note On",
            channel_1_based=8,
            data1=64,
            data2=127,
        )
    mock_message.assert_called_once_with("note_on", channel=7, note=64, velocity=127)
    output.send.assert_called_once()


def test_send_midi_message_sends_cc_alias():
    output = MagicMock()
    output_ctx = MagicMock()
    output_ctx.__enter__.return_value = output
    with patch("mido.open_output", return_value=output_ctx), patch("mido.Message") as mock_message:
        send_midi_message(
            output_port_name="Port A",
            event_type="cc",
            channel_1_based=1,
            data1=10,
            data2=64,
        )
    mock_message.assert_called_once_with("control_change", channel=0, control=10, value=64)


def test_send_midi_message_rejects_invalid_channel():
    try:
        send_midi_message(
            output_port_name="Port A",
            event_type="note_on",
            channel_1_based=0,
            data1=64,
            data2=127,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "channel" in str(exc)


def test_send_midi_message_rejects_invalid_data_byte():
    try:
        send_midi_message(
            output_port_name="Port A",
            event_type="note_on",
            channel_1_based=1,
            data1=128,
            data2=0,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "data1" in str(exc)


def test_send_midi_message_rejects_unknown_event_type():
    try:
        send_midi_message(
            output_port_name="Port A",
            event_type="pitch_bend",
            channel_1_based=1,
            data1=0,
            data2=0,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Unsupported event_type" in str(exc)


