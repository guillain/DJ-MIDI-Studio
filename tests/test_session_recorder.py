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
