import pytest

from djmidi.midi_api import MidiMessage, MidiPortInfo


def test_midi_port_info_exposes_web_midi_shaped_identity():
    port = MidiPortInfo(id="usb-1", name="DDJ-XP2", type="input")
    assert port.id == "usb-1"
    assert port.state == "connected"
    assert port.connection == "closed"


def test_midi_message_keeps_raw_bytes_and_sysex():
    message = MidiMessage(data=b"\xf0\x01\x02\xf7", received_time=12.5, port_id="usb-1")
    assert message.status == 0xF0
    assert message.is_sysex


def test_midi_message_rejects_empty_data():
    with pytest.raises(ValueError, match="cannot be empty"):
        MidiMessage(data=b"", received_time=0)
