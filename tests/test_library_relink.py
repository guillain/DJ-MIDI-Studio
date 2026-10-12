from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from djmidi.library.db import LibraryDB
from djmidi.library.metadata import TrackMetadata
from djmidi.library.relink import (
    MATCH_EXACT,
    MATCH_NAME,
    MATCH_TAGS,
    apply_relinks,
    find_relink_proposals,
)
from djmidi.library.scanner import scan_root


def _write(path: Path, size: int = 100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    return path


@pytest.fixture
def db():
    with LibraryDB(":memory:") as database:
        yield database


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def test_no_missing_tracks_means_no_proposals(db, tmp_path):
    _write(tmp_path / "a.mp3")
    scan_root(tmp_path, db)
    assert find_relink_proposals(db) == []


def test_moved_file_is_a_confident_exact_match(db, tmp_path):
    old = _write(tmp_path / "Old" / "Track.mp3", 120)
    _write(tmp_path / "Other" / "track.mp3", 999)  # same name, different size
    scan_root(tmp_path, db)
    _move(old, tmp_path / "New" / "TRACK.mp3")
    scan_root(tmp_path, db)

    [proposal] = find_relink_proposals(db)
    assert proposal.missing.path == str(old)
    assert proposal.confident
    assert proposal.best.path == str(tmp_path / "New" / "TRACK.mp3")
    assert proposal.best.match == MATCH_EXACT
    assert [c.match for c in proposal.candidates] == [MATCH_EXACT, MATCH_NAME]


def test_two_same_size_candidates_are_not_confident(db, tmp_path):
    old = _write(tmp_path / "a" / "x.mp3")
    scan_root(tmp_path, db)
    old.unlink()
    _write(tmp_path / "b" / "x.mp3")
    _write(tmp_path / "c" / "x.mp3")
    scan_root(tmp_path, db)
    [proposal] = find_relink_proposals(db)
    assert len(proposal.candidates) == 2
    assert not proposal.confident


def test_one_file_claimed_by_two_missing_tracks_is_not_confident(db, tmp_path):
    first = _write(tmp_path / "a" / "x.mp3")
    second = _write(tmp_path / "b" / "x.mp3")
    scan_root(tmp_path, db)
    first.unlink()
    _move(second, tmp_path / "c" / "x.mp3")
    scan_root(tmp_path, db)
    proposals = find_relink_proposals(db)
    assert len(proposals) == 2
    assert not any(p.confident for p in proposals)


def test_unindexed_file_under_a_root_is_found(db, tmp_path):
    old = _write(tmp_path / "a" / "x.mp3")
    scan_root(tmp_path, db)
    _move(old, tmp_path / "b" / "x.mp3")
    db.mark_missing_except(db.list_roots()[0].id, [])  # moved, not rescanned
    [proposal] = find_relink_proposals(db)
    assert proposal.confident and proposal.best.indexed is False
    assert find_relink_proposals(db, search_roots=False)[0].candidates == []


def test_cached_tags_rank_and_add_candidates(db, tmp_path):
    old = _write(tmp_path / "a" / "x.mp3")
    scan_root(tmp_path, db)
    track = db.get_track_by_path(old)
    db.set_cached_metadata(track.id, track.mtime, TrackMetadata(title="Alpha", artist="Zed"))
    old.unlink()
    renamed = _write(tmp_path / "b" / "01 - Alpha.mp3")
    same_name = _write(tmp_path / "c" / "x.mp3", 50)
    scan_root(tmp_path, db)
    renamed_track = db.get_track_by_path(renamed)
    db.set_cached_metadata(renamed_track.id, renamed_track.mtime, TrackMetadata(title="alpha ", artist="ZED"))
    [proposal] = find_relink_proposals(db)
    assert [(c.path, c.match) for c in proposal.candidates] == [(str(same_name), MATCH_NAME), (str(renamed), MATCH_TAGS)]
    assert not proposal.confident


def test_apply_merges_into_indexed_file_and_moves_playlists_and_cache(db, tmp_path):
    old = _write(tmp_path / "a" / "x.mp3")
    scan_root(tmp_path, db)
    track = db.get_track_by_path(old)
    db.set_cached_metadata(track.id, track.mtime, TrackMetadata(title="Alpha"))
    playlist = db.create_playlist("Set", [str(old), "/elsewhere/y.mp3"])
    new = tmp_path / "b" / "x.mp3"
    _move(old, new)
    scan_root(tmp_path, db)

    [proposal] = find_relink_proposals(db)
    result = apply_relinks(db, [(proposal.missing, proposal.best)])
    assert result.relinked == 1 and result.skipped == []
    assert db.get_track_by_path(old) is None
    assert [t.path for t in db.list_tracks()] == [str(new)]
    assert db.playlist_paths(playlist) == [str(new), "/elsewhere/y.mp3"]
    _mtime, metadata = db.get_cached_metadata(db.get_track_by_path(new).id)
    assert metadata.title == "Alpha"


def test_apply_keeps_the_found_files_own_cache(db, tmp_path):
    old = _write(tmp_path / "a" / "x.mp3")
    scan_root(tmp_path, db)
    track = db.get_track_by_path(old)
    db.set_cached_metadata(track.id, track.mtime, TrackMetadata(title="Old"))
    new = tmp_path / "b" / "x.mp3"
    _move(old, new)
    scan_root(tmp_path, db)
    new_track = db.get_track_by_path(new)
    db.set_cached_metadata(new_track.id, new_track.mtime, TrackMetadata(title="Fresh"))
    [proposal] = find_relink_proposals(db)
    apply_relinks(db, [(proposal.missing, proposal.best)])
    assert db.get_cached_metadata(new_track.id)[1].title == "Fresh"


def test_apply_renames_the_missing_row_when_the_file_is_not_indexed(db, tmp_path):
    old = _write(tmp_path / "a" / "x.mp3")
    scan_root(tmp_path, db)
    track = db.get_track_by_path(old)
    db.set_cached_metadata(track.id, track.mtime, TrackMetadata(title="Alpha"))
    new = tmp_path / "b" / "x.mp3"
    _move(old, new)
    db.mark_missing_except(track.root_id, [])
    [proposal] = find_relink_proposals(db)
    apply_relinks(db, [(proposal.missing, proposal.best)])
    relinked = db.get_track_by_path(new)
    assert relinked.id == track.id and relinked.missing is False
    assert db.get_cached_metadata(track.id)[1].title == "Alpha"


def test_apply_skips_vanished_or_out_of_root_candidates(db, tmp_path):
    old = _write(tmp_path / "root" / "a" / "x.mp3")
    scan_root(tmp_path / "root", db)
    new = tmp_path / "root" / "b" / "x.mp3"
    _move(old, new)
    scan_root(tmp_path / "root", db)
    [proposal] = find_relink_proposals(db)
    new.unlink()
    result = apply_relinks(db, [(proposal.missing, proposal.best)])
    assert result.relinked == 0 and result.skipped == [str(new)]
    assert db.get_track_by_path(old).missing


def test_relink_tracks_is_all_or_nothing(db, tmp_path):
    first = _write(tmp_path / "a" / "x.mp3")
    second = _write(tmp_path / "a" / "y.mp3")
    scan_root(tmp_path, db)
    one, two = db.get_track_by_path(first), db.get_track_by_path(second)
    first.unlink()
    second.unlink()
    db.mark_missing_except(one.root_id, [])
    playlist = db.create_playlist("Set", [str(first)])
    bad_root = 10_000  # violates the roots foreign key
    with pytest.raises(sqlite3.IntegrityError):
        db.relink_tracks(
            [
                (one.id, str(tmp_path / "b.mp3"), one.root_id, 1, 1.0),
                (two.id, str(tmp_path / "c.mp3"), bad_root, 1, 1.0),
            ]
        )
    assert db.get_track_by_path(first).missing
    assert db.get_track_by_path(tmp_path / "b.mp3") is None
    assert db.playlist_paths(playlist) == [str(first)]
    assert db.relink_tracks([(9_999, "/nowhere.mp3", one.root_id, 1, 1.0)]) == 0
