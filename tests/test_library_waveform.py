"""Waveform overview for the audio preview bar (issue #407)."""

from __future__ import annotations

import pytest

from djmidi.library import waveform
from djmidi.library.db import LibraryDB


def _make_loud_then_quiet_wav(tmp_path, sr=8000, seconds=4.0):
    np = pytest.importorskip("numpy")
    soundfile = pytest.importorskip("soundfile")

    n_samples = int(seconds * sr)
    audio = np.zeros(n_samples, dtype="float32")
    audio[: n_samples // 2] = 0.9  # loud first half
    # second half stays silent
    path = tmp_path / "loud_then_quiet.wav"
    soundfile.write(path, audio, sr)
    return path


def test_waveform_available_reflects_librosa_import():
    assert waveform.waveform_available() == (waveform.librosa is not None)


def test_compute_waveform_peaks_without_librosa_raises(monkeypatch):
    monkeypatch.setattr(waveform, "librosa", None)
    with pytest.raises(RuntimeError, match="analysis"):
        waveform.compute_waveform_peaks("whatever.wav")


def test_compute_waveform_peaks_on_synthetic_audio(tmp_path):
    pytest.importorskip("librosa")
    path = _make_loud_then_quiet_wav(tmp_path)

    peaks = waveform.compute_waveform_peaks(str(path), buckets=20)

    assert len(peaks) == 20
    assert all(0.0 <= value <= 1.0 for value in peaks)
    assert max(peaks[:9]) > 0.5  # loud first half
    assert max(peaks[11:]) < 0.1  # silent second half
    assert max(peaks) == pytest.approx(1.0)  # normalized to the loudest bucket


def test_compute_waveform_peaks_handles_a_silent_file(tmp_path):
    pytest.importorskip("librosa")
    np = pytest.importorskip("numpy")
    soundfile = pytest.importorskip("soundfile")
    path = tmp_path / "silence.wav"
    soundfile.write(path, np.zeros(8000, dtype="float32"), 8000)

    peaks = waveform.compute_waveform_peaks(str(path), buckets=10)

    assert peaks == [0.0] * 10


def test_cached_peaks_is_none_without_a_cache_entry():
    db = LibraryDB()
    root = db.add_root("/music")
    db.upsert_track(root.id, "/music/a.mp3", size=1, mtime=1.0)
    record = db.list_tracks()[0]
    assert waveform.cached_peaks(db, record) is None


def test_cached_peaks_roundtrips_and_detects_a_changed_file():
    db = LibraryDB()
    root = db.add_root("/music")
    db.upsert_track(root.id, "/music/a.mp3", size=1, mtime=1.0)
    record = db.list_tracks()[0]
    db.set_cached_waveform(record.id, record.mtime, [0.1, 0.9, 0.5])

    assert waveform.cached_peaks(db, record) == [0.1, 0.9, 0.5]

    db.upsert_track(root.id, "/music/a.mp3", size=1, mtime=2.0)  # file changed
    changed = db.list_tracks()[0]
    assert waveform.cached_peaks(db, changed) is None


def test_get_cached_waveform_tolerates_corrupt_json():
    db = LibraryDB()
    root = db.add_root("/music")
    db.upsert_track(root.id, "/music/a.mp3", size=1, mtime=1.0)
    record = db.list_tracks()[0]
    db._conn.execute(
        "INSERT INTO waveform_cache (track_id, mtime, peaks) VALUES (?, ?, ?)", (record.id, record.mtime, "not json")
    )
    assert db.get_cached_waveform(record.id) is None
