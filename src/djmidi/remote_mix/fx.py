"""Beat-synced effects on the official mix (the console), Qt-free.

Two send effects, as on a club mixer's master section:

- **Delay**: echoes of the mix a fraction of a beat later, at the tempo of
  the session (Link), so they land on the grid; a knob sets how much.
- **Reverb**: a room around the mix (a small Schroeder reverb: four
  feedback combs, then two all-pass filters); a knob sets how much.

Both work block by block on 48 kHz stereo float32 and keep their state
between blocks. A feedback line ``y[n] = x[n] + g * y[n - D]`` only needs
outputs at least ``D`` samples old, so a block is cut into chunks no longer
than ``D`` and each chunk is computed at once with numpy.
"""

from __future__ import annotations

import numpy as np

from djmidi.remote_mix import audio

DELAY_BEATS = (0.5, 0.75, 1.0, 2.0)  # the delay's choices, in beats
DELAY_FEEDBACK = 0.45
_MAX_DELAY_S = 4.0
_COMBS = (1557, 1617, 1491, 1422)  # Freeverb's comb lengths at 44.1 kHz
_ALLPASSES = (556, 441)
_COMB_FEEDBACK = 0.80
_ALLPASS_GAIN = 0.5


def _scaled(samples: int) -> int:
    return round(samples * audio.RATE / 44_100)


class _Line:
    """A delay line remembering its last ``size`` frames."""

    def __init__(self, size: int) -> None:
        self.history = np.zeros((size, audio.CHANNELS), dtype=np.float32)

    def past(self, delay: int, n: int) -> np.ndarray:
        """The ``n`` frames written ``delay`` frames before the next ones (``n <= delay``)."""
        start = len(self.history) - delay
        return self.history[start : start + n]

    def push(self, frames: np.ndarray) -> None:
        self.history = np.concatenate([self.history[len(frames) :], frames]) if len(frames) < len(self.history) else frames[-len(self.history) :].copy()


def _chunks(n: int, size: int):
    for start in range(0, n, size):
        yield start, min(n, start + size)


class _Comb:
    def __init__(self, delay: int) -> None:
        self.delay = delay
        self.line = _Line(delay)

    def process(self, x: np.ndarray) -> np.ndarray:
        y = np.empty_like(x)
        for a, b in _chunks(len(x), self.delay):
            y[a:b] = x[a:b] + _COMB_FEEDBACK * self.line.past(self.delay, b - a)
            self.line.push(y[a:b])
        return y


class _AllPass:
    def __init__(self, delay: int) -> None:
        self.delay = delay
        self.inputs = _Line(delay)
        self.outputs = _Line(delay)

    def process(self, x: np.ndarray) -> np.ndarray:
        y = np.empty_like(x)
        g = _ALLPASS_GAIN
        for a, b in _chunks(len(x), self.delay):
            n = b - a
            y[a:b] = -g * x[a:b] + self.inputs.past(self.delay, n) + g * self.outputs.past(self.delay, n)
            self.inputs.push(x[a:b])
            self.outputs.push(y[a:b])
        return y


class Reverb:
    def __init__(self) -> None:
        self._combs = [_Comb(_scaled(d)) for d in _COMBS]
        self._allpasses = [_AllPass(_scaled(d)) for d in _ALLPASSES]

    def process(self, x: np.ndarray, amount: float) -> np.ndarray:
        """The mix with ``amount`` (0..1) of reverb added."""
        if amount <= 0.0:
            self.feed_silence(len(x))
            return x
        wet = sum(comb.process(x) for comb in self._combs) / len(self._combs)
        for allpass in self._allpasses:
            wet = allpass.process(wet)
        return (x + amount * wet).astype(np.float32)

    def feed_silence(self, n: int) -> None:
        """Keep the tail ringing out while the knob is down."""
        silence = np.zeros((n, audio.CHANNELS), dtype=np.float32)
        tail = sum(comb.process(silence) for comb in self._combs)
        for allpass in self._allpasses:
            allpass.process(tail / len(self._combs))


class BeatDelay:
    def __init__(self) -> None:
        self._line = _Line(int(_MAX_DELAY_S * audio.RATE))

    @staticmethod
    def frames(beats: float, tempo: float) -> int:
        tempo = tempo if tempo > 0 else 120.0
        return max(1, min(int(_MAX_DELAY_S * audio.RATE) - 1, round(beats * 60.0 / tempo * audio.RATE)))

    def process(self, x: np.ndarray, amount: float, beats: float, tempo: float) -> np.ndarray:
        """The mix with echoes ``beats`` later at ``tempo``, ``amount`` (0..1) loud."""
        delay = self.frames(beats, tempo)
        out = np.empty_like(x)
        for a, b in _chunks(len(x), delay):
            echo = self._line.past(delay, b - a)
            out[a:b] = x[a:b] + amount * echo
            # What goes into the line: the mix (only while the knob is up) plus the echo fed back.
            self._line.push((x[a:b] * (1.0 if amount > 0 else 0.0) + DELAY_FEEDBACK * echo).astype(np.float32))
        return out


class MasterFx:
    """The console's effects on the official mix."""

    def __init__(self) -> None:
        self.delay = BeatDelay()
        self.reverb = Reverb()

    def process(self, mix: np.ndarray, *, delay: float, beats: float, reverb: float, tempo: float) -> np.ndarray:
        mix = self.delay.process(mix, delay, beats, tempo)
        return self.reverb.process(mix, reverb)
