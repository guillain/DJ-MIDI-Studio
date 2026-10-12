"""Background BPM/key analysis of untagged tracks (issue #224), Qt-free
half: the suggestion store in `LibraryDB` and the `workspace` job. Every
analyser here is a stub -- librosa is an optional extra."""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TBPM, TIT2, TKEY

from djmidi.library import analysis, workspace
from djmidi.library.db import LibraryDB
from djmidi.library.metadata import read_metadata
from djmidi.library.scanner import scan_root


def _mp3(path: Path, title: str, bpm: str | None = None, key: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((frame + b"\x00" * (417 - len(frame))) * 20)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=[title]))
    if bpm:
        tags.add(TBPM(encoding=3, text=[bpm]))
    if key:
        tags.add(TKEY(encoding=3, text=[key]))
    tags.save(path)
    return path


def _drain(steps):
    counts = []
    while True:
        try:
            counts.append(next(steps))
        except StopIteration as done:
            return counts, done.value


@pytest.fixture
def analysis_db(tmp_path):
    _mp3(tmp_path / "tagged.mp3", "Tagged", bpm="174", key="Am")
    _mp3(tmp_path / "no_bpm.mp3", "NoBpm", key="C")
    _mp3(tmp_path / "bare.mp3", "Bare")
    with LibraryDB() as db:
        scan_root(tmp_path, db)
        _drain(workspace.iter_refresh_metadata(db))
        yield db, tmp_path


def test_analysis_only_targets_tracks_missing_bpm_or_key(analysis_db):
    db, music = analysis_db
    calls = []

    def analyser(path, want_bpm, want_key):
        calls.append((Path(path).name, want_bpm, want_key))
        return 128.004, "F#m"

    counts, found = _drain(workspace.iter_analyse_missing(db, analyser))
    assert counts == [1, 2] and found == 2
    assert sorted(calls) == [("bare.mp3", True, True), ("no_bpm.mp3", True, False)]
    rows = {row.title: row for row in workspace.consolidate(db)}
    # Only empty tags get a suggestion; the existing key "C" stays alone.
    assert (rows["NoBpm"].bpm_suggestion, rows["NoBpm"].key_suggestion) == (128.0, None)
    assert (rows["Bare"].bpm_suggestion, rows["Bare"].key_suggestion) == (128.0, "F#m")
    assert not rows["Tagged"].has_analysis_suggestion
    # Suggestions never touch the files.
    assert read_metadata(music / "bare.mp3").bpm is None
    # Already analysed: a second run has nothing left to do.
    assert db.tracks_needing_analysis() == []


def test_failed_analysis_is_recorded_and_not_retried(analysis_db):
    db, _music = analysis_db

    def broken(path, want_bpm, want_key):
        raise RuntimeError("cannot decode")

    counts, found = _drain(workspace.iter_analyse_missing(db, broken))
    assert counts == [1, 2] and found == 0
    assert db.tracks_needing_analysis() == []
    assert db.analysis_suggestions() == {}


def test_changed_file_drops_its_stale_estimate(analysis_db):
    db, music = analysis_db
    _drain(workspace.iter_analyse_missing(db, lambda path, b, k: (140.0, "Dm")))
    bare = db.get_track_by_path(str(music / "bare.mp3"))
    assert bare.id in db.analysis_suggestions()
    db.upsert_track(bare.root_id, bare.path, bare.size, bare.mtime + 10)
    assert bare.id not in db.analysis_suggestions()
    # Its cached tags are stale too, so it waits for the next tag refresh
    # before being analysed again.
    assert bare.path not in {record.path for record in db.tracks_needing_analysis()}
    _drain(workspace.iter_refresh_metadata(db))
    assert bare.path in {record.path for record in db.tracks_needing_analysis()}


def test_analysis_tag_changes_fill_only_empty_tags(analysis_db):
    db, _music = analysis_db
    _drain(workspace.iter_analyse_missing(db, lambda path, b, k: (140.0, "Dm")))
    changes = workspace.analysis_tag_changes(workspace.consolidate(db))
    by_name = {Path(path).name: change for path, change in changes.items()}
    assert by_name == {
        "bare.mp3": ({"bpm": None, "key": None}, {"bpm": 140.0, "key": "Dm"}),
        "no_bpm.mp3": ({"bpm": None}, {"bpm": 140.0}),
    }


def test_removing_a_root_drops_its_suggestions(analysis_db):
    db, _music = analysis_db
    _drain(workspace.iter_analyse_missing(db, lambda path, b, k: (140.0, "Dm")))
    db.remove_root(db.list_roots()[0].id)
    assert db.analysis_suggestions() == {}


def test_analyse_clip_requires_the_optional_extra(monkeypatch, tmp_path):
    monkeypatch.setattr(analysis, "librosa", None)
    assert analysis.analysis_available() is False
    with pytest.raises(RuntimeError, match="analysis"):
        analysis.analyse_clip(tmp_path / "x.wav")
