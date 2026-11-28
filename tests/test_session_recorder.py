"""Unlimited live set recording: every event streamed to Logs/ as JSON Lines."""

from datetime import UTC, datetime

import djmidi.gui.live_monitor as live_monitor_mod
from djmidi import user_paths
from djmidi.gui.live_monitor import _MAX_ROWS, LiveMonitorView
from djmidi.midi_io import MidiEvent
from djmidi.session_recorder import SessionRecorder, read_recording


def _event(n: int, port: str = "DDJ-XP2") -> MidiEvent:
    return MidiEvent("in", "1", "Note On", str(n % 128), "127", 1000.0 + n, port)


def test_events_are_written_as_json_lines(tmp_path):
    recorder = SessionRecorder(tmp_path, now=lambda: datetime(2026, 11, 16, 18, 39, 15, tzinfo=UTC))
    path = recorder.start()
    assert path.name == "live-20261116-183915.jsonl"
    recorder.record(_event(27))
    assert recorder.stop() == path and not recorder.is_recording
    assert list(read_recording(path)) == [
        {"t": 1027.0, "port": "DDJ-XP2", "dir": "in", "ch": 1, "type": "Note On", "d1": 27, "d2": 127}
    ]


def test_a_second_recording_in_the_same_second_never_overwrites(tmp_path):
    clock = lambda: datetime(2026, 11, 16, 18, 39, 15, tzinfo=UTC)
    first = SessionRecorder(tmp_path, now=clock)
    second = SessionRecorder(tmp_path, now=clock)
    a, b = first.start(), second.start()
    first.stop(), second.stop()
    assert a != b and b.name == "live-20261116-183915~2.jsonl"


def test_events_after_stop_are_ignored_and_a_cut_line_is_skipped(tmp_path):
    recorder = SessionRecorder(tmp_path)
    path = recorder.start()
    recorder.record(_event(1))
    recorder.stop()
    recorder.record(_event(2))
    with path.open("a") as handle:
        handle.write('{"t": 1')  # a crash mid-line
    assert [row["d1"] for row in read_recording(path)] == [1]


def _monitor(monkeypatch, events):
    view = LiveMonitorView()
    monkeypatch.setattr(live_monitor_mod, "list_input_ports", lambda: ["DDJ-XP2"])
    monkeypatch.setattr(view._monitor, "open_input", lambda name: None)
    monkeypatch.setattr(view._monitor, "poll", lambda: events)
    return view


def test_recording_starts_monitoring_and_keeps_more_than_the_log(monkeypatch):
    events = [_event(n) for n in range(_MAX_ROWS + 100)]
    view = _monitor(monkeypatch, events)
    path = view.start_recording()
    assert view.is_running and view.is_recording
    assert path.parent == user_paths.subfolder(user_paths.LOGS)
    view._poll()
    assert len(view._events) == _MAX_ROWS
    assert view.stop_recording() == path
    assert sum(1 for _ in read_recording(path)) == _MAX_ROWS + 100
    assert str(_MAX_ROWS + 100) in view._recording_label.text()


def test_stopping_monitoring_or_shutdown_closes_the_recording(monkeypatch):
    view = _monitor(monkeypatch, [])
    view.start_recording()
    view._stop()
    assert not view.is_recording
    view.start_recording()
    view.shutdown()
    assert not view.is_recording


def test_no_input_means_no_recording(monkeypatch):
    view = LiveMonitorView()
    monkeypatch.setattr(live_monitor_mod, "list_input_ports", list)
    assert view.start_recording() is None and not view.is_recording


# --- record all: every MIDI message, the tracks played, what the app saw ----

import json

import mido

from djmidi.midi_io import MidiMonitor
from djmidi.session_recorder import (
    EVENTS_SUFFIX,
    MANIFEST_SUFFIX,
    TRACKS_SUFFIX,
    companion,
    read_rows,
)
from djmidi.set_analysis import load_set


class _Port:
    def __init__(self, messages):
        self.messages = messages

    def iter_pending(self):
        yield from self.messages


def test_every_other_midi_message_is_kept_as_raw_bytes(tmp_path):
    monitor = MidiMonitor()
    monitor._input_ports["XDJ-XZ (1)"] = _Port(
        [mido.Message("sysex", data=[0, 64, 5]), mido.Message("clock"), mido.Message("note_on", note=60, velocity=127)]
    )
    raw = []
    monitor.raw_sink = lambda *row: raw.append(row)
    assert [e.data1 for e in monitor.poll()] == ["60"]
    assert [(port, d, kind, data) for port, d, kind, data, _t in raw] == [
        ("XDJ-XZ (1)", "in", "sysex", [240, 0, 64, 5, 247]),
        ("XDJ-XZ (1)", "in", "clock", [248]),
    ]
    recorder = SessionRecorder(tmp_path)
    path = recorder.start()
    recorder.record_raw("XDJ-XZ (1)", "in", "sysex", [240, 0, 64, 5, 247], 12.5)
    recorder.record(_event(27))
    recorder.stop()
    rows = list(read_recording(path))
    assert rows[0] == {"t": 12.5, "port": "XDJ-XZ (1)", "dir": "in", "type": "sysex", "b": [240, 0, 64, 5, 247]}
    assert [e.number for e in load_set(path)] == [27]  # the analysis skips what it doesn't read


def test_manifest_tracks_and_app_events_share_one_clock(tmp_path):
    clock = iter([100.0, 105.0])
    recorder = SessionRecorder(tmp_path, clock=lambda: next(clock), wall=lambda: 1_800_000_000.0)
    path = recorder.start({"inputs": ["DDJ-XP2"]})
    recorder.add_track(1_800_000_030.0, "serato", "Alpha", "Artist", "/a.mp3", deck=1)
    recorder.note("deck", port="XDJ-XZ (1)", decks={"XDJ-XZ": {"left": 3}})
    recorder.stop()
    manifest = json.loads(companion(path, MANIFEST_SUFFIX).read_text())
    assert manifest["format"] == "djmidi-live-set/1" and manifest["inputs"] == ["DDJ-XP2"]
    assert manifest["wall_offset"] == 1_800_000_000.0 - 100.0
    assert (manifest["midi_events"], manifest["tracks"], manifest["app_events"]) == (0, 1, 1)
    [track] = read_rows(companion(path, TRACKS_SUFFIX))
    assert track["t"] == 130.0 and track["title"] == "Alpha" and track["deck"] == 1  # on the MIDI clock
    [event] = read_rows(companion(path, EVENTS_SUFFIX))
    assert event["kind"] == "deck" and event["t"] == 105.0


def test_live_monitor_records_history_and_deck_changes(monkeypatch):
    from djmidi.library import history

    deck = MidiEvent("in", "3", "Control Change", "102", "127", 1000.0, "XDJ-XZ (1)")
    view = _monitor(monkeypatch, [deck])
    monkeypatch.setattr(history, "default_history_dirs", dict)
    view.manifest_provider = lambda: {"mapping_file": "x.xml"}
    path = view.start_recording()
    view._poll()
    played = history.PlayedEntry("/a.mp3", datetime.now(UTC), "serato", "s", title="Alpha", deck=2)

    class _Watcher:
        def __init__(self):
            self.rows = [played]

        def poll(self):
            found, self.rows = self.rows, []
            return found

    view._history_watcher = _Watcher()
    view._poll_history()
    assert "1 track(s) played" in view._recording_label.text()
    view.note_event("macro", name="Pad 5")
    view.stop_recording()
    assert json.loads(companion(path, MANIFEST_SUFFIX).read_text())["mapping_file"] == "x.xml"
    assert [r["title"] for r in read_rows(companion(path, TRACKS_SUFFIX))] == ["Alpha"]
    assert [r["kind"] for r in read_rows(companion(path, EVENTS_SUFFIX))] == ["deck", "macro"]
    assert view._monitor.raw_sink is None
