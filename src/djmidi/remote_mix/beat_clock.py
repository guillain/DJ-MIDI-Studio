"""Our own beat clock, by listening: tempo and beat phase from the DJ's sound.

Without Ableton Link (or with a DJ program that doesn't speak it), the app can
still know where the beat is: it hears the sound it sends anyway. This follows
the onset-envelope approach of real-time beat trackers (spectral flux, tempo by
autocorrelation, phase by a comb of pulses, cf. Meier, Chiu & Müller's real-time
PLP, TISMIR 2024) in plain NumPy, with no model to bundle.

It reads; it never drives the DJ program. Beats line up with the music, but
which beat is "one" of the bar is unknown: the integer part of ``beat`` is the
clock's own count, not the track's bar.

Qt-free; `ListeningClock.reader` is a `probe.LinkReader`, so the connection
test, the bar-late playback and the phrase counter use it like Link.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from djmidi.remote_mix.probe import LinkSnapshot

ENVELOPE_RATE = 100  # onset-envelope frames per second (10 ms)
WINDOW_S = 8.0  # seconds of envelope analysed
MIN_BPM, MAX_BPM = 70.0, 180.0
PRIOR_BPM = 122.0  # club music: resolves double/half tempo
MIN_CONFIDENCE = 0.25
ESTIMATE_EVERY_S = 0.5
WARMUP_S = 3.0


@dataclass(frozen=True)
class Reading:
    tempo: float
    confidence: float  # 0..1, how clearly the sound pulses at that tempo


KICK_HZ = 200.0  # the beat in club music is the kick: phase from the lows


def onset_envelope(samples: np.ndarray, sample_rate: int, *, max_hz: float | None = None) -> np.ndarray:
    """Half-wave rectified log spectral flux, one value per 10 ms hop
    (only the bins up to ``max_hz`` when given)."""
    hop = sample_rate // ENVELOPE_RATE
    size = 1 << int(np.ceil(np.log2(hop * 2)))
    count = (len(samples) - size) // hop + 1
    if count < 2:
        return np.zeros(0)
    frames = np.lib.stride_tricks.sliding_window_view(samples, size)[::hop][:count]
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(size), axis=1))
    if max_hz is not None:
        spectrum = spectrum[:, 1 : max(2, int(max_hz * size / sample_rate) + 1)]
    spectrum = np.log1p(100.0 * spectrum)
    flux = np.maximum(np.diff(spectrum, axis=0), 0.0).sum(axis=1)
    return np.concatenate(([0.0], flux))


def estimate_tempo(envelope: np.ndarray, rate: float = ENVELOPE_RATE) -> Reading | None:
    """Tempo (BPM) of an onset envelope by autocorrelation, refined to a
    fraction of a frame, weighted towards club tempos."""
    env = envelope - envelope.mean()
    if len(env) < rate * 2 or not env.any():
        return None
    spectrum = np.fft.rfft(env, n=2 * len(env))
    acf = np.fft.irfft(spectrum * np.conj(spectrum))[: len(env)]
    if acf[0] <= 0:
        return None
    acf = acf / acf[0]
    lo = int(rate * 60.0 / MAX_BPM)
    hi = min(len(acf) - 2, int(np.ceil(rate * 60.0 / MIN_BPM)))
    lags = np.arange(lo, hi + 1)
    bpm = rate * 60.0 / lags
    prior = np.exp(-0.5 * (np.log2(bpm / PRIOR_BPM) / 0.5) ** 2)
    # A beat lag also correlates at twice the lag: add it, so the half tempo
    # of a straight four-on-the-floor doesn't win.
    double = acf[np.minimum(lags * 2, len(acf) - 1)]
    score = (acf[lags] + 0.5 * double) * prior
    best = int(np.argmax(score))
    # Twice as fast also pulses as strongly (drum & bass found at half speed):
    # take it when it fits the range.
    half = lags[best] / 2
    if rate * 60.0 / half <= MAX_BPM and np.interp(half, np.arange(len(acf)), acf) > 0.6 * acf[lags[best]]:
        best = int(np.argmin(np.abs(lags - half)))
    lag = float(lags[best])
    if 0 < best < len(lags) - 1:  # parabolic refinement on the raw acf
        a, b, c = acf[lags[best] - 1], acf[lags[best]], acf[lags[best] + 1]
        denom = a - 2 * b + c
        if denom < 0:
            lag += 0.5 * (a - c) / denom
    return Reading(tempo=rate * 60.0 / lag, confidence=float(max(0.0, min(1.0, acf[lags[best]]))))


def beat_phase(envelope: np.ndarray, period: float) -> float:
    """Where the beats fall in ``envelope`` (frames, 0 <= phase < period):
    the offset of the comb of pulses that collects the most onset energy.
    Recent frames weigh more, so a drifting beat is followed."""
    n = len(envelope)
    weights = np.linspace(0.3, 1.0, n)
    weighted = envelope * weights
    candidates = np.arange(0.0, period, 0.25)
    pulses = np.arange(0.0, n, period)
    best, best_score = 0.0, -1.0
    for offset in candidates:
        positions = pulses + offset
        positions = positions[positions < n - 1]
        index = positions.astype(int)
        frac = positions - index
        score = float(np.sum(weighted[index] * (1 - frac) + weighted[index + 1] * frac))
        if score > best_score:
            best, best_score = float(offset), score
    # Refine around the best quarter frame.
    return best


class ListeningClock:
    """Feed it the DJ's sound (``feed``); ``snapshot`` says the tempo and the
    beat at a given time once it is sure, like a Link session would."""

    def __init__(self, sample_rate: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.sample_rate = sample_rate
        self._clock = clock
        self._keep = int(sample_rate * WINDOW_S)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._buffer_end: float | None = None  # clock time of the last sample
        self._fed = 0  # samples heard so far: warm-up and estimate pace go by the sound, not the wall clock
        self._next_estimate = int(sample_rate * WARMUP_S)
        self.reading: Reading | None = None
        self._tempo: float | None = None
        self._anchor: tuple[float, float] | None = None  # (clock time, beat)

    def feed(self, samples: np.ndarray, at: float | None = None) -> None:
        """Mono or interleaved-stereo PCM (int16 or float); ``at`` = the
        clock time when the last sample was heard (default: now)."""
        at = self._clock() if at is None else at
        data = np.asarray(samples)
        if data.ndim == 2:
            data = data.mean(axis=1)
        data = data.astype(np.float32)
        if np.issubdtype(np.asarray(samples).dtype, np.integer):
            data /= 32768.0
        self._buffer = np.concatenate((self._buffer, data))[-self._keep :]
        self._buffer_end = at
        self._fed += len(data)
        if self._fed >= self._next_estimate:
            self._next_estimate = self._fed + int(self.sample_rate * ESTIMATE_EVERY_S)
            self._estimate()

    def _estimate(self) -> None:
        envelope = onset_envelope(self._buffer, self.sample_rate)
        reading = estimate_tempo(envelope)
        if reading is None or reading.confidence < MIN_CONFIDENCE:
            self.reading = reading
            if reading is None or reading.confidence < MIN_CONFIDENCE / 2:
                self._tempo, self._anchor = None, None
            return
        # DJ programs hold a tempo: smooth small changes, jump on big ones.
        if self._tempo is None or abs(reading.tempo - self._tempo) > 2.0:
            tempo = reading.tempo
        else:
            tempo = 0.7 * self._tempo + 0.3 * reading.tempo
        period = ENVELOPE_RATE * 60.0 / tempo
        lows = onset_envelope(self._buffer, self.sample_rate, max_hz=KICK_HZ)
        phase = beat_phase(lows if lows.any() else envelope, period)
        hop = self.sample_rate // ENVELOPE_RATE
        size = 1 << int(np.ceil(np.log2(hop * 2)))
        # Envelope frame i covers samples [i*hop, i*hop+size): its onset sits
        # near the window's middle.
        last_frame = phase + np.floor((len(envelope) - 1 - phase) / period) * period
        sample_of_beat = last_frame * hop + size / 2
        beat_time = self._buffer_end - (len(self._buffer) - sample_of_beat) / self.sample_rate
        if self._anchor is None or self._tempo is None:
            beat = 0.0
        else:
            predicted = self._anchor[1] + (beat_time - self._anchor[0]) * self._tempo / 60.0
            beat = float(np.round(predicted))  # keep counting: same beat numbers
        self._tempo = tempo
        self._anchor = (beat_time, beat)
        self.reading = Reading(tempo=tempo, confidence=reading.confidence)

    @property
    def locked(self) -> bool:
        return self._anchor is not None

    def snapshot(self, now: float | None = None) -> LinkSnapshot | None:
        if self._anchor is None or self._tempo is None:
            return None
        now = self._clock() if now is None else now
        t0, beat0 = self._anchor
        return LinkSnapshot(
            tempo=self._tempo, beat=beat0 + (now - t0) * self._tempo / 60.0, at=now, peers=0, quantum=1.0
        )

    def reader(self) -> LinkSnapshot | None:
        """A `probe.LinkReader`."""
        return self.snapshot()


__all__ = ["ListeningClock", "Reading", "beat_phase", "estimate_tempo", "onset_envelope"]
