import mido

from seratomidiconf import catalog
from seratomidiconf.midi_io import mido_message_to_event


def test_note_on_converts_with_1_indexed_channel():
    msg = mido.Message("note_on", channel=7, note=64, velocity=127)
    event = mido_message_to_event(msg, "in", timestamp=0.0)
    assert event is not None
    assert event.channel == "8"  # mido channel 7 (0-indexed) -> our "8"
    assert event.event_type == "Note On"
    assert event.data1 == "64"
    assert event.data2 == "127"
    assert event.direction == "in"


def test_note_off_converts():
    msg = mido.Message("note_off", channel=0, note=10, velocity=0)
    event = mido_message_to_event(msg, "in", timestamp=0.0)
    assert event is not None
    assert event.channel == "1"
    assert event.event_type == "Note Off"


def test_control_change_converts():
    msg = mido.Message("control_change", channel=4, control=20, value=64)
    event = mido_message_to_event(msg, "out", timestamp=0.0)
    assert event is not None
    assert event.channel == "5"
    assert event.event_type == "Control Change"
    assert event.data1 == "20"
    assert event.data2 == "64"
    assert event.direction == "out"


def test_unmapped_message_type_returns_none():
    msg = mido.Message("pitchwheel", channel=0, pitch=0)
    assert mido_message_to_event(msg, "in") is None

    clock_msg = mido.Message("clock")
    assert mido_message_to_event(clock_msg, "in") is None


def test_live_note_on_resolves_via_catalog_like_the_real_sample_file():
    # channel=7/note=64 was the exact message sent through IAC and confirmed
    # received during this feature's planning; it matches the DDJ-XP2 pad
    # trigger for ch8/#64 already used throughout the sample fixture.
    msg = mido.Message("note_on", channel=7, note=64, velocity=127)
    event = mido_message_to_event(msg, "in", timestamp=0.0)
    assert event is not None
    hits = catalog.lookup(event.channel, event.event_type, event.data1)
    assert any(h.controller == "DDJ-XP2" and h.name == "Deck 1 Pad 13 (PAD MODE 5)" for h in hits)


def test_timestamp_defaults_to_monotonic_clock_when_not_given():
    msg = mido.Message("note_on", channel=0, note=1, velocity=1)
    event = mido_message_to_event(msg, "in")
    assert event is not None
    assert event.timestamp > 0


def test_port_defaults_to_empty_and_can_be_set():
    msg = mido.Message("note_on", channel=0, note=1, velocity=1)
    assert mido_message_to_event(msg, "in", timestamp=0.0).port == ""
    event = mido_message_to_event(msg, "in", timestamp=0.0, port="IAC Driver Bus 1")
    assert event is not None
    assert event.port == "IAC Driver Bus 1"
