import numpy as np
import pytest

from djmidi.remote_mix.beat_clock import ListeningClock, estimate_tempo, onset_envelope

SR = 48_000


def club_loop(bpm, seconds, *, first_kick=0.137, hats=True, noise=0.02, seed=1):
    """Four-on-the-floor kick, off-beat hats, a bass line and noise."""
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    out = noise * rng.standard_normal(n)
    beat = 60.0 / bpm
    t = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * (50 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
    hat = rng.standard_normal(int(0.04 * SR)) * np.exp(-np.arange(int(0.04 * SR)) / SR * 90) * 0.3
    kicks = np.arange(first_kick, seconds, beat)
    for k in kicks:
        i = int(k * SR)
        seg = kick[: n - i]
        out[i : i + len(seg)] += seg
        if hats:
            j = int((k + beat / 2) * SR)
            if j < n:
                seg = hat[: n - j]
                out[j : j + len(seg)] += seg
    # Off-beat bass (house), quieter than the kick, with a soft attack.
    bass_t = np.arange(n) / SR
    gate = np.clip(np.sin(2 * np.pi * (bass_t - first_kick - beat / 2) / beat) * 8, 0, 1)
    out += 0.25 * np.sin(2 * np.pi * 55 * bass_t) * gate
    return (out / np.abs(out).max() * 20000).astype(np.int16), kicks


@pytest.mark.parametrize("bpm", [96.0, 122.0, 128.0, 140.0, 174.0])
def test_tempo_from_the_sound(bpm):
    pcm, _ = club_loop(bpm, 8.0)
    reading = estimate_tempo(onset_envelope(pcm / 32768.0, SR))
    assert reading is not None
    assert reading.tempo == pytest.approx(bpm, abs=0.6)


def feed_live(clock_time, pcm, *, chunk=240):
    clock = ListeningClock(SR, clock=lambda: clock_time[0])
    for start in range(0, len(pcm), chunk):
        part = pcm[start : start + chunk]
        clock_time[0] = (start + len(part)) / SR
        clock.feed(part)
    return clock


@pytest.mark.parametrize(("bpm", "first_kick"), [(126.0, 0.137), (122.0, 0.4), (132.5, 0.02), (174.0, 0.21)])
def test_the_beat_lands_on_the_kicks(bpm, first_kick):
    pcm, kicks = club_loop(bpm, 12.0, first_kick=first_kick)
    now = [0.0]
    clock = feed_live(now, pcm)
    assert clock.locked
    snap = clock.snapshot()
    assert snap.tempo == pytest.approx(bpm, abs=0.5)
    period = 60.0 / snap.tempo
    for kick in kicks[-6:]:
        beat = snap.beat + (kick - snap.at) / period
        error_ms = (beat - round(beat)) * period * 1000
        assert abs(error_ms) < 12, error_ms


def test_beat_numbers_keep_counting_across_estimates():
    pcm, _ = club_loop(124.0, 14.0)
    now = [0.0]
    clock = ListeningClock(SR, clock=lambda: now[0])
    beats = []
    for start in range(0, len(pcm), 240):
        now[0] = (start + 240) / SR
        clock.feed(pcm[start : start + 240])
        snap = clock.snapshot()
        if snap is not None:
            beats.append((now[0], snap.beat))
    assert beats
    values = [b for _, b in beats]
    jumps = np.diff(values)
    assert jumps.min() > -0.05  # never runs backwards
    assert jumps.max() < 0.1  # no jump of a beat


def test_silence_or_noise_is_not_a_beat():
    now = [0.0]
    rng = np.random.default_rng(3)
    noise = (rng.standard_normal(SR * 6) * 3000).astype(np.int16)
    assert not feed_live(now, noise).locked
    assert not feed_live([0.0], np.zeros(SR * 6, dtype=np.int16)).locked


def test_stereo_is_mixed_down():
    pcm, _ = club_loop(128.0, 8.0)
    stereo = np.stack([pcm, pcm], axis=1)
    now = [0.0]
    clock = ListeningClock(SR, clock=lambda: now[0])
    for start in range(0, len(stereo), 240):
        now[0] = (start + 240) / SR
        clock.feed(stereo[start : start + 240])
    assert clock.snapshot().tempo == pytest.approx(128.0, abs=0.5)
