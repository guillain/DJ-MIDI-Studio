import json
from contextlib import contextmanager

import pytest

from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.midi_io import MidiEvent
from djmidi.midi_macros import (
    MacroStep,
    MacroTrigger,
    MidiMacro,
    load_macros,
    macro_file_name,
    macro_from_sync_set,
    macro_schedule,
    macros_for_event,
    resolve_macro_port,
    retriggers_itself,
    run_macro,
    save_macros,
    steps_from_rows,
    validate_macros,
)

PRESS = SyncMessage("Note On", 1, 11, 127)
RELEASE = SyncMessage("Note Off", 1, 11, 0)
CC = SyncMessage("Control Change", 2, 7, 64)


def _macro(name="Loop", port="PIONEER DDJ-XP2", shortcut="Ctrl+Shift+1"):
    return MidiMacro(name, port, (MacroStep(PRESS), MacroStep(RELEASE, 200), MacroStep(CC, 50)), shortcut)


def test_round_trips_through_dict():
    macro = _macro()
    raw = macro.to_dict()
    assert raw["version"] == 1
    assert raw["steps"][1] == {**RELEASE.to_dict(), "delay_ms": 200}
    assert MidiMacro.from_dict(json.loads(json.dumps(raw))) == macro
    assert macro.duration_ms == 250


def test_from_dict_defaults_and_rejects_bad_input():
    assert MidiMacro.from_dict({"name": " Fx ", "steps": [PRESS.to_dict()]}) == MidiMacro("Fx", "", (MacroStep(PRESS),))
    with pytest.raises(ValueError):
        MidiMacro.from_dict({"name": "  "})
    with pytest.raises(ValueError):
        MidiMacro.from_dict({"name": "x", "steps": [{**PRESS.to_dict(), "delay_ms": -1}]})
    with pytest.raises(TypeError):
        MidiMacro.from_dict({"name": "x", "steps": "nope"})


def test_steps_from_rows_validates_and_names_the_bad_row():
    assert steps_from_rows([("Note On", "1", "11", "127", ""), ("cc", 2, 7, 64, "50")]) == (
        MacroStep(PRESS),
        MacroStep(CC, 50),
    )
    with pytest.raises(ValueError, match="Step 2: delay"):
        steps_from_rows([("Note On", 1, 11, 127, 0), ("Note On", 1, 11, 127, "999999")])
    with pytest.raises(ValueError, match="Step 1: channel"):
        steps_from_rows([("Note On", 17, 11, 127, 0)])


def test_validate_macros_flags_duplicate_names_and_shortcuts():
    assert validate_macros([_macro("A", shortcut="Ctrl+1"), _macro("B", shortcut="")]) == []
    problems = validate_macros([_macro("A", shortcut="Ctrl+1"), _macro("a", shortcut="Ctrl+1")])
    assert any("named" in problem for problem in problems)
    assert any("same shortcut" in problem for problem in problems)


def test_schedule_accumulates_delays():
    assert macro_schedule(_macro()) == [(0, PRESS), (200, RELEASE), (250, CC)]


def test_port_resolution_matches_like_sync():
    macro = _macro(port="DDJ-XP2")
    assert resolve_macro_port(macro, ["IAC Bus", "PIONEER DDJ-XP2 MIDI 1"]) == "PIONEER DDJ-XP2 MIDI 1"
    assert resolve_macro_port(macro, ["IAC Bus"]) is None
    assert resolve_macro_port(_macro(port=""), ["IAC Bus"]) is None


def test_run_macro_sends_in_order_and_sleeps_each_delay():
    sent, slept = [], []
    result = run_macro(_macro(), ["PIONEER DDJ-XP2"], sender=lambda **kw: sent.append(kw), sleep=slept.append)
    assert result.ok and result.sent == 3 and result.total == 3
    assert slept == [0.2, 0.05]
    assert [(kw["event_type"], kw["data2"]) for kw in sent] == [
        ("Note On", 127),
        ("Note Off", 0),
        ("Control Change", 64),
    ]
    assert {kw["output_port_name"] for kw in sent} == {"PIONEER DDJ-XP2"}
    assert "sent 3 message(s)" in result.summary()


def test_run_macro_reports_why_it_did_not_play():
    assert run_macro(MidiMacro("Empty", "x"), ["x"]).error == "no message to send"
    assert run_macro(_macro(port=""), ["x"]).error == "no output port chosen"
    unplugged = run_macro(_macro(), ["IAC Bus"], sender=lambda **kw: pytest.fail("must not send"))
    assert not unplugged.ok and "not connected" in unplugged.summary()


def test_run_macro_stops_at_a_failing_send():
    calls = []

    def sender(**kw):
        calls.append(kw)
        if len(calls) == 2:
            raise OSError("port vanished")

    result = run_macro(_macro(), ["PIONEER DDJ-XP2"], sender=sender, sleep=lambda _s: None)
    assert (result.ok, result.sent, result.error) == (False, 1, "port vanished")
    assert "stopped after 1/3" in result.summary()


class _FakeOutput:
    """Counts how often a port is opened and closed (issue #308)."""

    def __init__(self, fail_on=None, fail_open=False):
        self.opened, self.closed, self.sent = [], 0, []
        self._fail_on, self._fail_open = fail_on, fail_open

    @contextmanager
    def __call__(self, port):
        if self._fail_open:
            raise OSError("cannot open")
        self.opened.append(port)
        try:

            def send(**kw):
                if len(self.sent) + 1 == self._fail_on:
                    raise OSError("port vanished")
                self.sent.append(kw)

            yield send
        finally:
            self.closed += 1


def test_run_macro_opens_its_port_once_for_the_whole_run():
    output = _FakeOutput()
    result = run_macro(_macro(), ["PIONEER DDJ-XP2"], sleep=lambda _s: None, port_opener=output)
    assert result.ok and result.sent == 3
    assert output.opened == ["PIONEER DDJ-XP2"] and output.closed == 1
    assert [kw["data1"] for kw in output.sent] == [11, 11, 7]
    assert "output_port_name" not in output.sent[0]


def test_run_macro_sleeps_with_the_port_open():
    output, open_while_sleeping = _FakeOutput(), []
    run_macro(
        _macro(),
        ["PIONEER DDJ-XP2"],
        sleep=lambda _s: open_while_sleeping.append(len(output.opened) - output.closed),
        port_opener=output,
    )
    assert open_while_sleeping == [1, 1]


def test_run_macro_releases_the_port_during_a_long_sleep():
    """Issue #336: a wait over HOLD_PORT_MAX_DELAY_MS sleeps with the port
    closed, so another client (Sync) can open it meanwhile."""
    output, open_while_sleeping = _FakeOutput(), []
    macro = MidiMacro("Long", "PIONEER DDJ-XP2", (MacroStep(PRESS), MacroStep(RELEASE, 2000), MacroStep(CC)))
    result = run_macro(
        macro,
        ["PIONEER DDJ-XP2"],
        sleep=lambda _s: open_while_sleeping.append(len(output.opened) - output.closed),
        port_opener=output,
    )
    assert result.ok and result.sent == 3
    assert open_while_sleeping == [0]
    assert len(output.opened) == 2 and output.closed == 2  # reopened once, for the last two steps


def test_run_macro_closes_its_port_when_a_send_fails():
    output = _FakeOutput(fail_on=2)
    result = run_macro(_macro(), ["PIONEER DDJ-XP2"], sleep=lambda _s: None, port_opener=output)
    assert (result.ok, result.sent, result.error) == (False, 1, "port vanished")
    assert output.closed == 1


def test_run_macro_reports_a_port_that_will_not_open():
    result = run_macro(_macro(), ["PIONEER DDJ-XP2"], port_opener=_FakeOutput(fail_open=True))
    assert (result.ok, result.sent, result.error) == (False, 0, "cannot open")


def test_run_macro_uses_open_midi_output_by_default(monkeypatch):
    from djmidi import midi_io

    output = _FakeOutput()
    monkeypatch.setattr(midi_io, "open_midi_output", output)
    monkeypatch.setattr(midi_io, "send_midi_message", lambda **kw: pytest.fail("must not reopen per step"))
    result = run_macro(_macro(), ["PIONEER DDJ-XP2"], sleep=lambda _s: None)
    assert result.ok and output.opened == ["PIONEER DDJ-XP2"] and len(output.sent) == 3


def test_macro_from_sync_set_copies_messages_without_delays():
    sync_set = ControllerSyncSet("DDJ-XP2", "", (PRESS, CC))
    macro = macro_from_sync_set("Init", sync_set)
    assert macro.output_port == "DDJ-XP2"
    assert macro.steps == (MacroStep(PRESS), MacroStep(CC))


def test_store_writes_one_file_per_macro_and_mirrors_deletions(tmp_path):
    first, second = _macro("Loop roll / 1"), _macro("FX on", shortcut="")
    save_macros(tmp_path, [first, second])
    assert sorted(path.name for path in tmp_path.glob("*.json")) == ["fx-on.json", "loop-roll-1.json"]
    assert load_macros(tmp_path) == [second, first]  # sorted by name

    (tmp_path / "notes.json").write_text("{ hand-edited, broken")
    save_macros(tmp_path, [second])
    assert sorted(path.name for path in tmp_path.glob("*.json")) == ["fx-on.json", "notes.json"]
    assert load_macros(tmp_path) == [second]  # the broken file is skipped, not lost


def test_store_keeps_colliding_slugs_apart(tmp_path):
    save_macros(tmp_path, [_macro("FX on"), _macro("FX-on", shortcut="")])
    assert len(load_macros(tmp_path)) == 2
    assert macro_file_name("  ") == "macro.json"
    assert load_macros(tmp_path / "missing") == []


# --- controller triggers (issue #252) -------------------------------------------


def _event(event_type="Note On", channel="1", data1="40", data2="127", port="DDJ-XP2", direction="in"):
    return MidiEvent(direction, channel, event_type, data1, data2, 0.0, port)


def test_trigger_learned_from_a_press_only():
    assert MacroTrigger.from_event(_event()) == MacroTrigger("Note On", 1, 40, "DDJ-XP2")
    assert MacroTrigger.from_event(_event("Control Change", "3", "7", "0")) == MacroTrigger("Control Change", 3, 7, "DDJ-XP2")
    assert MacroTrigger.from_event(_event(data2="0")) is None  # velocity-0 Note On is a release
    assert MacroTrigger.from_event(_event("Note Off", data2="0")) is None
    assert MacroTrigger.from_event(_event(direction="out")) is None  # LED feedback


def test_trigger_round_trips_and_old_files_still_load():
    trigger = MacroTrigger("Note On", 1, 40, "DDJ-XP2")
    macro = MidiMacro("Fx", "DDJ-XP2", (MacroStep(PRESS),), triggers=(trigger,))
    raw = json.loads(json.dumps(macro.to_dict()))
    assert raw["trigger"] == {"event_type": "Note On", "channel": 1, "data1": 40, "port": "DDJ-XP2"}
    assert MidiMacro.from_dict(raw) == macro
    assert "trigger" not in _macro().to_dict()
    assert MidiMacro.from_dict({"name": "x", "trigger": None}).triggers == ()
    assert "trigger_gap_ms" not in raw  # a single press keeps the old file shape
    with pytest.raises(ValueError):
        MacroTrigger.from_dict({"event_type": "Note Off", "channel": 1, "data1": 40})
    with pytest.raises(ValueError):
        MacroTrigger.from_dict({"event_type": "Note On", "channel": 17, "data1": 40})


def test_trigger_matches_presses_on_its_port_only():
    trigger = MacroTrigger("Note On", 1, 40, "PIONEER DDJ-XP2")
    assert trigger.matches(_event(port="pioneer ddj-xp2"))
    assert not trigger.matches(_event(port="XDJ-XZ"))
    assert not trigger.matches(_event(data2="0"))
    assert not trigger.matches(_event(data1="41"))
    assert not trigger.matches(_event("Control Change"))
    assert MacroTrigger("Note On", 1, 40).matches(_event(port="XDJ-XZ"))  # blank port: any input


def test_macros_for_event_and_store_keep_the_binding(tmp_path):
    bound = MidiMacro("Bound", "P", (MacroStep(PRESS),), triggers=(MacroTrigger("Control Change", 2, 7, "DDJ-XP2"),))
    unbound = _macro("Unbound")
    assert macros_for_event([bound, unbound], _event("Control Change", "2", "7", "0")) == [bound]
    assert macros_for_event([bound, unbound], _event()) == []
    save_macros(tmp_path, [bound, unbound])
    assert load_macros(tmp_path) == [bound, unbound]


def test_validate_flags_shared_triggers_and_self_loops():
    trigger = MacroTrigger("Note On", 1, 40, "DDJ-XP2")
    a = MidiMacro("A", "XDJ-XZ", (MacroStep(PRESS),), triggers=(trigger,))
    b = MidiMacro("B", "XDJ-XZ", (MacroStep(PRESS),), triggers=(MacroTrigger("Note On", 1, 40),))
    other_port = MidiMacro("C", "XDJ-XZ", (MacroStep(PRESS),), triggers=(MacroTrigger("Note On", 1, 40, "XDJ-XZ"),))
    assert validate_macros([a, other_port]) == []
    assert any("same controller trigger" in problem for problem in validate_macros([a, b]))

    echo = SyncMessage("Note On", 1, 40, 127)
    looping = MidiMacro("Loop", "IAC Bus", (MacroStep(echo),), triggers=(MacroTrigger("Note On", 1, 40, "IAC Bus"),))
    assert retriggers_itself(looping)
    assert any("would loop" in problem for problem in validate_macros([looping]))
    released = MidiMacro("Rel", "IAC Bus", (MacroStep(SyncMessage("Note On", 1, 40, 0)),), triggers=looping.triggers)
    assert not retriggers_itself(released)
    assert not retriggers_itself(MidiMacro("Out", "XDJ-XZ", (MacroStep(echo),), triggers=looping.triggers))


# --- trigger sequences --------------------------------------------------------


def _at(data1, seconds, event_type="Note On", data2="127", port="DDJ-XP2"):
    return MidiEvent("in", "1", event_type, str(data1), data2, seconds, port)


def _sequence(*notes, port="DDJ-XP2"):
    return tuple(MacroTrigger("Note On", 1, note, port) for note in notes)


def test_sequence_round_trips_as_a_list_with_its_gap():
    macro = MidiMacro("Seq", "XDJ-XZ", (MacroStep(PRESS),), triggers=_sequence(40, 41, 42), trigger_gap_ms=700)
    raw = json.loads(json.dumps(macro.to_dict()))
    assert [item["data1"] for item in raw["trigger"]] == [40, 41, 42]
    assert raw["trigger_gap_ms"] == 700
    assert MidiMacro.from_dict(raw) == macro
    assert macro.trigger_label() == "Note 40, ch 1 → Note 41, ch 1 → Note 42, ch 1 on DDJ-XP2"
    mixed = (MacroTrigger("Note On", 1, 40, "A"), MacroTrigger("Control Change", 2, 7))
    assert MidiMacro("M", triggers=mixed).trigger_label() == "Note 40, ch 1 on A → CC 7, ch 2"
    with pytest.raises(ValueError):
        MidiMacro.from_dict({**raw, "trigger_gap_ms": 50})
    with pytest.raises(ValueError):
        MidiMacro.from_dict({**raw, "trigger": raw["trigger"] * 6})  # 18 presses > 16


def test_matcher_fires_a_sequence_only_once_it_is_complete():
    from djmidi.midi_macros import MacroTriggerMatcher

    seq = MidiMacro("Seq", "P", (MacroStep(PRESS),), triggers=_sequence(40, 41, 42))
    single = MidiMacro("One", "P", (MacroStep(PRESS),), triggers=_sequence(50))
    matcher = MacroTriggerMatcher()
    assert matcher.feed([seq, single], _at(40, 0.0)) == []
    assert matcher.feed([seq, single], _at(40, 0.1, data2="0")) == []  # releases don't count
    assert matcher.feed([seq, single], _at(41, 0.5)) == []
    assert matcher.feed([seq, single], _at(42, 1.2)) == [seq]
    assert matcher.feed([seq, single], _at(42, 1.3)) == []  # history cleared after firing
    assert matcher.feed([seq, single], _at(50, 1.4)) == [single]


def test_matcher_breaks_a_sequence_on_a_slow_or_wrong_press_but_ignores_cc_noise():
    from djmidi.midi_macros import MacroTriggerMatcher

    seq = MidiMacro("Seq", "P", (MacroStep(PRESS),), triggers=_sequence(40, 41), trigger_gap_ms=500)
    matcher = MacroTriggerMatcher()
    matcher.feed([seq], _at(40, 0.0))
    assert matcher.feed([seq], _at(41, 0.6)) == []  # 600 ms > 500 ms
    matcher.feed([seq], _at(40, 1.0))
    matcher.feed([seq], _at(60, 1.1))  # another note in between
    assert matcher.feed([seq], _at(41, 1.2)) == []
    matcher.feed([seq], _at(40, 2.0))
    matcher.feed([seq], _at(33, 2.1, "Control Change", "65"))  # a jog tick
    assert matcher.feed([seq], _at(41, 2.2)) == [seq]
    other_port = MacroTriggerMatcher()
    other_port.feed([seq], _at(40, 0.0))
    assert other_port.feed([seq], _at(41, 0.1, port="XDJ-XZ")) == []
    # The one-press helper never completes a sequence.
    assert macros_for_event([seq], _at(41, 0.0)) == []


def test_validate_refuses_a_sequence_inside_another():
    whole = MidiMacro("Whole", "XDJ-XZ", (MacroStep(PRESS),), triggers=_sequence(40, 41, 42))
    tail = MidiMacro("Tail", "XDJ-XZ", (MacroStep(PRESS),), triggers=_sequence(41, 42))
    first = MidiMacro("First", "XDJ-XZ", (MacroStep(PRESS),), triggers=_sequence(40))
    other = MidiMacro("Other", "XDJ-XZ", (MacroStep(PRESS),), triggers=_sequence(42, 41))
    same = MidiMacro("Same", "XDJ-XZ", (MacroStep(PRESS),), triggers=_sequence(40, 41, 42))
    assert validate_macros([whole, other]) == []
    assert "in the middle of the trigger sequence" in validate_macros([whole, tail])[0]
    assert "in the middle of the trigger sequence" in validate_macros([first, whole])[0]
    assert "same controller trigger" in validate_macros([whole, same])[0]


def test_a_sequence_loops_only_when_the_steps_replay_all_of_it():
    seq = _sequence(40, 41, port="IAC Bus")
    both = (MacroStep(SyncMessage("Note On", 1, 40, 127)), MacroStep(SyncMessage("Note On", 1, 41, 127)))
    assert retriggers_itself(MidiMacro("Loop", "IAC Bus", both, triggers=seq))
    assert not retriggers_itself(MidiMacro("Half", "IAC Bus", both[1:], triggers=seq))


def test_step_from_event_records_presses_releases_and_cc():
    from djmidi.midi_macros import MAX_DELAY_MS, step_from_event

    assert step_from_event(_at(40, 0), 12.6) == MacroStep(SyncMessage("Note On", 1, 40, 127), 13)
    assert step_from_event(_at(40, 0, data2="0")).message.event_type == "Note Off"
    assert step_from_event(_at(7, 0, "Control Change", "64")).message == SyncMessage("Control Change", 1, 7, 64)
    assert step_from_event(_at(40, 0), 10**9).delay_ms == MAX_DELAY_MS
    assert step_from_event(MidiEvent("out", "1", "Note On", "40", "127", 0.0, "P")) is None


# --- step 2: toggles, scenes, wait steps (issue #367) ------------------------


def test_toggle_scenes_and_wait_steps_round_trip():
    wait = MacroStep(SyncMessage("Note On", 1, 50, 0), 5000, wait=True)
    macro = MidiMacro(
        "Fx",
        "P",
        (MacroStep(PRESS), wait, MacroStep(RELEASE)),
        alternate_steps=(MacroStep(CC),),
        scenes=("Club", "Radio"),
    )
    raw = json.loads(json.dumps(macro.to_dict()))
    assert raw["steps"][1]["wait"] is True and "wait" not in raw["steps"][0]
    assert raw["alternate_steps"][0]["event_type"] == "Control Change"
    assert raw["scenes"] == ["Club", "Radio"]
    assert MidiMacro.from_dict(raw) == macro
    assert "alternate_steps" not in _macro().to_dict() and "scenes" not in _macro().to_dict()
    assert macro.is_toggle and macro.variant(True).steps == (MacroStep(CC),) and macro.variant(False) is macro
    assert macro.plays_in_scene("club") and not macro.plays_in_scene("Default")
    assert _macro().plays_in_scene("anything")
    assert wait.wait_trigger == MacroTrigger("Note On", 1, 50) and wait.wait_timeout_ms == 5000
    with pytest.raises(ValueError):
        MacroStep.from_dict({"event_type": "Note Off", "channel": 1, "data1": 1, "data2": 0, "wait": True})


def test_wait_rows_and_their_type_label():
    from djmidi.midi_macros import step_type

    (step,) = steps_from_rows([("Wait for Control Change", "2", "7", "", "0")])
    assert step.wait and step.message == SyncMessage("Control Change", 2, 7, 0)
    assert step_type(step) == "Wait for Control Change" and step.wait_timeout_ms == 60_000
    with pytest.raises(ValueError, match="Step 1"):
        steps_from_rows([("Wait for Note Off", "1", "1", "", "0")])


def test_same_trigger_allowed_on_macros_of_disjoint_scenes():
    trigger = (MacroTrigger("Note On", 1, 40),)
    club = MidiMacro("Club", "X", (MacroStep(PRESS),), triggers=trigger, scenes=("Club",))
    radio = MidiMacro("Radio", "X", (MacroStep(PRESS),), triggers=trigger, scenes=("Radio",))
    everywhere = MidiMacro("All", "X", (MacroStep(PRESS),), triggers=trigger)
    assert validate_macros([club, radio]) == []
    assert validate_macros([club, everywhere])  # "All" also plays in Club
    assert validate_macros([club, MidiMacro("Club2", "X", (MacroStep(PRESS),), triggers=trigger, scenes=("club",))])


def test_synchronous_play_refuses_a_wait_step():
    macro = MidiMacro("W", "P", (MacroStep(PRESS), MacroStep(SyncMessage("Note On", 1, 9, 0), wait=True)))
    result = run_macro(macro, ["P"], sender=lambda **kw: None, sleep=lambda s: None)
    assert not result.ok and result.sent == 1 and "waits for a controller press" in result.error
