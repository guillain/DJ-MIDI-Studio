import re

import pytest

from djmidi.library import estimate_bpm, estimate_key, resolve_bpm_key, to_camelot

# Real-world notations found in the maintainer's own library (issue #128
# investigation comment), plus a couple of Camelot-passthrough/flat-spelling
# cases for robustness.
CAMELOT_CASES = [
    ("Am", "8A"),
    ("Ebm", "2A"),
    ("F#m", "11A"),
    ("G#m", "1A"),
    ("C#m", "12A"),
    ("Fm", "4A"),
    ("G", "9B"),
    ("E", "12B"),
    # Open Key notation (Mixed In Key) -- 7m is D#/Eb minor, matching Ebm above.
    ("7m", "2A"),
    ("1d", "8B"),
    ("1m", "8A"),
    ("12m", "7A"),
    # Enharmonic flat spellings should agree with their sharp counterparts.
    ("Db", "3B"),
    ("Dbm", "12A"),
    ("Bb", "6B"),
    ("Bbm", "3A"),
    ("Gb", "2B"),
    ("Gbm", "11A"),
    # Camelot codes passed straight through (and normalized).
    ("8B", "8B"),
    ("8b", "8B"),
    ("1A", "1A"),
    # Explicit "maj"/"min" suffixes and lowercase input.
    ("Amaj", "11B"),
    ("Amin", "8A"),
    ("am", "8A"),
    ("c", "8B"),
]


@pytest.mark.parametrize("musical_key,expected", CAMELOT_CASES)
def test_to_camelot_known_notations(musical_key, expected):
    assert to_camelot(musical_key) == expected


def test_to_camelot_all_24_major_and_minor_keys_are_covered():
    majors = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    minors = [f"{letter}m" for letter in majors]
    camelot_codes = {to_camelot(k) for k in majors + minors}
    # 12 majors (B) + 12 minors (A), all distinct Camelot codes 1-12 of each letter.
    assert camelot_codes == {f"{n}{letter}" for n in range(1, 13) for letter in "AB"}


@pytest.mark.parametrize("musical_key", [None, "", "   ", "H", "Xm", "13A", "0m", "Hmaj"])
def test_to_camelot_unrecognized_or_empty_returns_none(musical_key):
    assert to_camelot(musical_key) is None


def _make_click_track_wav(tmp_path, duration_seconds=4.0, bpm=128.0, sr=22050):
    np = pytest.importorskip("numpy")
    soundfile = pytest.importorskip("soundfile")

    beat_interval = 60.0 / bpm
    n_samples = int(duration_seconds * sr)
    audio = np.zeros(n_samples, dtype="float32")
    click_duration = int(0.02 * sr)
    t = 0.0
    while t < duration_seconds:
        start = int(t * sr)
        end = min(start + click_duration, n_samples)
        envelope = np.linspace(1.0, 0.0, end - start, dtype="float32")
        audio[start:end] += envelope
        t += beat_interval

    path = tmp_path / "click_track.wav"
    soundfile.write(path, audio, sr)
    return path


def test_estimate_bpm_on_synthetic_click_track_is_in_a_sane_range(tmp_path):
    pytest.importorskip("librosa")
    path = _make_click_track_wav(tmp_path, bpm=128.0)

    bpm = estimate_bpm(path)

    assert bpm is not None
    # Beat trackers commonly lock onto a half/double-time multiple of the
    # true tempo, so accept 128 or one of its simple multiples/divisors.
    assert any(abs(bpm - 128.0 * factor) < 5.0 for factor in (0.5, 1.0, 2.0))


def test_estimate_key_on_synthetic_audio_returns_a_plausible_key_or_none(tmp_path):
    pytest.importorskip("librosa")
    path = _make_click_track_wav(tmp_path, bpm=128.0)

    key = estimate_key(path)

    # A click track carries no real tonal content, so this only asserts the
    # estimator doesn't crash and returns *something* shaped like a key.
    assert key is None or re.fullmatch(r"[A-G]#?m?", key)


def test_estimate_bpm_without_librosa_raises_clear_error(monkeypatch):
    import djmidi.library.analysis as analysis_module

    monkeypatch.setattr(analysis_module, "librosa", None)
    with pytest.raises(RuntimeError, match="analysis"):
        analysis_module.estimate_bpm("does-not-matter.wav")


def test_resolve_bpm_key_prefers_existing_values(tmp_path):
    bpm, key = resolve_bpm_key(140.0, "Am", tmp_path / "unused.wav")
    assert bpm == 140.0
    assert key == "Am"


def test_resolve_bpm_key_is_noop_when_librosa_unavailable(monkeypatch, tmp_path):
    import djmidi.library.analysis as analysis_module

    monkeypatch.setattr(analysis_module, "librosa", None)
    bpm, key = analysis_module.resolve_bpm_key(None, None, tmp_path / "unused.wav")
    assert bpm is None
    assert key is None


def test_resolve_bpm_key_fills_missing_bpm_from_audio(tmp_path):
    pytest.importorskip("librosa")
    path = _make_click_track_wav(tmp_path, bpm=128.0)

    bpm, key = resolve_bpm_key(None, "Am", path)

    assert bpm is not None
    assert key == "Am"  # untouched, since it was already present
