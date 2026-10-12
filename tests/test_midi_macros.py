import json

import pytest

from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.midi_macros import (
    MacroStep,
    MidiMacro,
    load_macros,
    macro_file_name,
    macro_from_sync_set,
    macro_schedule,
    resolve_macro_port,
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
