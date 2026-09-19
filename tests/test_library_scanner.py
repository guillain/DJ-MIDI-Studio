import os

from djmidi.library import LibraryDB, iter_audio_files, scan_root


def _touch(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_iter_audio_files_filters_extensions_and_junk(tmp_path):
    _touch(tmp_path / "track.mp3")
    _touch(tmp_path / "track.wav")
    _touch(tmp_path / "notes.txt")
    _touch(tmp_path / "._track.mp3")  # AppleDouble sidecar
    _touch(tmp_path / ".DS_Store")
    _touch(tmp_path / ".Trash" / "hidden.mp3")  # hidden directory
    _touch(tmp_path / "Sub Folder" / "nested.flac")

    found = {p.name for p in iter_audio_files(tmp_path)}

    assert found == {"track.mp3", "track.wav", "nested.flac"}


def test_scan_root_adds_new_tracks(tmp_path):
    _touch(tmp_path / "a.mp3")
    _touch(tmp_path / "b.flac")
    db = LibraryDB()

    result = scan_root(tmp_path, db)

    assert result.added == 2
    assert result.updated == 0
    assert result.unchanged == 0
    assert len(db.list_tracks()) == 2


def test_scan_root_is_incremental(tmp_path):
    a = _touch(tmp_path / "a.mp3")
    db = LibraryDB()
    scan_root(tmp_path, db)

    result = scan_root(tmp_path, db)
    assert result.added == 0
    assert result.unchanged == 1
    assert result.updated == 0

    os.utime(a, (a.stat().st_atime, a.stat().st_mtime + 100))
    result = scan_root(tmp_path, db)
    assert result.updated == 1
    assert result.unchanged == 0


def test_scan_root_flags_deleted_files_as_missing_without_removing_them(tmp_path):
    a = _touch(tmp_path / "a.mp3")
    _touch(tmp_path / "b.mp3")
    db = LibraryDB()
    scan_root(tmp_path, db)

    a.unlink()
    result = scan_root(tmp_path, db)

    assert result.missing == 1
    tracks = {t.path: t.missing for t in db.list_tracks()}
    assert tracks[str(a)] is True
    assert len(tracks) == 2  # the missing track's history is kept, not deleted


def test_scan_root_reports_progress(tmp_path):
    _touch(tmp_path / "a.mp3")
    _touch(tmp_path / "b.mp3")
    db = LibraryDB()
    seen = []

    scan_root(tmp_path, db, progress_callback=seen.append)

    assert seen == [1, 2]
