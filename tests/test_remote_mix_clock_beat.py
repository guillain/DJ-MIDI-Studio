"""Tempo and beat from Traktor's MIDI Clock, through polling jitter."""

import random

import pytest

from djmidi.remote_mix.clock_beat import CLOCK, START, STOP, MidiClockBeat


def _ticks(clock, bpm, beats, start=10.0, jitter=0.004, seed=1):
    rng = random.Random(seed)
    per_tick = 60.0 / bpm / 24
    clock.feed(START, start)
    last = start
    for i in range(int(beats * 24)):
        t = start + i * per_tick
        last = t + rng.uniform(0, jitter)  # polled up to 4 ms late
        clock.feed(CLOCK, last)
    return start, per_tick, last


@pytest.mark.parametrize("bpm", [124.0, 128.0, 140.0, 174.0])
def test_tempo_and_phase_through_polling_jitter(bpm):
    clock = MidiClockBeat()
    start, per_tick, last = _ticks(clock, bpm, 8)
    snap = clock.snapshot(last)
    assert snap.tempo == pytest.approx(bpm, abs=0.3)
    assert snap.quantum == 1.0
    # Beat 0 was the Start: the beat grid lands within a few ms of it.
    true_beat = (last - start) / (per_tick * 24)
    assert abs(snap.beat - true_beat) * 60 / bpm * 1000 < 4


def test_no_beat_before_a_beat_of_ticks_and_after_the_clock_stops():
    clock = MidiClockBeat()
    clock.feed(START, 0.0)
    for i in range(10):
        clock.feed(CLOCK, i * 0.02)
    assert clock.snapshot(0.2) is None  # fewer than 24 ticks
    _start, _pt, last = _ticks(clock, 128.0, 2, start=1.0)
    assert clock.snapshot(last + 0.1) is not None
    assert clock.snapshot(last + 1.0) is None  # silent: stopped
    clock.feed(STOP, last + 0.01)
    assert not clock.running
