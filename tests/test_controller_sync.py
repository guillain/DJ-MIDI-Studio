import json

import pytest

from djmidi.controller_sync import (
    DEFAULT_SCENE,
    ControllerSyncSet,
    PlugInSyncTracker,
    SyncMessage,
    SyncResult,
    resolve_output_port,
    run_sync,
    scene_names,
    sets_for_scene,
    summarize_results,
    sync_set_from_events,
)
from djmidi.midi_io import MidiEvent
from djmidi.plugins import PluginPreferences


def _event(event_type="Note On", channel="1", data1="11", data2="127", direction="in", port="PIONEER DDJ-XP2"):
    return MidiEvent(direction, channel, event_type, data1, data2, 0.0, port)


class _Recorder:
    def __init__(self, fail_on: str | None = None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, **kwargs):
        if kwargs["output_port_name"] == self.fail_on:
            raise OSError("port vanished")
        self.calls.append(kwargs)


def test_sync_message_normalizes_and_validates():
    assert SyncMessage.create("note_on", "2", "60", "127") == SyncMessage("Note On", 2, 60, 127)
    assert SyncMessage.create("cc", 1, 7, 0).event_type == "Control Change"
    with pytest.raises(ValueError):
        SyncMessage.create("pitchwheel", 1, 0, 0)
    with pytest.raises(ValueError):
        SyncMessage.create("Note On", 17, 0, 0)
    with pytest.raises(ValueError):
        SyncMessage.create("Note On", 1, 128, 0)


def test_sync_set_from_events_keeps_input_note_cc_in_order_and_defaults_port():
    events = [
        _event(data1="11"),
        _event(direction="out", data1="99"),
        _event(event_type="Control Change", data1="7", data2="64"),
        _event(channel="not-a-number"),
        _event(event_type="Note Off", data1="11", data2="0"),
    ]
    sync_set = sync_set_from_events(" DDJ-XP2 ", events)
    assert sync_set.controller == "DDJ-XP2"
    assert sync_set.output_port == "PIONEER DDJ-XP2"
    assert [(m.event_type, m.data1) for m in sync_set.messages] == [
        ("Note On", 11),
        ("Control Change", 7),
        ("Note Off", 11),
    ]


def test_sync_set_from_events_requires_a_name():
    with pytest.raises(ValueError):
        sync_set_from_events("  ", [_event()])


def test_sync_set_dict_roundtrip():
    sync_set = ControllerSyncSet("XDJ-XZ", "XDJ-XZ", (SyncMessage("Note On", 1, 0, 127),))
    assert ControllerSyncSet.from_dict(json.loads(json.dumps(sync_set.to_dict()))) == sync_set


@pytest.mark.parametrize(
    ("output_port", "controller", "ports", "expected"),
    [
        ("PIONEER DDJ-XP2", "DDJ-XP2", ["XDJ-XZ", "PIONEER DDJ-XP2"], "PIONEER DDJ-XP2"),
        # Recorded port renamed with a numeric suffix (Windows-style).
        ("PIONEER DDJ-XP2", "DDJ-XP2", ["PIONEER DDJ-XP2 1"], "PIONEER DDJ-XP2 1"),
        # No recorded port: match the controller name.
        ("", "DDJ-XP2", ["IAC Driver Bus 1", "PIONEER DDJ-XP2"], "PIONEER DDJ-XP2"),
        ("", "XDJ-XZ", ["PIONEER DDJ-XP2"], None),
        ("", "DDJ-XP2", [], None),
    ],
)
def test_resolve_output_port(output_port, controller, ports, expected):
    assert resolve_output_port(ControllerSyncSet(controller, output_port), ports) == expected


def test_run_sync_sends_each_set_and_skips_disconnected_ones():
    sets = [
        ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127), SyncMessage("Note Off", 1, 11, 0))),
        ControllerSyncSet("XDJ-XZ", "", (SyncMessage("Note On", 1, 0, 127),)),
    ]
    sender = _Recorder()
    results = run_sync(sets, ["PIONEER DDJ-XP2"], sender=sender)
    assert results == [
        SyncResult("DDJ-XP2", "PIONEER DDJ-XP2", 2),
        SyncResult("XDJ-XZ", None, error="not connected"),
    ]
    assert [(c["event_type"], c["data1"], c["data2"]) for c in sender.calls] == [
        ("Note On", 11, 127),
        ("Note Off", 11, 0),
    ]
    assert summarize_results(results) == "Synced 1/2 controller(s): DDJ-XP2 (2 msg), XDJ-XZ (not connected)"


def test_run_sync_failing_port_does_not_stop_other_controllers():
    sets = [
        ControllerSyncSet("DDJ-XP2", "A", (SyncMessage("Note On", 1, 11, 127),)),
        ControllerSyncSet("XDJ-XZ", "B", (SyncMessage("Note On", 1, 0, 127),)),
    ]
    sender = _Recorder(fail_on="A")
    results = run_sync(sets, ["A", "B"], sender=sender)
    assert not results[0].ok and "port vanished" in results[0].error
    assert results[1].ok and results[1].sent == 1


class _FakeOutput:
    """Stands in for a ``mido`` output port, counting opens and closes."""

    def __init__(self, name, log, fail_on=None):
        self.name = name
        self.log = log
        self.fail_on = fail_on

    def __enter__(self):
        if self.name == self.fail_on:
            raise OSError("port vanished")
        self.log.append(("open", self.name))
        return self

    def __exit__(self, *exc):
        self.log.append(("close", self.name))
        return False

    def send(self, message):
        self.log.append(("send", self.name, message.type))


def test_run_sync_opens_each_port_once_per_set(monkeypatch):
    """Issue #297: a set's messages share one open port, not one open each."""
    log = []
    monkeypatch.setattr("djmidi.midi_io.mido.open_output", lambda name: _FakeOutput(name, log))
    messages = tuple(SyncMessage("Note On", 1, n, 127) for n in range(5))
    sets = [ControllerSyncSet("DDJ-XP2", "A", messages), ControllerSyncSet("XDJ-XZ", "B", messages[:2])]
    results = run_sync(sets, ["A", "B"])
    assert [r.sent for r in results] == [5, 2] and all(r.ok for r in results)
    assert [entry for entry in log if entry[0] != "send"] == [
        ("open", "A"),
        ("close", "A"),
        ("open", "B"),
        ("close", "B"),
    ]
    assert log.count(("send", "A", "note_on")) == 5
    assert log.count(("send", "B", "note_on")) == 2


def test_run_sync_port_that_fails_to_open_does_not_stop_other_sets(monkeypatch):
    log = []
    monkeypatch.setattr("djmidi.midi_io.mido.open_output", lambda name: _FakeOutput(name, log, fail_on="A"))
    sets = [
        ControllerSyncSet("DDJ-XP2", "A", (SyncMessage("Note On", 1, 11, 127),)),
        ControllerSyncSet("XDJ-XZ", "B", (SyncMessage("Note On", 1, 0, 127),)),
    ]
    results = run_sync(sets, ["A", "B"])
    assert not results[0].ok and results[0].sent == 0 and "port vanished" in results[0].error
    assert results[1].ok and results[1].sent == 1
    assert log == [("open", "B"), ("send", "B", "note_on"), ("close", "B")]


def test_run_sync_injected_port_opener_is_entered_once_per_set():
    opened = []
    sent = []

    class _Opener:
        def __init__(self, port):
            opened.append(port)
            self.port = port

        def __enter__(self):
            return lambda **kw: sent.append((self.port, kw["data1"]))

        def __exit__(self, *exc):
            return False

    messages = (SyncMessage("Note On", 1, 1, 127), SyncMessage("Note On", 1, 2, 127))
    results = run_sync([ControllerSyncSet("DDJ-XP2", "A", messages)], ["A"], port_opener=_Opener)
    assert opened == ["A"]
    assert sent == [("A", 1), ("A", 2)]
    assert results[0].ok and results[0].sent == 2


def test_summarize_with_no_sets():
    assert summarize_results([]) == "No controller sync set recorded"


def test_preferences_store_one_sync_set_per_controller_and_roundtrip():
    preferences = PluginPreferences()
    first = ControllerSyncSet("DDJ-XP2", "", (SyncMessage("Note On", 1, 11, 127),))
    other = ControllerSyncSet("XDJ-XZ", "XDJ-XZ", ())
    replacement = ControllerSyncSet("DDJ-XP2", "PIONEER DDJ-XP2", (SyncMessage("Control Change", 2, 7, 0),))
    preferences.set_sync_set(first)
    preferences.set_sync_set(other)
    preferences.set_sync_set(replacement)
    assert preferences.controller_sync_sets == [replacement, other]
    assert preferences.sync_set_for("DDJ-XP2") == replacement

    restored = PluginPreferences.from_json(preferences.to_json())
    assert restored.controller_sync_sets == [replacement, other]

    restored.remove_sync_set("DDJ-XP2")
    assert restored.sync_set_for("DDJ-XP2") is None


def test_preferences_without_sync_sets_still_load():
    assert PluginPreferences.from_json('{"enabled": {}}').controller_sync_sets == []


def test_preferences_reject_malformed_sync_sets():
    with pytest.raises(TypeError):
        PluginPreferences.from_json('{"enabled": {}, "controller_sync_sets": {}}')
    with pytest.raises(ValueError):
        PluginPreferences.from_json(
            '{"enabled": {}, "controller_sync_sets": [{"controller": "X", "messages": '
            '[{"event_type": "Note On", "channel": 99, "data1": 0, "data2": 0}]}]}'
        )


def test_sync_sets_from_recording_splits_by_port():
    from djmidi.controller_sync import sync_sets_from_recording
    from djmidi.midi_io import MidiEvent

    events = [
        MidiEvent("in", "1", "Note On", "11", "127", 0.0, "PIONEER DDJ-XP2"),
        MidiEvent("out", "1", "Note On", "99", "127", 0.0, "DJMidiStudio Monitor"),
        MidiEvent("in", "2", "Control Change", "7", "64", 0.0, "Other"),
        MidiEvent("in", "1", "Note Off", "11", "0", 0.0, "PIONEER DDJ-XP2"),
        MidiEvent("in", "1", "Pitch", "0", "0", 0.0, "Junk"),
    ]
    names = {"PIONEER DDJ-XP2": "DDJ-XP2"}
    sets = sync_sets_from_recording(events, names.get)
    assert [(s.controller, s.output_port, len(s.messages)) for s in sets] == [
        ("DDJ-XP2", "PIONEER DDJ-XP2", 2),
        ("Other", "Other", 1),
    ]


_XP2 = ControllerSyncSet("DDJ-XP2", "PIONEER DDJ-XP2", ())
_XZ = ControllerSyncSet("XDJ-XZ", "", ())


def test_plug_in_tracker_first_call_only_seeds():
    tracker = PlugInSyncTracker()
    assert not tracker.seeded
    assert tracker.due([_XP2], ["PIONEER DDJ-XP2"]) == []
    assert tracker.seeded


def test_plug_in_tracker_sends_on_appearance_once_and_again_after_replug():
    tracker = PlugInSyncTracker()
    tracker.seed(["IAC Driver Bus 1"])
    assert tracker.due([_XP2, _XZ], ["IAC Driver Bus 1", "PIONEER DDJ-XP2"]) == [_XP2]
    # Staying connected never re-sends.
    assert tracker.due([_XP2, _XZ], ["IAC Driver Bus 1", "PIONEER DDJ-XP2"]) == []
    # Unplugged, then replugged: due again.
    assert tracker.due([_XP2, _XZ], ["IAC Driver Bus 1"]) == []
    assert tracker.due([_XP2, _XZ], ["IAC Driver Bus 1", "PIONEER DDJ-XP2"]) == [_XP2]


def test_plug_in_tracker_seed_prevents_double_sync_at_launch():
    tracker = PlugInSyncTracker()
    tracker.seed(["PIONEER DDJ-XP2", "XDJ-XZ"])  # the ports the launch Sync used
    assert tracker.due([_XP2, _XZ], ["PIONEER DDJ-XP2", "XDJ-XZ"]) == []


def test_plug_in_tracker_ignores_unrelated_ports_and_new_sets_for_connected_controllers():
    tracker = PlugInSyncTracker()
    tracker.seed(["PIONEER DDJ-XP2"])
    assert tracker.due([_XP2], ["PIONEER DDJ-XP2", "Some Synth"]) == []
    # A set recorded while XDJ-XZ is already connected isn't sent back to it.
    tracker.seed(["PIONEER DDJ-XP2", "XDJ-XZ"])
    assert tracker.due([_XP2, _XZ], ["PIONEER DDJ-XP2", "XDJ-XZ"]) == []


def test_plug_in_tracker_several_controllers_appearing_together():
    tracker = PlugInSyncTracker()
    tracker.seed([])
    assert tracker.due([_XP2, _XZ], ["XDJ-XZ", "PIONEER DDJ-XP2"]) == [_XP2, _XZ]


def test_plug_in_tracker_reset_reseeds_without_sending():
    tracker = PlugInSyncTracker()
    tracker.seed([])
    tracker.reset()
    assert tracker.due([_XP2], ["PIONEER DDJ-XP2"]) == []


def test_with_messages_replaces_only_the_messages():
    original = ControllerSyncSet("DDJ-XP2", "PIONEER DDJ-XP2", (SyncMessage("Note On", 1, 11, 127),))
    edited = original.with_messages([SyncMessage("Control Change", 2, 7, 0)])
    assert edited == ControllerSyncSet("DDJ-XP2", "PIONEER DDJ-XP2", (SyncMessage("Control Change", 2, 7, 0),))
    assert original.messages == (SyncMessage("Note On", 1, 11, 127),)


def test_move_message_clamps_and_ignores_bad_index():
    from djmidi.controller_sync import move_message

    a, b, c = (SyncMessage("Note On", 1, n, 127) for n in (1, 2, 3))
    assert move_message((a, b, c), 2, -1) == (a, c, b)
    assert move_message((a, b, c), 0, 1) == (b, a, c)
    assert move_message((a, b, c), 0, -1) == (a, b, c)
    assert move_message((a, b, c), 2, 5) == (a, b, c)
    assert move_message((a, b, c), 7, 1) == (a, b, c)


def test_messages_from_rows_validates_and_names_the_bad_row():
    from djmidi.controller_sync import messages_from_rows

    assert messages_from_rows([("Note On", "1", "11", "127"), ("cc", 2, 7, 0)]) == (
        SyncMessage("Note On", 1, 11, 127),
        SyncMessage("Control Change", 2, 7, 0),
    )
    assert messages_from_rows([]) == ()
    with pytest.raises(ValueError, match="Message 2: data1"):
        messages_from_rows([("Note On", 1, 11, 127), ("Note On", 1, 128, 0)])
    with pytest.raises(ValueError, match="Message 1"):
        messages_from_rows([("Note On", 1, 11)])


# --- Scenes (issue #188) ----------------------------------------------------


def _scene_set(controller: str, scene: str = "Default", note: int = 1) -> ControllerSyncSet:
    return ControllerSyncSet(controller, "", (SyncMessage.create("Note On", 1, note, 127),), scene)


def test_a_set_saved_before_scenes_loads_as_the_default_scene():
    old = {
        "controller": "DDJ-XP2",
        "output_port": "",
        "messages": [{"event_type": "Note On", "channel": 1, "data1": 11, "data2": 127}],
    }
    sync_set = ControllerSyncSet.from_dict(old)
    assert sync_set.scene == DEFAULT_SCENE
    assert sync_set.label == "DDJ-XP2"
    assert ControllerSyncSet.from_dict({**old, "scene": "  "}).scene == DEFAULT_SCENE
    assert ControllerSyncSet.from_dict(_scene_set("DDJ-XP2", "Tek").to_dict()).scene == "Tek"


def test_with_messages_and_in_scene_keep_the_other_fields():
    tek = _scene_set("DDJ-XP2", "Tek")
    assert tek.with_messages(()).scene == "Tek"
    moved = tek.in_scene(" DnB ")
    assert (moved.scene, moved.messages, moved.label) == ("DnB", tek.messages, "DDJ-XP2 — DnB")


def test_sets_for_scene_falls_back_to_each_controllers_default_set():
    xp2_default, xp2_tek = _scene_set("DDJ-XP2"), _scene_set("DDJ-XP2", "Tek", 2)
    xz_default = _scene_set("XDJ-XZ")
    lc1_dnb = _scene_set("CMD LC-1", "DnB")
    sets = [xp2_tek, xz_default, xp2_default, lc1_dnb]
    assert sets_for_scene(sets, "Tek") == [xp2_tek, xz_default]
    assert sets_for_scene(sets, "Default") == [xp2_default, xz_default]
    # No set for that scene and no Default set: the controller is left out.
    assert sets_for_scene(sets, "Warm-up") == [xp2_default, xz_default]
    assert sets_for_scene(sets, "DnB") == [xp2_default, xz_default, lc1_dnb]


def test_scene_names_lists_default_first_then_alphabetically():
    sets = [_scene_set("A", "tek"), _scene_set("B", "DnB"), _scene_set("C")]
    assert scene_names(sets) == ["Default", "DnB", "tek"]
    assert scene_names([], "Warm-up") == ["Default", "Warm-up"]


def test_preferences_key_sets_by_controller_and_scene():
    preferences = PluginPreferences()
    default, tek = _scene_set("DDJ-XP2"), _scene_set("DDJ-XP2", "Tek")
    preferences.set_sync_set(default)
    preferences.set_sync_set(tek)
    replacement = _scene_set("DDJ-XP2", "Tek", 9)
    preferences.set_sync_set(replacement)
    assert preferences.controller_sync_sets == [default, replacement]
    assert preferences.sync_set_for("DDJ-XP2") == default
    assert preferences.sync_set_for("DDJ-XP2", "Tek") == replacement
    assert preferences.sync_set_for("DDJ-XP2", "DnB") is None

    preferences.active_sync_scene = "Tek"
    assert preferences.active_sync_sets() == [replacement]
    preferences.active_sync_scene = "DnB"
    assert preferences.active_sync_sets() == [default]

    restored = PluginPreferences.from_json(preferences.to_json())
    assert restored.active_sync_scene == "DnB"
    assert restored.controller_sync_sets == [default, replacement]

    restored.remove_sync_set("DDJ-XP2", "Tek")
    assert restored.controller_sync_sets == [default]
    restored.set_sync_set(tek)
    restored.remove_sync_set("DDJ-XP2")  # no scene: every scene of that controller
    assert restored.controller_sync_sets == []


def test_old_preferences_json_loads_into_the_default_scene():
    old = {
        "enabled": {},
        "controller_sync_sets": [
            {"controller": "DDJ-XP2", "output_port": "", "messages": []},
            {"controller": "DDJ-XP2", "output_port": "Later", "messages": []},
        ],
    }
    preferences = PluginPreferences.from_json(json.dumps(old))
    assert preferences.active_sync_scene == DEFAULT_SCENE
    # One per (controller, scene): the last one wins.
    assert [(s.key, s.output_port) for s in preferences.controller_sync_sets] == [(("DDJ-XP2", "Default"), "Later")]


def test_sync_sets_from_recording_keeps_one_set_per_port_when_ports_name_the_same_controller():
    from djmidi.controller_sync import sync_sets_from_recording
    from djmidi.midi_io import MidiEvent

    events = [
        MidiEvent("in", "1", "Pitch", "0", "0", 0.0, "Silent"),  # no note/CC: takes no name
        MidiEvent("in", "1", "Note On", "11", "127", 0.0, "DDJ-XP2 0"),
        MidiEvent("in", "1", "Note On", "12", "127", 0.0, "DDJ-XP2 1"),
        MidiEvent("in", "1", "Note On", "13", "127", 0.0, "DDJ-XP2"),
    ]
    # Sets are stored one per controller name: a second unit keeps its own
    # recording under its port's name instead of overwriting the first.
    sets = sync_sets_from_recording(events, lambda port: "DDJ-XP2")
    assert [(s.controller, s.output_port, [m.data1 for m in s.messages]) for s in sets] == [
        ("DDJ-XP2", "DDJ-XP2 0", [11]),
        ("DDJ-XP2 1", "DDJ-XP2 1", [12]),
        ("DDJ-XP2 (2)", "DDJ-XP2", [13]),
    ]


def test_collapse_control_changes_keeps_last_value_at_last_position():
    from djmidi.controller_sync import collapse_control_changes

    messages = (
        SyncMessage("Control Change", 1, 7, 10),
        SyncMessage("Note On", 1, 11, 127),
        SyncMessage("Control Change", 1, 7, 20),
        SyncMessage("Control Change", 2, 7, 5),  # another channel: its own CC
        SyncMessage("Note On", 1, 12, 127),
        SyncMessage("Control Change", 1, 7, 30),
        SyncMessage("Note Off", 1, 11, 0),
    )
    kept, dropped = collapse_control_changes(messages)
    assert kept == (
        SyncMessage("Note On", 1, 11, 127),
        SyncMessage("Control Change", 2, 7, 5),
        SyncMessage("Note On", 1, 12, 127),
        SyncMessage("Control Change", 1, 7, 30),
        SyncMessage("Note Off", 1, 11, 0),
    )
    assert dropped == 2


def test_collapse_control_changes_keeps_repeated_notes():
    from djmidi.controller_sync import collapse_control_changes

    messages = (SyncMessage("Note On", 1, 11, 127),) * 3
    assert collapse_control_changes(messages) == (messages, 0)


def test_sync_sets_from_recording_collapses_a_moved_fader():
    from djmidi.controller_sync import recorded_sync_sets, sync_sets_from_recording

    events = [_event("Note On", data1="11")]
    events += [_event("Control Change", data1="19", data2=str(value)) for value in range(128)]
    events.append(_event("Note On", data1="12"))
    sets = sync_sets_from_recording(events, lambda port: "DDJ-XP2")
    assert [(m.event_type, m.data1, m.data2) for m in sets[0].messages] == [
        ("Note On", 11, 127),
        ("Control Change", 19, 127),
        ("Note On", 12, 127),
    ]
    _sets, collapsed = recorded_sync_sets(events, lambda port: "DDJ-XP2")
    assert collapsed == {"PIONEER DDJ-XP2": 127}


def test_sync_set_from_events_does_not_collapse_control_changes():
    # Controller Setup shows every recorded row for review before saving.
    events = [_event("Control Change", data1="19", data2=str(value)) for value in range(3)]
    assert len(sync_set_from_events("DDJ-XP2", events).messages) == 3


def test_plug_in_tracker_ignores_a_windows_port_renumbering():
    # Issue #305: Windows numbers ports ("DDJ-XP2 1") and renumbers them when
    # another device comes or goes; the controller never left.
    tracker = PlugInSyncTracker()
    tracker.seed(["Some Synth 0", "PIONEER DDJ-XP2 1"])
    assert tracker.due([_XP2], ["PIONEER DDJ-XP2 0"]) == []
    assert tracker.due([_XP2], ["Some Synth 0", "PIONEER DDJ-XP2 1"]) == []
    # A real unplug / replug under a new number is still a plug-in.
    assert tracker.due([_XP2], ["Some Synth 0"]) == []
    assert tracker.due([_XP2], ["Some Synth 0", "PIONEER DDJ-XP2 2"]) == [_XP2]


def test_plug_in_tracker_second_identical_controller_is_a_plug_in():
    tracker = PlugInSyncTracker()
    tracker.seed(["IAC Driver Bus 1"])
    iac = ControllerSyncSet("IAC", "IAC Driver Bus 2", ())
    assert tracker.due([iac], ["IAC Driver Bus 1", "IAC Driver Bus 2"]) == [iac]


def test_port_identity_strips_only_the_trailing_index():
    from djmidi.controller_sync import port_identity

    assert port_identity("PIONEER DDJ-XP2 1") == "PIONEER DDJ-XP2"
    assert port_identity("DDJ-XP2") == "DDJ-XP2"
    assert port_identity("CMD LC-1") == "CMD LC-1"
