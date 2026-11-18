"""Remote mix phase 5: each DJ's EQ and filter."""

import numpy as np
import pytest

from djmidi.remote_mix import eq


def _sine(freq, seconds=0.5):
    t = np.arange(int(eq.RATE * seconds)) / eq.RATE
    mono = 0.5 * np.sin(2 * np.pi * freq * t)
    return np.stack([mono, mono], axis=1).astype(np.float32)


def _level_db(strip, freq):
    """Run a sine through the strip in 5 ms blocks; level of the second half vs the input."""
    x = _sine(freq)
    out = np.concatenate([strip.process(x[i : i + 240]) for i in range(0, len(x), 240)])
    half = len(x) // 2
    return 20 * np.log10(np.sqrt(np.mean(out[half:] ** 2)) / np.sqrt(np.mean(x[half:] ** 2)) + 1e-12)


def test_knobs_are_flat_at_noon_cut_to_the_left_and_boost_to_the_right():
    assert eq.knob_db(50) == 0.0
    assert eq.knob_db(100) == pytest.approx(6.0)
    assert eq.knob_db(25) == pytest.approx(-6.0, abs=0.1)
    assert eq.knob_db(0) == eq.KILL_DB
    assert eq.filter_cutoff(50) is None and eq.filter_cutoff(51) is None
    kind, low = eq.filter_cutoff(0)
    assert kind == "low" and low == pytest.approx(150.0)
    assert eq.filter_cutoff(100)[0] == "high"


def test_flat_strip_gives_back_the_original():
    strip = eq.ChannelStrip()
    x = _sine(440, 0.05)
    assert strip.flat and np.allclose(strip.process(x), x)


def test_a_cut_band_goes_and_the_others_stay():
    strip = eq.ChannelStrip()
    strip.low = 0
    assert _level_db(strip, 40) < -40
    assert abs(_level_db(eq.ChannelStrip(), 1000)) < 0.5
    strip = eq.ChannelStrip()
    strip.low = 0
    assert abs(_level_db(strip, 1500)) < 1.0
    strip = eq.ChannelStrip()
    strip.high = 100
    assert _level_db(strip, 12000) == pytest.approx(6.0, abs=0.7)
    assert eq.response_db(strip, 100) == pytest.approx(0.0, abs=0.2)


def test_the_filter_sweeps_low_pass_left_and_high_pass_right():
    strip = eq.ChannelStrip()
    strip.filter = 0
    assert _level_db(strip, 5000) < -40
    strip = eq.ChannelStrip()
    strip.filter = 100
    assert _level_db(strip, 60) < -40
    assert eq.response_db(strip, 15000) == pytest.approx(0.0, abs=1.0)


def test_self_check_passes():
    assert eq.self_check() is None
