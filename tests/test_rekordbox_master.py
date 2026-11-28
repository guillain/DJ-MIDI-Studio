"""rekordbox's own library (master.db), read-only from a copy.

The real master.db is SQLCipher-encrypted (opened by pyrekordbox). These tests
build a plain SQLite file with the real table and column names (read from a
real rekordbox 7 master.db) and open it with sqlite3 instead.
"""

import sqlite3
import sys
from datetime import UTC, datetime

import pytest

from djmidi.library import history, rekordbox_master, workspace

_SCHEMA = """
CREATE TABLE djmdContent (ID VARCHAR, FolderPath VARCHAR, Title VARCHAR, ArtistID VARCHAR, BPM INTEGER,
    Length INTEGER, rb_local_deleted INTEGER);
CREATE TABLE djmdArtist (ID VARCHAR, Name VARCHAR, rb_local_deleted INTEGER);
CREATE TABLE djmdPlaylist (ID VARCHAR, Seq INTEGER, Name VARCHAR, Attribute INTEGER, ParentID VARCHAR,
    rb_local_deleted INTEGER);
CREATE TABLE djmdSongPlaylist (ID VARCHAR, PlaylistID VARCHAR, ContentID VARCHAR, TrackNo INTEGER,
    rb_local_deleted INTEGER, created_at DATETIME);
CREATE TABLE djmdHistory (ID VARCHAR, Seq INTEGER, Name VARCHAR, Attribute INTEGER, ParentID VARCHAR,
    DateCreated VARCHAR, rb_local_deleted INTEGER);
CREATE TABLE djmdSongHistory (ID VARCHAR, HistoryID VARCHAR, ContentID VARCHAR, TrackNo INTEGER,
    rb_local_deleted INTEGER, created_at DATETIME);
"""


def _make_master(path):
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    con.executemany(
        "INSERT INTO djmdContent VALUES (?,?,?,?,?,?,?)",
        [
            ("1", "/Music/a.mp3", "Alpha", "10", 17400, 300, 0),
            ("2", "/Music/b.mp3", "Bravo", None, 0, 0, 0),
            ("3", "/Music/gone.mp3", "Gone", None, 0, 0, 1),  # deleted in rekordbox
        ],
    )
    con.execute("INSERT INTO djmdArtist VALUES ('10', 'Artist A', 0)")
    con.executemany(
        "INSERT INTO djmdPlaylist VALUES (?,?,?,?,?,?)",
        [
            ("100", 1, "Dub", 1, "root", 0),  # folder
            ("101", 2, "Warm up", 0, "100", 0),
            ("102", 3, "Peak", 0, "root", 0),
            ("103", 4, "Smart", 4, "root", 0),  # rules, not tracks
        ],
    )
    con.executemany(
        "INSERT INTO djmdSongPlaylist VALUES (?,?,?,?,?,?)",
        [
            ("s1", "101", "2", 2, 0, None),
            ("s2", "101", "1", 1, 0, None),
            ("s3", "102", "3", 1, 0, None),
            ("s4", "103", "1", 1, 0, None),
        ],
    )
    con.executemany(
        "INSERT INTO djmdHistory VALUES (?,?,?,?,?,?,?)",
        [("200", 1, "2026", 1, "root", "2026-01-17", 0), ("201", 2, "2026-01-17", 0, "200", "2026-01-17", 0)],
    )
    con.executemany(
        "INSERT INTO djmdSongHistory VALUES (?,?,?,?,?,?)",
        [
            ("h1", "201", "1", 1, 0, "2026-01-17 20:37:24.538 +00:00"),
            ("h2", "201", "2", 2, 0, "2026-01-17 20:41:30 +00:00"),
        ],
    )
    con.commit()
    con.close()


def _sqlite(path):
    con = sqlite3.connect(path)
    return con, con.close


@pytest.fixture
def master(tmp_path):
    path = tmp_path / "rekordbox" / "master.db"
    path.parent.mkdir()
    _make_master(path)
    return path


def test_reads_tracks_playlists_and_history(master):
    library = rekordbox_master.read_library(master, opener=_sqlite)
    assert set(library.tracks) == {"1", "2"}
    alpha = library.tracks["1"]
    assert (alpha.artist, alpha.bpm, alpha.duration) == ("Artist A", 174.0, 300.0)  # BPM in hundredths
    assert library.tracks["2"].bpm is None
    # Folders and smart playlists hold no tracks; a nested playlist keeps its folder.
    assert library.playlists == {"Dub / Warm up": ["/Music/a.mp3", "/Music/b.mp3"], "Peak": []}
    [day] = library.histories
    assert day.name == "2026-01-17"
    assert [track for track, _at in day.entries] == ["1", "2"]
    assert day.entries[0][1] == datetime(2026, 1, 17, 20, 37, 24, 538000, tzinfo=UTC)


def test_the_djs_file_is_never_opened(master, tmp_path):
    before = (master.read_bytes(), master.stat().st_mtime_ns)
    (master.parent / "master.db-wal").write_bytes(b"wal")
    opened = []

    def opener(copy):
        opened.append(copy)
        assert copy != master and (copy.parent / "master.db-wal").read_bytes() == b"wal"
        return _sqlite(copy)

    rekordbox_master.read_library(master, opener=opener)
    assert (master.read_bytes(), master.stat().st_mtime_ns) == before
    assert not opened[0].exists()  # the copy is gone


def test_missing_pyrekordbox_and_unreadable_files(master, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pyrekordbox.masterdb", None)
    with pytest.raises(rekordbox_master.MasterDbUnavailable):
        rekordbox_master.read_library(master)
    with pytest.raises(rekordbox_master.MasterDbError):
        rekordbox_master.read_library(tmp_path / "nothing.db")
    bad = tmp_path / "bad" / "master.db"
    bad.parent.mkdir()
    bad.write_bytes(b"not sqlite")
    with pytest.raises(rekordbox_master.MasterDbError):
        rekordbox_master.read_library(bad, opener=_sqlite)


def test_parse_time():
    assert rekordbox_master.parse_time("2026-01-17 20:41:30") == datetime(2026, 1, 17, 20, 41, 30, tzinfo=UTC)
    assert rekordbox_master.parse_time("nonsense") is None
    assert rekordbox_master.parse_time(None) is None


def test_import_and_history_use_master_db(master, monkeypatch, tmp_path):
    monkeypatch.setattr(rekordbox_master, "_open_with_pyrekordbox", _sqlite)
    assert workspace.read_rekordbox_any(master) == {"Dub / Warm up": ["/Music/a.mp3", "/Music/b.mp3"], "Peak": []}
    assert history.detect_source(master.parent) == history.SOURCE_REKORDBOX
    [session] = history.read_history({history.SOURCE_REKORDBOX: master.parent})
    assert [e.title for e in session.entries] == ["Alpha", "Bravo"]
    assert session.started_at == datetime(2026, 1, 17, 20, 37, 24, 538000, tzinfo=UTC)


def test_rekordbox_on_this_computer_is_found(tmp_path, monkeypatch):
    home = tmp_path / "dj-home"
    monkeypatch.setenv("DJMIDI_DJ_HOME", str(home))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert history.SOURCE_REKORDBOX not in history.default_history_dirs()
    master = home / "Library" / "Pioneer" / "rekordbox" / "master.db"
    master.parent.mkdir(parents=True)
    _make_master(master)
    assert history.default_history_dirs()[history.SOURCE_REKORDBOX] == master.parent


def test_the_library_view_explains_a_missing_component():
    from djmidi.gui.music_library_view import MusicLibraryView

    view = MusicLibraryView()
    text = view._read_error_text(rekordbox_master.MasterDbUnavailable("no module"))
    assert "rekordbox XML" in text
    assert view._read_error_text(ValueError("x")) == "x"


# OneLibrary (exportLibrary.db): the column names of a real export written by rekordbox 7.
_ONELIBRARY_SCHEMA = """
CREATE TABLE content (content_id INTEGER, title VARCHAR, bpmx100 INTEGER, length INTEGER,
    artist_id_artist INTEGER, path VARCHAR);
CREATE TABLE artist (artist_id INTEGER, name VARCHAR, nameForSearch VARCHAR);
CREATE TABLE playlist (playlist_id INTEGER, sequenceNo INTEGER, name VARCHAR, image_id INTEGER,
    attribute INTEGER, playlist_id_parent INTEGER);
CREATE TABLE playlist_content (playlist_id INTEGER, content_id INTEGER, sequenceNo INTEGER);
CREATE TABLE history (history_id INTEGER, sequenceNo INTEGER, name VARCHAR, attribute INTEGER,
    history_id_parent INTEGER);
CREATE TABLE history_content (history_id INTEGER, content_id INTEGER, sequenceNo INTEGER);
"""


@pytest.fixture
def usb(tmp_path):
    root = tmp_path / "USB"
    path = root / "PIONEER" / "rekordbox" / "exportLibrary.db"
    path.parent.mkdir(parents=True)
    con = sqlite3.connect(path)
    con.executescript(_ONELIBRARY_SCHEMA)
    con.executemany(
        "INSERT INTO content VALUES (?,?,?,?,?,?)",
        [(1, "Alpha", 17725, 368, 7, "/Contents/a.mp3"), (2, "Bravo", 0, 0, None, "/Contents/b.mp3")],
    )
    con.execute("INSERT INTO artist VALUES (7, 'Artist A', 'artist a')")
    con.executemany(
        "INSERT INTO playlist VALUES (?,?,?,?,?,?)",
        [(10, 1, "Tek", 0, 1, 0), (11, 1, "Night", 0, 0, 10), (12, 2, "Solo", 0, 0, 0)],
    )
    con.executemany("INSERT INTO playlist_content VALUES (?,?,?)", [(11, 2, 2), (11, 1, 1), (12, 2, 1)])
    con.executemany("INSERT INTO history VALUES (?,?,?,?,?)", [(20, 1, "HISTORY 001", 0, 0)])
    con.executemany("INSERT INTO history_content VALUES (?,?,?)", [(20, 1, 1)])
    con.commit()
    con.close()
    return root


def test_onelibrary_export_is_read_from_a_copy(usb, monkeypatch):
    monkeypatch.setattr(rekordbox_master, "_open_with_pyrekordbox", _sqlite)
    export = usb / "PIONEER" / "rekordbox" / "exportLibrary.db"
    before = export.read_bytes()
    library = rekordbox_master.read_library(export)
    assert library.tracks["1"].bpm == 177.25 and library.tracks["1"].artist == "Artist A"
    # Paths are relative to the stick; the import puts them under it.
    assert workspace.read_rekordbox_any(export) == {
        "Tek / Night": [str(usb / "Contents" / "a.mp3"), str(usb / "Contents" / "b.mp3")],
        "Solo": [str(usb / "Contents" / "b.mp3")],
    }
    assert export.read_bytes() == before
    # A stick with only a OneLibrary export: its history, without times.
    assert history.detect_source(usb) == history.SOURCE_REKORDBOX
    [session] = history.read_history({history.SOURCE_REKORDBOX: usb})
    assert session.name == "HISTORY 001"
    assert [(e.path, e.played_at) for e in session.entries] == [(str(usb / "Contents" / "a.mp3"), None)]
