import sqlite3

import pytest

from djmidi.library import LibraryDB
from djmidi.library.metadata import TrackMetadata


def test_add_root_is_idempotent():
    db = LibraryDB()
    first = db.add_root("/music/root")
    second = db.add_root("/music/root")
    assert first.id == second.id
    assert [r.path for r in db.list_roots()] == ["/music/root"]


def test_upsert_and_list_tracks():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=100, mtime=1.0)
    db.upsert_track(root.id, "/music/root/b.mp3", size=200, mtime=2.0)

    tracks = db.list_tracks(root_id=root.id)
    assert [t.path for t in tracks] == ["/music/root/a.mp3", "/music/root/b.mp3"]
    assert tracks[0].size == 100
    assert tracks[0].missing is False


def test_upsert_updates_existing_track():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=100, mtime=1.0)
    db.upsert_track(root.id, "/music/root/a.mp3", size=999, mtime=5.0)

    track = db.get_track_by_path("/music/root/a.mp3")
    assert track.size == 999
    assert track.mtime == 5.0


def test_mark_missing_except_flags_absent_tracks():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    db.upsert_track(root.id, "/music/root/b.mp3", size=1, mtime=1.0)

    flagged = db.mark_missing_except(root.id, seen_paths=["/music/root/a.mp3"])

    assert flagged == 1
    tracks = {t.path: t.missing for t in db.list_tracks(root_id=root.id)}
    assert tracks["/music/root/a.mp3"] is False
    assert tracks["/music/root/b.mp3"] is True


def test_upsert_clears_missing_flag_when_track_reappears():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    db.mark_missing_except(root.id, seen_paths=[])
    assert db.get_track_by_path("/music/root/a.mp3").missing is True

    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    assert db.get_track_by_path("/music/root/a.mp3").missing is False


def test_remove_root_cascades_to_tracks():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)

    db.remove_root(root.id)

    assert db.list_roots() == []
    assert db.list_tracks() == []


def test_list_tracks_can_exclude_missing():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    db.upsert_track(root.id, "/music/root/b.mp3", size=1, mtime=1.0)
    db.mark_missing_except(root.id, seen_paths=["/music/root/a.mp3"])

    present_only = db.list_tracks(root_id=root.id, include_missing=False)

    assert [t.path for t in present_only] == ["/music/root/a.mp3"]


def test_settings_roundtrip_and_survive_reopen(tmp_path):
    path = tmp_path / "library.sqlite3"
    db = LibraryDB(path)
    assert db.get_setting("missing", "fallback") == "fallback"
    db.set_setting("mix", {"direction": "down", "max_length": None})
    db.set_setting("mix", {"direction": "up", "max_length": 12})
    db.close()
    reopened = LibraryDB(path)
    assert reopened.get_setting("mix") == {"direction": "up", "max_length": 12}
    reopened.close()


def test_cached_metadata_roundtrips_duration():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    track = db.list_tracks()[0]

    db.set_cached_metadata(track.id, track.mtime, TrackMetadata(title="A", duration=123.4))

    _mtime, cached = db.get_cached_metadata(track.id)
    assert cached.duration == pytest.approx(123.4)


def test_duration_column_is_added_to_a_pre_existing_track_metadata_table(tmp_path):
    """A library index created before `duration` existed (issue #403) gains
    the column in place instead of failing at the next cache write."""
    path = tmp_path / "library.sqlite3"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE track_metadata (
            track_id INTEGER PRIMARY KEY, mtime REAL NOT NULL,
            title TEXT, artist TEXT, album TEXT, genre TEXT, bpm REAL, key TEXT,
            comment TEXT, rating TEXT, energy TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    db = LibraryDB(path)
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    track = db.list_tracks()[0]
    db.set_cached_metadata(track.id, track.mtime, TrackMetadata(duration=42.0))

    _mtime, cached = db.get_cached_metadata(track.id)
    assert cached.duration == pytest.approx(42.0)
    db.close()
