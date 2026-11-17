"""Analysing a recorded live set: presses per control, sequences, activity."""

import json

import djmidi.gui.live_monitor as live_monitor_mod
from djmidi.gui.live_monitor import LiveMonitorView
from djmidi.gui.set_analysis_dialog import SetAnalysisDialog
from djmidi.set_analysis import BEND, CC, NOTE, SetEvent, analyse, load_set


def _write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_both_recording_formats_load_and_releases_are_dropped(tmp_path):
    app_rows = [
        {"t": 1.0, "port": "DDJ-XP2", "dir": "in", "ch": 1, "type": "Note On", "d1": 88, "d2": 127},
        {"t": 1.1, "port": "DDJ-XP2", "dir": "in", "ch": 1, "type": "Note On", "d1": 88, "d2": 0},
        {"t": 1.2, "port": "DDJ-XP2", "dir": "out", "ch": 1, "type": "Note On", "d1": 88, "d2": 127},
    ]
    script_rows = [
        {"t": 2.0, "port": "XDJ-XZ (1)", "bytes": [0x90, 1, 127]},
        {"t": 2.1, "port": "XDJ-XZ (1)", "bytes": [0xB0, 33, 65]},
        {"t": 2.2, "port": "XDJ-XZ (1)", "bytes": [0xE1, 0, 64]},
    ]
    assert [e.kind for e in load_set(_write(tmp_path / "a.jsonl", app_rows))] == [NOTE]
    events = load_set(_write(tmp_path / "b.jsonl", script_rows))
    assert [(e.kind, e.channel, e.number, e.value) for e in events] == [
        (NOTE, 1, 1, 127),
        (CC, 1, 33, 65),
        (BEND, 2, 0, 8192),
    ]


def test_presses_are_named_per_deck_and_counted():
    events = [SetEvent(float(n), "XDJ-XZ (1)", NOTE, 1, 1, 127) for n in range(3)]
    events += [SetEvent(10.0, "XDJ-XZ (1)", NOTE, 2, 1, 127), SetEvent(11.0, "XDJ-XZ (1)", NOTE, 1, 99, 127)]
    result = analyse(events)
    names = [(name, count) for _key, name, count in result.buttons]
    assert names[0] == ("DECK · CUE · ch 1", 3)
    assert ("DECK · CUE · ch 2", 1) in names
    assert result.presses == 5


def test_jogs_are_named_and_unknown_messages_keep_their_numbers():
    events = [SetEvent(0.0, "XDJ-XZ (1)", CC, 1, 33, 65), SetEvent(0.1, "XDJ-XZ (1)", CC, 9, 120, 3)]
    names = {name for _key, name, _count in analyse(events).continuous}
    assert "DISPLAY · Jog wheel · ch 1" in names and "CC 120 · ch 9" in names


def test_quick_pairs_become_sequences_and_presses_fill_activity_slices():
    cue, play = (1, 1), (1, 0)
    events = []
    for start in (0.0, 30.0, 700.0):
        events += [SetEvent(start, "XDJ-XZ (1)", NOTE, *cue, 127), SetEvent(start + 0.5, "XDJ-XZ (1)", NOTE, *play, 127)]
    events.append(SetEvent(800.0, "XDJ-XZ (1)", NOTE, *play, 127))  # too late to follow anything
    result = analyse(events)
    assert result.sequences[0] == ("DECK · CUE · ch 1 (XDJ-XZ (1))", "DECK · PLAY/PAUSE · ch 1 (XDJ-XZ (1))", 3)
    assert result.activity == [4, 3]


def test_an_empty_set_analyses_to_nothing():
    assert analyse([]).events == 0


def test_the_live_monitor_opens_the_dialog(tmp_path):
    view = LiveMonitorView()
    path = _write(tmp_path / "live.jsonl", [{"t": 1.0, "port": "DDJ-XP2", "bytes": [0x90, 88, 127]}])
    dialog = view.analyse_set(path)
    assert isinstance(dialog, SetAnalysisDialog)
    assert dialog.buttons_table.rowCount() == 1 and "live.jsonl" in dialog.summary_label.text()
    dialog.close()
    assert view.analyse_set(_write(tmp_path / "empty.jsonl", [])) is None
    assert "no MIDI event" in view._recording_label.text()
    assert live_monitor_mod.SetAnalysisDialog is SetAnalysisDialog
