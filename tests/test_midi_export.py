"""Live Monitor log -> Standard MIDI File (phase 5 item 4)."""

import mido

from djmidi.midi_export import TICKS_PER_BEAT, events_to_midi_file, write_midi_file
from djmidi.midi_io import MidiEvent

EVENTS = [
    MidiEvent("in", "1", "Note On", "11", "127", 10.0, "DDJ-XP2"),
    MidiEvent("in", "1", "Note Off", "11", "0", 10.25, "DDJ-XP2"),
    MidiEvent("out", "1", "Note On", "11", "127", 10.1, "DDJ-XP2"),
    MidiEvent("in", "2", "Control Change", "19", "64", 11.0, "XDJ-XZ"),
    MidiEvent("in", "17", "Note On", "11", "127", 11.5, "XDJ-XZ"),  # not a MIDI channel: skipped
]


def _seconds(track, ticks_per_beat=TICKS_PER_BEAT):
    total, times = 0, []
    for message in track:
        total += message.time
        if not message.is_meta:
            times.append((round(mido.tick2second(total, ticks_per_beat, mido.bpm2tempo(120)), 3), message))
    return times


def test_one_track_per_port_and_direction_with_real_timing():
    midi = events_to_midi_file(EVENTS)
    assert midi.type == 1 and midi.tracks[0][0].type == "set_tempo"
    names = [track[0].name for track in midi.tracks[1:]]
    assert names == ["DDJ-XP2", "DDJ-XP2 (out)", "XDJ-XZ"]
    xp2 = _seconds(midi.tracks[1])
    assert [(time, message.type, message.note) for time, message in xp2] == [(0.0, "note_on", 11), (0.25, "note_off", 11)]
    assert _seconds(midi.tracks[2])[0][0] == 0.1
    (time, cc), = _seconds(midi.tracks[3])
    assert time == 1.0 and (cc.type, cc.channel, cc.control, cc.value) == ("control_change", 1, 19, 64)


def test_the_file_reads_back(tmp_path):
    path = tmp_path / "session.mid"
    assert write_midi_file(EVENTS, path) == 4
    reread = mido.MidiFile(str(path))
    assert sum(1 for message in reread if not message.is_meta) == 4
    assert round(reread.length, 3) == 1.0
    assert write_midi_file([], tmp_path / "empty.mid") == 0


def test_live_monitor_saves_a_midi_file(tmp_path, monkeypatch):
    import djmidi.gui.live_monitor as live_monitor_mod
    from djmidi.gui.live_monitor import LiveMonitorView

    view = LiveMonitorView()
    view._events = list(EVENTS)
    path = tmp_path / "monitor"
    monkeypatch.setattr(
        live_monitor_mod.QFileDialog, "getSaveFileName", lambda *args: (str(path), "MIDI files (*.mid)")
    )
    view._save_log()
    assert (tmp_path / "monitor.mid").exists() and "Saved 4 MIDI event(s)" in view._status_label.text()
    assert view.save_log(tmp_path / "again.midi") and mido.MidiFile(str(tmp_path / "again.midi")).type == 1
