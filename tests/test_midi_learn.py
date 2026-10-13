"""Tests for djmidi.midi_learn (Qt-free MIDI Learn core, issue #220)."""
from __future__ import annotations

from djmidi.midi_io import MidiEvent
from djmidi.midi_learn import (
    LearnedTrigger,
    describe_conflicts,
    find_parent_control,
    find_trigger_conflicts,
    trigger_from_event,
    trigger_of,
    unique_controls,
)
from djmidi.model import Control, MappingElement, MidiConfig, UserIO


def _event(event_type: str = "Note On", data1: str = "12", data2: str = "127", direction: str = "in") -> MidiEvent:
    return MidiEvent(direction=direction, channel="3", event_type=event_type, data1=data1, data2=data2, timestamp=0.0)


def _control(channel: str = "1", control: str = "10", *tags: str) -> Control:
    mappings = [MappingElement(tag=tag, deck_id="1") for tag in tags]
    return Control(channel=channel, event_type="Note On", control=control, userios=[UserIO("click", mappings)])


def test_note_on_press_is_learned():
    assert trigger_from_event(_event()) == LearnedTrigger("3", "Note On", "12")


def test_control_change_is_learned_whatever_its_value():
    assert trigger_from_event(_event("Control Change", "7", "0")) == LearnedTrigger("3", "Control Change", "7")


def test_release_and_velocity_zero_are_ignored():
    assert trigger_from_event(_event("Note Off", data2="0")) is None
    assert trigger_from_event(_event("Note On", data2="0")) is None
    assert trigger_from_event(_event("Note On", data2="garbage")) is None


def test_output_direction_is_ignored():
    assert trigger_from_event(_event(direction="out")) is None


def test_trigger_label_and_trigger_of():
    control = _control("8", "64")
    assert trigger_of(control) == LearnedTrigger("8", "Note On", "64")
    assert trigger_of(control).label() == "ch8 Note On #64"


def test_conflicts_exclude_the_controls_being_moved():
    moved = _control("1", "10", "play")
    clash = _control("2", "20", "cue")
    other = _control("2", "21", "sync")
    config = MidiConfig(controls=[moved, clash, other])
    trigger = LearnedTrigger("2", "Note On", "20")
    assert find_trigger_conflicts(config, trigger, [moved]) == [clash]
    assert find_trigger_conflicts(config, trigger, [moved, clash]) == []
    assert find_trigger_conflicts(None, trigger) == []


def test_conflict_event_type_must_match():
    config = MidiConfig(controls=[_control("2", "20", "cue")])
    assert find_trigger_conflicts(config, LearnedTrigger("2", "Control Change", "20")) == []


def test_describe_conflicts_dedupes_serato_duplicates_and_caps():
    duplicates = [_control("2", "20", "cue") for _ in range(10)]
    assert describe_conflicts(duplicates) == ["cue deck 1 [click]"]
    many = [_control("2", "20", *[f"f{i}" for i in range(12)])]
    lines = describe_conflicts(many)
    assert len(lines) == 9
    assert lines[-1] == "… and 4 more"


def test_unique_controls_keeps_order_by_identity():
    a, b = _control(), _control()
    assert unique_controls([a, b, a]) == [a, b]


def test_find_parent_control_by_identity():
    target = _control("1", "10", "play")
    mapping = target.userios[0].mappings[0]
    lookalike = MappingElement(tag="play", deck_id="1")
    config = MidiConfig(controls=[_control("1", "11", "play"), target])
    assert find_parent_control(config, mapping) is target
    assert find_parent_control(config, lookalike) is None
    assert find_parent_control(None, mapping) is None
