"""Live Monitor log -> Standard MIDI File (Qt-free).

The Live Monitor already saves its log as CSV; a ``.mid`` file opens in any
DAW or MIDI tool, with the real timing kept, so a captured session can be
replayed, compared or attached to a bug report. :func:`events_to_midi_file`
writes a type 1 file: one track per (port, direction), named after the port
(`` (out)`` for software -> controller feedback), the first event at time 0
and every other one at its offset from it.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import mido

from djmidi.midi_io import MidiEvent

TICKS_PER_BEAT = 480
TEMPO = mido.bpm2tempo(120)  # 1 beat = 0.5 s, so 1 tick ~ 1 ms
_TYPES = {"Note On": "note_on", "Note Off": "note_off", "Control Change": "control_change"}


def _message(event: MidiEvent) -> mido.Message | None:
    kind = _TYPES.get(event.event_type)
    if kind is None:
        return None
    try:
        channel, data1, data2 = int(event.channel) - 1, int(event.data1), int(event.data2)
    except ValueError:
        return None
    if not (0 <= channel <= 15 and 0 <= data1 <= 127 and 0 <= data2 <= 127):
        return None
    if kind == "control_change":
        return mido.Message(kind, channel=channel, control=data1, value=data2)
    return mido.Message(kind, channel=channel, note=data1, velocity=data2)


def events_to_midi_file(events: Iterable[MidiEvent]) -> mido.MidiFile:
    """The type 1 MIDI file for `events` (any order; sorted by time)."""
    ordered = sorted(events, key=lambda event: event.timestamp)
    midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=TEMPO, time=0))
    midi.tracks.append(tempo_track)
    if not ordered:
        return midi
    start = ordered[0].timestamp
    tracks: dict[tuple[str, str], tuple[mido.MidiTrack, list[int]]] = {}
    for event in ordered:
        message = _message(event)
        if message is None:
            continue
        key = (event.port, event.direction)
        if key not in tracks:
            track = mido.MidiTrack()
            name = event.port or "MIDI"
            track.append(mido.MetaMessage("track_name", name=name if event.direction == "in" else f"{name} (out)"))
            midi.tracks.append(track)
            tracks[key] = (track, [0])
        track, last = tracks[key]
        tick = round(mido.second2tick(event.timestamp - start, TICKS_PER_BEAT, TEMPO))
        track.append(message.copy(time=max(tick - last[0], 0)))
        last[0] = max(tick, last[0])
    return midi


def write_midi_file(events: Iterable[MidiEvent], path: str | Path) -> int:
    """Saves `events` as a ``.mid`` file; returns how many messages went in."""
    midi = events_to_midi_file(events)
    midi.save(str(path))
    return sum(1 for track in midi.tracks[1:] for message in track if not message.is_meta)


__all__ = ["TICKS_PER_BEAT", "events_to_midi_file", "write_midi_file"]
