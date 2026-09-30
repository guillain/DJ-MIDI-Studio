from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TBPM, TCON, TIT2, TKEY

from djmidi import taxonomy
from djmidi.library import workspace
from djmidi.library.db import LibraryDB, StoredCategory
from djmidi.library.metadata import TrackMetadata
from djmidi.library.scanner import iter_scan_root, scan_root
from djmidi.library.serato_library import parse_crate, write_crate_file


def _mp3(path: Path, *, title: str | None = None, genre: str | None = None, bpm: str | None = None,
         key: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((frame + b"\x00" * (417 - len(frame))) * 20)
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=[title]))
    if genre:
        tags.add(TCON(encoding=3, text=[genre]))
    if bpm:
        tags.add(TBPM(encoding=3, text=[bpm]))
    if key:
        tags.add(TKEY(encoding=3, text=[key]))
    tags.save(path)
    return path


def test_iter_scan_root_yields_progress_and_returns_result(tmp_path):
    _mp3(tmp_path / "a.mp3")
    _mp3(tmp_path / "b.mp3")
    with LibraryDB() as db:
        steps = iter_scan_root(tmp_path, db)
        counts = []
        while True:
            try:
                counts.append(next(steps))
            except StopIteration as done:
                result = done.value
                break
        assert counts == [1, 2]
        assert result.added == 2
        # The blocking wrapper still behaves the same on a rescan.
        assert scan_root(tmp_path, db).unchanged == 2


def test_metadata_cache_roundtrip_and_staleness(tmp_path):
    track = _mp3(tmp_path / "a.mp3", title="One")
    with LibraryDB() as db:
        scan_root(tmp_path, db)
        assert [r.path for r in db.tracks_needing_metadata()] == [str(track)]
        assert list(workspace.iter_refresh_metadata(db)) == [1]
        assert db.tracks_needing_metadata() == []
        record = db.get_track_by_path(track)
        _mtime, cached = db.get_cached_metadata(record.id)
        assert cached.title == "One"
        # A changed mtime (e.g. tags edited in Serato) makes the cache stale.
        db.upsert_track(record.root_id, str(track), record.size, record.mtime + 10)
        assert [r.id for r in db.tracks_needing_metadata()] == [record.id]


def test_refresh_survives_unreadable_file(tmp_path):
    (tmp_path / "broken.mp3").write_bytes(b"not audio at all")
    with LibraryDB() as db:
        scan_root(tmp_path, db)
        assert list(workspace.iter_refresh_metadata(db)) == [1]
        [(_record, metadata)] = db.list_tracks_with_metadata()
        assert metadata == TrackMetadata()


def test_consolidate_resolves_camelot_and_folder_category(tmp_path):
    _mp3(tmp_path / "Tek" / "PsyTrance" / "x.mp3", title="X", genre="House", bpm="145", key="Am")
    with LibraryDB() as db:
        scan_root(tmp_path, db)
        list(workspace.iter_refresh_metadata(db))
        [row] = workspace.consolidate(db)
    assert row.title == "X"
    assert row.bpm == 145
    assert row.camelot_key == "8A"
    # The hand-curated folder beats the unreliable TCON tag (issue #127).
    assert row.category == "Tek%%PsyTrance"
    assert row.category_suggestion is None


def test_consolidate_keeps_fuzzy_match_as_suggestion_only(tmp_path):
    _mp3(tmp_path / "misc" / "y.mp3", genre="Psytrancee")
    with LibraryDB() as db:
        scan_root(tmp_path, db)
        list(workspace.iter_refresh_metadata(db))
        [row] = workspace.consolidate(db)
    assert row.category is None
    assert row.category_suggestion == "Tek%%PsyTrance"


def test_consolidate_uses_imported_serato_crate_as_hint(tmp_path):
    track = _mp3(tmp_path / "loose" / "z.mp3", genre="Other")
    with LibraryDB() as db:
        scan_root(tmp_path, db)
        list(workspace.iter_refresh_metadata(db))
        db.create_playlist("Tek%%HardTek%%Friday", [str(track)], source=workspace.SOURCE_SERATO)
        [row] = workspace.consolidate(db)
    assert row.category == "Tek%%HardTek"


def test_folder_hint():
    assert workspace.folder_hint("/music/Tek/Psy/a.mp3", "/music") == "Tek/Psy"
    assert workspace.folder_hint("/music/a.mp3", "/music") is None
    assert workspace.folder_hint("/elsewhere/Psy/a.mp3", "/music") == "Psy"


def test_playlist_crud():
    with LibraryDB() as db:
        playlist_id = db.create_playlist("Set", ["/a.mp3", "/b.mp3"])
        assert db.playlist_paths(playlist_id) == ["/a.mp3", "/b.mp3"]
        db.set_playlist_paths(playlist_id, ["/b.mp3"])
        db.rename_playlist(playlist_id, "Renamed")
        [record] = db.list_playlists()
        assert (record.name, record.source, record.track_count) == ("Renamed", "manual", 1)
        db.delete_playlist(playlist_id)
        assert db.list_playlists() == []


def test_category_edits_persist_and_replay():
    with LibraryDB() as db:
        workspace.create_category(db, "Dub", "Steppa", ["Steppas"])
        workspace.add_category_alias(db, "Dub%%Steppa", "Stepper")
        renamed = workspace.rename_category(db, "Dub%%Steppa", "Steppers")
        assert renamed.aliases == {"Steppas", "Stepper", "Steppa"}
        workspace.merge_categories(db, "Tek%%HardTek", "Tek%%BarBass")
        workspace.delete_category(db, "Tek%%FrenchCore")
        saved, removed = db.category_overrides()

        # Simulate a restart: built-ins back, user edits gone...
        taxonomy.unregister("Dub%%Steppers")
        taxonomy.register(taxonomy.Category("Tek", "BarBass"), replace=True)
        taxonomy.register(taxonomy.Category("Tek", "FrenchCore"), replace=True)
        taxonomy.register(taxonomy.Category("Tek", "HardTek"), replace=True)
        # ...then replayed from the DB.
        workspace.load_taxonomy_overrides(db)

    names = {c.canonical for c in taxonomy.all_categories()}
    assert "Dub%%Steppers" in names
    assert "Dub%%Steppa" not in names
    assert "Tek%%BarBass" not in names
    assert "Tek%%FrenchCore" not in names
    assert "BarBass" in taxonomy.get_category("Tek%%HardTek").aliases
    assert {s.canonical for s in saved} == {"Dub%%Steppers", "Tek%%HardTek"}
    assert set(removed) == {"Dub%%Steppa", "Tek%%BarBass", "Tek%%FrenchCore"}


def test_category_validation():
    with LibraryDB() as db:
        with pytest.raises(ValueError):
            workspace.create_category(db, "", "x")
        with pytest.raises(ValueError):
            workspace.merge_categories(db, "Tek%%HardTek", "Tek%%HardTek")
        with pytest.raises(ValueError):
            workspace.delete_category(db, "Nope%%Nope")


def test_stored_category_canonical():
    assert StoredCategory("A", "B").canonical == "A%%B"


def _row(path, category=None, bpm=None, key=None, missing=False):
    return workspace.LibraryRow(
        track_id=0, path=path, missing=missing, metadata=TrackMetadata(bpm=bpm),
        camelot_key=key, category=category,
    )


def test_generate_playlist_default_order_and_seeded():
    rows = [
        _row("/c.mp3", "Tek%%Tribe", 175, "9A"),
        _row("/a.mp3", "Dub%%Roots", 80, "8A"),
        _row("/b.mp3", "Tek%%Tribe", 172, "8A"),
        _row("/gone.mp3", "Tek%%Tribe", 172, "8A", missing=True),
    ]
    assert workspace.generate_playlist(rows) == ["/a.mp3", "/b.mp3", "/c.mp3"]
    assert workspace.generate_playlist(rows, seed_path="/b.mp3") == ["/b.mp3", "/c.mp3"]
    with pytest.raises(ValueError):
        workspace.generate_playlist(rows, seed_path="/gone.mp3")


def test_volume_root():
    assert workspace.volume_root("/Volumes/DJ/Music/a.mp3") == Path("/Volumes/DJ")
    assert workspace.volume_root("/Users/me/Music/a.mp3") == Path("/")


def test_serato_crate_export_import_roundtrip(tmp_path):
    crate = tmp_path / "Set.crate"
    track = tmp_path / "music" / "a.mp3"
    workspace.export_serato_crate(crate, [str(track)])
    # Stored relative to the volume root, like Serato's own crates.
    assert parse_crate(crate) == [str(track.resolve().relative_to("/"))]
    assert workspace.read_serato_crate(crate) == [str(Path("/") / track.resolve().relative_to("/"))]


def test_read_serato_crate_keeps_absolute_entries(tmp_path):
    crate = tmp_path / "x.crate"
    write_crate_file(crate, ["/abs/a.mp3"])
    assert workspace.read_serato_crate(crate) == ["/abs/a.mp3"]


def test_traktor_key_to_path(tmp_path):
    assert workspace.traktor_key_to_path("Nowhere Drive/:Users/:me/:a.mp3") == "/Users/me/a.mp3"
    assert workspace.traktor_key_to_path("plain") == "plain"


def test_read_traktor_playlists(tmp_path):
    nml = tmp_path / "collection.nml"
    nml.write_text(
        '<?xml version="1.0"?><NML VERSION="20"><COLLECTION ENTRIES="0"></COLLECTION>'
        '<PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="1">'
        '<NODE TYPE="PLAYLIST" NAME="Set"><PLAYLIST ENTRIES="1" TYPE="LIST">'
        '<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="NoSuchVolume/:m/:a.mp3"/></ENTRY>'
        "</PLAYLIST></NODE></SUBNODES></NODE></PLAYLISTS></NML>",
        encoding="utf-8",
    )
    assert workspace.read_traktor_playlists(nml) == {"Set": ["/m/a.mp3"]}


def test_read_rekordbox_playlists_maps_device_root(tmp_path, monkeypatch):
    from djmidi.library.rekordbox_library import RekordboxPlaylist, RekordboxTrack

    track = RekordboxTrack(
        id=7, title="t", artist="", album="", genre="", label="", key="", bpm=None,
        duration_seconds=0, year=0, rating=0, comment="", file_path="/Contents/a.mp3", filename="a.mp3",
    )
    monkeypatch.setattr(workspace, "parse_export", lambda _p: [track])
    monkeypatch.setattr(
        workspace,
        "parse_rekordbox_playlists",
        lambda _p: [
            RekordboxPlaylist(id=1, name="Folder", parent_id=0, is_folder=True),
            RekordboxPlaylist(id=2, name="Set", parent_id=1, is_folder=False, track_ids=[7, 99]),
        ],
    )
    pdb = tmp_path / "USB" / "PIONEER" / "rekordbox" / "export.pdb"
    assert workspace.read_rekordbox_playlists(pdb) == {"Set": [str(tmp_path / "USB" / "Contents" / "a.mp3")]}


def test_refresh_track_metadata_after_write(tmp_path):
    from djmidi.library.metadata import write_metadata

    track = _mp3(tmp_path / "a.mp3", title="Old")
    with LibraryDB() as db:
        scan_root(tmp_path, db)
        list(workspace.iter_refresh_metadata(db))
        write_metadata(track, title="New")
        workspace.refresh_track_metadata(db, str(track))
        [row] = workspace.consolidate(db)
    assert row.title == "New"
