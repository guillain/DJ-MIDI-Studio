from __future__ import annotations

from seratomidiconf.catalog._registry import ControlInfo
from seratomidiconf.midi_io import MidiEvent
from seratomidiconf.session_player import (
    play_control_info_entries,
    replay_midi_events,
    send_control_info_entry,
)


def test_send_control_info_entry_sends_note_click(monkeypatch):
    import seratomidiconf.session_player as session_player_mod

    sent = []
    entry = ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10")
    monkeypatch.setattr(session_player_mod, "send_midi_message", lambda **kwargs: sent.append(kwargs))
    count = send_control_info_entry("Port A", entry, 127)
    assert count == 2
    assert sent[0]["event_type"] == "note_on"
    assert sent[1]["event_type"] == "note_off"


def test_send_control_info_entry_sends_cc(monkeypatch):
    import seratomidiconf.session_player as session_player_mod

    sent = []
    entry = ControlInfo("MiniPad", "KNOB", "B", "CC", ("2",), "20")
    monkeypatch.setattr(session_player_mod, "send_midi_message", lambda **kwargs: sent.append(kwargs))
    count = send_control_info_entry("Port A", entry, 64)
    assert count == 1
    assert sent[0]["event_type"] == "control_change"


def test_play_control_info_entries_counts_skipped_invalid_rows(monkeypatch):
    import seratomidiconf.session_player as session_player_mod

    sent = []
    entries = [
        ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10"),
        ControlInfo("MiniPad", "PAD", "B", "NOTE", ("1",), "abc"),
    ]
    monkeypatch.setattr(session_player_mod, "send_midi_message", lambda **kwargs: sent.append(kwargs))
    stats = play_control_info_entries("Port A", entries, 127)
    assert stats.sent_messages == 2
    assert stats.skipped_entries == 1


def test_replay_midi_events_preserves_recorded_values_and_order():
    sent = []
    events = [
        MidiEvent("in", "2", "Note On", "60", "99", 1.0, "Controller"),
        MidiEvent("in", "2", "Note Off", "60", "12", 1.2, "Controller"),
        MidiEvent("in", "3", "Control Change", "10", "64", 1.4, "Controller"),
    ]

    stats = replay_midi_events("MIDI Out", events, sender=lambda **kwargs: sent.append(kwargs))

    assert stats.sent_messages == 3
    assert stats.skipped_entries == 0
    assert [message["event_type"] for message in sent] == ["Note On", "Note Off", "Control Change"]
    assert sent[0]["output_port_name"] == "MIDI Out"
    assert sent[0]["channel_1_based"] == 2
    assert sent[0]["data1"] == 60
    assert sent[0]["data2"] == 99


def test_replay_midi_events_skips_invalid_recorded_event():
    sent = []
    events = [MidiEvent("in", "17", "Note On", "60", "127", 1.0)]

    stats = replay_midi_events("MIDI Out", events, sender=lambda **kwargs: sent.append(kwargs))

    assert stats.sent_messages == 0
    assert stats.skipped_entries == 1
    assert sent == []


def test_send_control_info_entry_rejects_invalid_channel_and_type():
    import pytest

    sender = lambda **kwargs: None
    with pytest.raises(ValueError, match="Channel"):
        send_control_info_entry(
            "Port A",
            ControlInfo("MiniPad", "PAD", "A", "NOTE", ("17",), "10"),
            127,
            sender=sender,
        )
    with pytest.raises(ValueError, match="Unsupported row Type"):
        send_control_info_entry(
            "Port A",
            ControlInfo("MiniPad", "PAD", "A", "OTHER", ("1",), "10"),
            127,
            sender=sender,
        )
