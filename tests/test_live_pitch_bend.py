"""Live pitch bend (issue #436): read, logged, exported and captured, never a
note/CC trigger and never a layout hit."""

import mido
import pytest

from djmidi import catalog
from djmidi.controller_sync import sync_set_from_events
from djmidi.hardware_session import (
    CHECKS_BY_ID,
    CheckResult,
    captured_from_event,
    verdict,
)
from djmidi.midi_export import events_to_midi_file
from djmidi.midi_io import PITCH_BEND, MidiEvent, mido_message_to_event
from djmidi.midi_learn import trigger_from_event
from djmidi.midi_macros import MacroTrigger, step_from_event
from djmidi.stage import format_stage_line


def _bend(value=9000, channel="3", direction="in"):
    return MidiEvent(direction, channel, PITCH_BEND, "0", str(value), 1.0, "CMD Studio 4a")


@pytest.mark.parametrize(("pitch", "value"), [(-8192, "0"), (0, "8192"), (8191, "16383")])
def test_pitchwheel_becomes_a_pitch_bend_event(pitch, value):
    event = mido_message_to_event(mido.Message("pitchwheel", channel=2, pitch=pitch), "in", 1.0, "port")
    assert (event.event_type, event.channel, event.data1, event.data2) == (PITCH_BEND, "3", "0", value)


def test_other_unmapped_messages_are_still_dropped():
    assert mido_message_to_event(mido.Message("program_change", program=3), "in") is None


def test_note_and_cc_consumers_ignore_pitch_bend():
    event = _bend()
    assert trigger_from_event(event) is None
    assert MacroTrigger.from_event(event) is None
    assert step_from_event(event) is None
    assert sync_set_from_events("Behringer CMD Studio 4a", [event]).messages == ()
    assert catalog.lookup("3", PITCH_BEND, "0") == []


def test_profile_check_ignores_pitch_bend():
    from djmidi.gui.profile_check import press_from_event

    assert press_from_event(_bend()) is None


def test_stage_line_shows_the_raw_value():
    assert format_stage_line(_bend(9000)).endswith("9000")


def test_midi_export_writes_pitch_bend():
    events = [_bend(0), _bend(16383), _bend(20000)]  # the last one is out of range
    midi = events_to_midi_file(events)
    bends = [m for track in midi.tracks for m in track if m.type == "pitchwheel"]
    assert [(m.channel, m.pitch) for m in bends] == [(2, -8192), (2, 8191)]


def test_hardware_session_captures_pitch_bend():
    message = captured_from_event(_bend(8200))
    assert message is not None and message.event_type == PITCH_BEND and message.data2 == 8200
    check = CHECKS_BY_ID["cmd-studio-4a-jog"]
    text = verdict(check, CheckResult(captured=[message, message]))
    assert "Pitch Bend ch 3 #0 ×2" in text


def test_main_window_keeps_the_selection_on_pitch_bend():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    window._update_layout_selection("8", "Note On", "0")
    selected = set(window.layout_view._selected_keys)
    assert selected  # a DDJ-XP2 pad
    window._on_live_midi_event(_bend())
    assert window.layout_view._selected_keys == selected
    window.close()
