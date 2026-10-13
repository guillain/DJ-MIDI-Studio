"""Qt-free core of Stage Mode (issue #230): line formatting and the bounded log."""

import pytest

from djmidi.catalog import ControlInfo
from djmidi.midi_io import MidiEvent
from djmidi.stage import DEFAULT_MAX_LINES, StageLog, format_stage_line, hits_for_port


def _event(event_type="Note On", data2="127", port="", direction="in", data1="11"):
    return MidiEvent(direction, "1", event_type, data1, data2, 0.0, port)


def _hit(controller, name):
    return ControlInfo(controller, "DECK", name, "NOTE", ("1",), "11")


def test_unknown_trigger_shows_the_raw_message():
    assert format_stage_line(_event(event_type="Control Change", data2="64")) == (
        "IN · Ch 1 Control Change 11 · 64"
    )


def test_note_values_read_on_and_off():
    assert format_stage_line(_event(data2="127")).endswith("· ON")
    assert format_stage_line(_event(data2="0")).endswith("· OFF")
    assert format_stage_line(_event(event_type="Note Off", data2="64")).endswith("· OFF")


def test_known_control_shows_controller_and_name():
    line = format_stage_line(_event(direction="out"), [_hit("XDJ-XZ", "PLAY/PAUSE")])
    assert line == "OUT · XDJ-XZ PLAY/PAUSE · ON"


def test_source_port_narrows_ambiguous_hits():
    hits = [_hit("XDJ-XZ", "PLAY/PAUSE"), _hit("DDJ-REV1", "CUE")]
    assert hits_for_port(hits, "XDJ-XZ MIDI 1") == [hits[0]]
    assert hits_for_port(hits, "") == hits
    assert "DDJ-REV1" not in format_stage_line(_event(port="xdj-xz port"), hits)


def test_duplicate_hits_are_listed_once():
    hits = [_hit("XDJ-XZ", "PLAY/PAUSE"), _hit("XDJ-XZ", "PLAY/PAUSE")]
    assert format_stage_line(_event(), hits) == "IN · XDJ-XZ PLAY/PAUSE · ON"


def test_log_is_newest_first_and_bounded():
    log = StageLog(max_lines=3)
    for n in range(5):
        log.add(f"line {n}")
    assert log.lines() == ["line 4", "line 3", "line 2"]
    assert log.max_lines == 3
    log.clear()
    assert log.lines() == []


def test_log_default_size_and_rejects_zero():
    assert StageLog().max_lines == DEFAULT_MAX_LINES
    with pytest.raises(ValueError):
        StageLog(max_lines=0)
