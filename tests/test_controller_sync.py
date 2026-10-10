import json

import pytest

from djmidi.controller_sync import (
    ControllerSyncSet,
    SyncMessage,
    SyncResult,
    resolve_output_port,
    run_sync,
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
