from __future__ import annotations

import re
from pathlib import Path

try:
    import librosa
except ImportError:  # pragma: no cover - exercised only when the optional extra is absent
    librosa = None

# Camelot wheel number for each major-key pitch class (0=C, 1=C#, ... 11=B),
# i.e. what a track tagged with that major key would be, e.g. C -> 8B.
_MAJOR_CAMELOT_NUMBER = {0: 8, 1: 3, 2: 10, 3: 5, 4: 12, 5: 7, 6: 2, 7: 9, 8: 4, 9: 11, 10: 6, 11: 1}

# A minor key shares its Camelot number with its relative major (3 semitones
# up), only the letter differs (A instead of B) -- e.g. Am is the relative
# minor of C, so Am -> 8A, same number as C -> 8B.
_RELATIVE_MAJOR_OFFSET = 3

_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_MINOR_QUALITIES = {"m", "min", "minor"}

# Open Key notation (Mixed In Key's alternative to Camelot) numbers the same
# circle of fifths 1-12 with a 'd' (major, "dur") / 'm' (minor, "moll") suffix
# instead of Camelot's B/A, offset from Camelot's own numbering by a fixed 6.
_OPEN_KEY_TO_CAMELOT_NUMBER = {n: ((n + 6) % 12) + 1 for n in range(1, 13)}

_CAMELOT_RE = re.compile(r"^(1[0-2]|[1-9])([ab])$", re.IGNORECASE)
_OPEN_KEY_RE = re.compile(r"^(1[0-2]|[1-9])([md])$", re.IGNORECASE)
_NOTE_RE = re.compile(r"^([A-G])([#b]?)(maj|major|min|minor|m)?$", re.IGNORECASE)


def to_camelot(musical_key: str | None) -> str | None:
    """Map a musical key notation to its Camelot wheel code, or None if unrecognized.

    Accepts standard note notation (`C`, `Am`, `F#m`, `Ebm`, ...), Open Key
    notation (`7m`, `1d`, ...), and Camelot codes themselves (returned
    normalized, e.g. `8b` -> `8B`) so callers don't need to know which
    notation a given tag is already in.
    """
    if not musical_key:
        return None
    key = musical_key.strip()
    if not key:
        return None

    camelot_match = _CAMELOT_RE.match(key)
    if camelot_match:
        number, letter = camelot_match.groups()
        return f"{int(number)}{letter.upper()}"

    open_key_match = _OPEN_KEY_RE.match(key)
    if open_key_match:
        number, quality = open_key_match.groups()
        camelot_number = _OPEN_KEY_TO_CAMELOT_NUMBER[int(number)]
        letter = "A" if quality.lower() == "m" else "B"
        return f"{camelot_number}{letter}"

    note_match = _NOTE_RE.match(key)
    if note_match:
        letter, accidental, quality = note_match.groups()
        pitch_class = _PITCH_CLASS[letter.upper()]
        if accidental == "#":
            pitch_class += 1
        elif accidental.lower() == "b":
            pitch_class -= 1
        pitch_class %= 12
        is_minor = bool(quality) and quality.lower() in _MINOR_QUALITIES
        if is_minor:
            pitch_class = (pitch_class + _RELATIVE_MAJOR_OFFSET) % 12
        camelot_number = _MAJOR_CAMELOT_NUMBER[pitch_class]
        return f"{camelot_number}{'A' if is_minor else 'B'}"

    return None


def _require_librosa() -> None:
    if librosa is None:
        raise RuntimeError(
            "librosa is required for audio-based BPM/key analysis. Install the "
            "optional 'analysis' extra, e.g. `uv sync --extra analysis` or "
            "`pip install djmidi[analysis]`."
        )


def estimate_bpm(path: str | Path) -> float | None:
    """Estimate BPM from audio via beat tracking. Requires the 'analysis' extra."""
    _require_librosa()
    y, sr = librosa.load(str(path), sr=None, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    # librosa has returned a bare float in some versions and a 1-element
    # array in others (e.g. 0.10+); normalize either to a plain float.
    value = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return value if value > 0 else None


# Krumhansl-Schmuckler key profiles (relative pitch-class weights, tonic
# first), the standard textbook approach for chroma-based key estimation.
# Deliberately kept simple: this is a "strong suggestion", not ground truth
# (see the module-level confidence caveat below).
_MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
_PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def estimate_key(path: str | Path) -> str | None:
    """Estimate musical key from audio chroma via Krumhansl-Schmuckler profile matching.

    Requires the 'analysis' extra. Meaningfully less reliable than
    `estimate_bpm` -- chroma-based key estimation commonly sits in the
    70-90% accuracy range and can be thrown off by heavy bass/kick content,
    so a caller should always let the user confirm/correct the result
    rather than trust it silently (see issue #128).
    """
    _require_librosa()
    import numpy as np

    y, sr = librosa.load(str(path), sr=None, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    if not np.any(chroma_mean):
        return None

    best_score = -float("inf")
    best_key = None
    for shift in range(12):
        major_score = np.corrcoef(chroma_mean, np.roll(_MAJOR_PROFILE, shift))[0, 1]
        minor_score = np.corrcoef(chroma_mean, np.roll(_MINOR_PROFILE, shift))[0, 1]
        if major_score > best_score:
            best_score = major_score
            best_key = _PITCH_NAMES[shift]
        if minor_score > best_score:
            best_score = minor_score
            best_key = f"{_PITCH_NAMES[shift]}m"
    return best_key


def resolve_bpm_key(
    existing_bpm: float | None,
    existing_key: str | None,
    audio_path: str | Path,
) -> tuple[float | None, str | None]:
    """Prefer existing tag values; only run audio analysis for what's missing.

    A no-op fallback (returns the existing values unchanged) when librosa
    isn't installed, rather than raising -- callers that already have both
    values, or don't have the optional extra installed, pay no cost.
    """
    bpm = existing_bpm
    key = existing_key
    if librosa is not None:
        if bpm is None:
            bpm = estimate_bpm(audio_path)
        if key is None:
            key = estimate_key(audio_path)
    return bpm, key
