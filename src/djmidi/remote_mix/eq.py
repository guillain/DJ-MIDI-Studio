"""A DJ mixer channel's EQ and filter for Mix Together (remote mix, phase 5), Qt-free.

Each DJ gets the knobs of a club mixer channel: **Low**, **Mid** and **High**
(an isolator: below 250 Hz, between, above 4 kHz; from a full cut on the
left to +6 dB on the right, flat at noon) and one **Filter** knob (low-pass
to the left, high-pass to the right, off at noon).

Knob positions are 0..100 with 50 at noon, the way a controller knob sends 0..127
with 64 at its centre detent. The bands come from Linkwitz-Riley crossovers
and the Filter is a resonant biquad (Robert Bristow-Johnson's cookbook), all
run by SciPy with a state that carries over from block to block, so turning
a knob never restarts the sound.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import butter, sosfilt

RATE = 48_000
CENTRE = 50
LOW_HZ = 250.0
HIGH_HZ = 4_000.0
MAX_BOOST_DB = 6.0
KILL_DB = -80.0
FILTER_DEAD_ZONE = 2  # knob steps around noon where the filter is off
LOW_PASS_RANGE = (20_000.0, 150.0)  # cut-off from just left of noon to full left
HIGH_PASS_RANGE = (20.0, 6_000.0)  # cut-off from just right of noon to full right
FILTER_Q = 0.9


def knob_db(position: float) -> float:
    """An EQ knob's gain: a full cut at 0, flat at noon (50), +6 dB at 100."""
    position = min(100.0, max(0.0, position))
    if position >= CENTRE:
        return MAX_BOOST_DB * (position - CENTRE) / (100 - CENTRE)
    if position <= 0:
        return KILL_DB
    return max(KILL_DB, 20.0 * math.log10(position / CENTRE))


def _pass(kind: str, freq: float, q: float = FILTER_Q) -> np.ndarray:
    w0 = 2 * math.pi * min(freq, RATE * 0.45) / RATE
    alpha = math.sin(w0) / (2 * q)
    cos = math.cos(w0)
    if kind == "low":
        b = [(1 - cos) / 2, 1 - cos, (1 - cos) / 2]
    else:
        b = [(1 + cos) / 2, -(1 + cos), (1 + cos) / 2]
    a0 = 1 + alpha
    return np.array([*b, a0, -2 * cos, 1 - alpha]) / a0


def filter_cutoff(position: float) -> tuple[str, float] | None:
    """('low' | 'high', cut-off Hz) for a Filter knob position, None at noon."""
    offset = min(100.0, max(0.0, position)) - CENTRE
    if abs(offset) <= FILTER_DEAD_ZONE:
        return None
    amount = (abs(offset) - FILTER_DEAD_ZONE) / (CENTRE - FILTER_DEAD_ZONE)
    start, end = LOW_PASS_RANGE if offset < 0 else HIGH_PASS_RANGE
    return ("low" if offset < 0 else "high"), start * (end / start) ** amount


def _crossover(kind: str, freq: float) -> np.ndarray:
    """A Linkwitz-Riley 4th-order low- or high-pass: two Butterworth biquads."""
    section = butter(2, freq, btype="lowpass" if kind == "low" else "highpass", fs=RATE, output="sos")
    return np.vstack([section, section])


_LOW_SPLIT = (_crossover("low", LOW_HZ), _crossover("high", LOW_HZ))
_HIGH_SPLIT = (_crossover("low", HIGH_HZ), _crossover("high", HIGH_HZ))


def _gain(position: float) -> float:
    return 10 ** (knob_db(position) / 20.0) if position > 0 else 0.0


class ChannelStrip:
    """One DJ's Low / Mid / High / Filter, applied to stereo float blocks.

    A DJ isolator: Linkwitz-Riley crossovers split the sound into a low band
    (below 250 Hz), a mid band and a high band (above 4 kHz) that add back to
    the original's level at noon. Each band gets its knob's gain
    (a full cut at 0), then the Filter."""

    def __init__(self, channels: int = 2) -> None:
        # 6 crossover filters: low/rest at 250 Hz, mid/high at 4 kHz, and the
        # same 4 kHz pair on the low band so its phase matches the others.
        self._states = [np.zeros((2, 2, channels)) for _ in range(6)]
        self._filter_state = np.zeros((1, 2, channels))
        self._filter_sos: np.ndarray | None = None
        self._filter_setting: float | None = None
        self.low = self.mid = self.high = self.filter = float(CENTRE)

    def reset(self) -> None:
        self.low = self.mid = self.high = self.filter = float(CENTRE)

    @property
    def flat(self) -> bool:
        return self.low == self.mid == self.high == CENTRE and filter_cutoff(self.filter) is None

    def _run(self, index: int, sos: np.ndarray, x: np.ndarray) -> np.ndarray:
        y, self._states[index] = sosfilt(sos, x, axis=0, zi=self._states[index])
        return y

    def _split(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Three bands that add back to the original's level (all filters always
        run, so a knob turned later starts from a warm state)."""
        low = self._run(0, _LOW_SPLIT[0], x)
        rest = self._run(1, _LOW_SPLIT[1], x)
        mid = self._run(2, _HIGH_SPLIT[0], rest)
        high = self._run(3, _HIGH_SPLIT[1], rest)
        low = self._run(4, _HIGH_SPLIT[0], low) + self._run(5, _HIGH_SPLIT[1], low)
        return low, mid, high

    def process(self, samples: np.ndarray) -> np.ndarray:
        """``samples`` (frames x channels) through the strip; the filter state carries over."""
        if not len(samples):
            return samples
        x = samples.astype(np.float64, copy=False)
        low, mid, high = self._split(x)
        if self.low == self.mid == self.high == CENTRE:
            out = x  # flat: the original itself, not its phase-shifted sum
        else:
            out = _gain(self.low) * low + _gain(self.mid) * mid + _gain(self.high) * high
        if self.filter != self._filter_setting:
            cutoff = filter_cutoff(self.filter)
            self._filter_sos = None if cutoff is None else _pass(*cutoff)[None, :]
            self._filter_setting = self.filter
        if self._filter_sos is None:
            self._filter_state[:] = 0.0
        else:
            out, self._filter_state = sosfilt(self._filter_sos, out, axis=0, zi=self._filter_state)
        return out.astype(np.float32)


def _response(sos: np.ndarray, freq: float) -> complex:
    z = np.exp(-1j * 2 * math.pi * freq / RATE)
    gain = 1.0 + 0j
    for b0, b1, b2, a0, a1, a2 in sos:
        gain *= (b0 + b1 * z + b2 * z * z) / (a0 + a1 * z + a2 * z * z)
    return gain


def response_db(strip: ChannelStrip, freq: float) -> float:
    """The strip's gain at ``freq`` (for tests and a future curve display)."""
    low_lp, low_hp = (_response(sos, freq) for sos in _LOW_SPLIT)
    high_lp, high_hp = (_response(sos, freq) for sos in _HIGH_SPLIT)
    low = low_lp * (high_lp + high_hp)
    total = _gain(strip.low) * low + _gain(strip.mid) * low_hp * high_lp + _gain(strip.high) * low_hp * high_hp
    cutoff = filter_cutoff(strip.filter)
    if cutoff is not None:
        total *= _response(_pass(*cutoff)[None, :], freq)
    return 20 * math.log10(max(abs(total), 1e-12))


def self_check() -> str | None:
    """Cut the lows of a 40 Hz tone: None when the EQ works in this build (SciPy
    bundled), else what failed. Run by the packaged app's ``--self-check-opus``."""
    try:
        strip = ChannelStrip()
        strip.low = 0
        t = np.arange(RATE // 2) / RATE
        tone = np.repeat((0.5 * np.sin(2 * np.pi * 40 * t))[:, None], 2, axis=1).astype(np.float32)
        out = np.concatenate([strip.process(tone[i : i + 240]) for i in range(0, len(tone), 240)])
    except Exception as error:  # noqa: BLE001 - reported, not hidden
        return f"{type(error).__name__}: {error}"
    if float(np.max(np.abs(out[len(out) // 2 :]))) > 0.05:
        return "the EQ did not cut the lows"
    return None
