"""Waveform overview for the audio preview bar (issue #407).

A precomputed amplitude envelope -- not full-resolution audio, just enough
buckets to see a track's structure (intro, drop, outro) at a glance, drawn
behind the preview bar's seek slider. Same "gap-filler" posture as
`analysis.py`'s BPM/key estimation: it only works when the optional
`analysis` extra (`librosa`) is installed, and the result is cached by the
file's mtime (`LibraryDB.set_cached_waveform`/`get_cached_waveform`) so a
track's envelope is only ever decoded once.
"""

from __future__ import annotations

try:
    import librosa
except ImportError:  # pragma: no cover - exercised only when the optional extra is absent
    librosa = None

from .db import LibraryDB
from .db import TrackRecord as _TrackRecord

DEFAULT_BUCKETS = 200
# Plenty for an amplitude envelope, and decodes much faster than a track's
# native sample rate.
SAMPLE_RATE = 8000


def waveform_available() -> bool:
    """Whether the optional 'analysis' extra (librosa) is installed."""
    return librosa is not None


def _require_librosa() -> None:
    if librosa is None:
        raise RuntimeError(
            "librosa is required for the waveform overview. Install the 'analysis' extra: "
            "uv sync --extra analysis"
        )


def compute_waveform_peaks(path: str, buckets: int = DEFAULT_BUCKETS) -> list[float]:
    """`buckets` amplitudes in 0..1 (the loudest bucket is 1.0; all zero
    for a silent file). Raises `RuntimeError` without the `analysis`
    extra, and whatever librosa itself raises for a file it can't decode
    -- a caller on a background thread should catch broadly, the same way
    `workspace.run_analyser` does for BPM/key estimation."""
    _require_librosa()
    samples, _sr = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    if samples.size == 0:
        return [0.0] * buckets
    bucket_size = max(1, len(samples) // buckets)
    peaks: list[float] = []
    for index in range(buckets):
        start = index * bucket_size
        end = len(samples) if index == buckets - 1 else start + bucket_size
        chunk = samples[start:end]
        peaks.append(float(abs(chunk).max()) if chunk.size else 0.0)
    largest = max(peaks)
    if largest <= 0:
        return peaks
    return [peak / largest for peak in peaks]


def cached_peaks(db: LibraryDB, record: _TrackRecord) -> list[float] | None:
    """The cached waveform for `record`, only if it's still fresh (the
    file hasn't changed since); `None` otherwise -- never computes it."""
    cached = db.get_cached_waveform(record.id)
    if cached is None or cached[0] != record.mtime:
        return None
    return cached[1]


__all__ = [
    "DEFAULT_BUCKETS",
    "SAMPLE_RATE",
    "cached_peaks",
    "compute_waveform_peaks",
    "waveform_available",
]
