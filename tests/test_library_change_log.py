"""Issue #261: persistent change history. Only tmp_path files and a
`:memory:`/tmp_path index -- never real music or the real Trash."""

from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TBPM, TCON, TIT2

from djmidi.library import change_log, discard
from djmidi.library.db import ChangeItem, LibraryDB
from djmidi.library.duplicates import TIER_EXACT, DuplicateGroup
from djmidi.library.metadata import read_metadata, write_metadata


def _mp3(path: Path, **tags: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((frame + b"\x00" * (417 - len(frame))) * 20)
    id3 = ID3()
    frames = {"title": TIT2, "genre": TCON, "bpm": TBPM}
    for name, value in tags.items():
        id3.add(frames[name](encoding=3, text=[value]))
    id3.save(path)
    return path


@pytest.fixture
def db():
    database = LibraryDB(":memory:")
    yield database
    database.close()


def _clock(start: float = 1000.0):
    ticks = iter(range(10_000))
    return lambda: start + next(ticks)


def test_change_log_survives_reopening_the_index(tmp_path):
    path = tmp_path / "library.sqlite3"
    with LibraryDB(path) as database:
        change_id = change_log.record_tag_changes(database, {"/x/a.mp3": ({"bpm": 120.0}, {"bpm": 128.0})})
    with LibraryDB(path) as database:
        [entry] = database.list_changes()
        assert entry.id == change_id and entry.kind == change_log.KIND_TAGS and entry.item_count == 1
        assert entry.summary == "Edit bpm of 1 track(s)"
        change = database.get_change(change_id)
        assert change.items == [ChangeItem("/x/a.mp3", {"bpm": 120.0}, {"bpm": 128.0})]


def test_record_nothing_and_pruning(db):
    assert change_log.record_tag_changes(db, {}) is None
    clock = _clock()
    for index in range(5):
        change_log.record_change(db, "tags", f"#{index}", [ChangeItem("/a", {}, {})], now=clock)
    assert db.prune_changes(3) == 2
    assert [c.summary for c in db.list_changes()] == ["#4", "#3", "#2"]
    assert [c.summary for c in db.list_changes(limit=1)] == ["#4"]


def test_record_never_raises(db, caplog):
    db.close()
    assert change_log.record_tag_changes(db, {"/a": ({"bpm": 1.0}, {"bpm": 2.0})}) is None
    assert "Could not record" in caplog.text


def test_revert_tags_writes_old_values_and_logs_the_revert(db, tmp_path):
    track = _mp3(tmp_path / "a.mp3", title="Alpha", genre="Techno", bpm="120")
    write_metadata(str(track), genre="Tribe", bpm=128.0)
    clock = _clock()
    change_id = change_log.record_tag_changes(
        db, {str(track): ({"genre": "Techno", "bpm": 120.0}, {"genre": "Tribe", "bpm": 128.0})}, now=clock
    )
    result = change_log.revert_change(db, change_id, now=clock)
    assert result.reverted == [str(track)] and result.complete
    metadata = read_metadata(str(track))
    assert metadata.genre == "Techno" and metadata.bpm == 120.0 and metadata.title == "Alpha"
    assert db.get_change(change_id).reverted_at is not None
    revert = db.get_change(result.log_id)
    assert revert.summary.startswith(f"Revert #{change_id}:")
    assert revert.items[0].after == {"genre": "Techno", "bpm": 120.0}
    with pytest.raises(ValueError, match="already reverted"):
        change_log.revert_change(db, change_id)
    # The revert is itself revertible.
    change_log.revert_change(db, result.log_id)
    assert read_metadata(str(track)).genre == "Tribe"


def test_revert_tags_leaves_a_file_changed_since_alone(db, tmp_path):
    edited = _mp3(tmp_path / "edited.mp3", genre="Psy")
    untouched = _mp3(tmp_path / "ok.mp3", genre="Tribe")
    already = _mp3(tmp_path / "already.mp3", genre="Techno")
    change_id = change_log.record_tag_changes(
        db,
        {
            str(edited): ({"genre": "Techno"}, {"genre": "Tribe"}),
            str(untouched): ({"genre": "Techno"}, {"genre": "Tribe"}),
            str(already): ({"genre": "Techno"}, {"genre": "Tribe"}),
            str(tmp_path / "gone.mp3"): ({"genre": "Techno"}, {"genre": "Tribe"}),
        },
    )
    result = change_log.revert_change(db, change_id)
    assert result.reverted == [str(untouched)]
    assert result.already == [str(already)]
    assert dict(result.failed) == {
        str(edited): "genre changed since",
        str(tmp_path / "gone.mp3"): "file not found",
    }
    assert read_metadata(str(edited)).genre == "Psy"
    assert read_metadata(str(untouched)).genre == "Techno"
    # Not complete: stays open so it can be retried.
    assert db.get_change(change_id).reverted_at is None


def test_revert_uses_injected_io(db):
    writes = []
    context = change_log.RevertContext(
        writer=lambda path, **values: writes.append((path, values)),
        reader=lambda path: type("M", (), {"bpm": 128.0})(),
    )
    change_id = change_log.record_tag_changes(db, {__file__: ({"bpm": None}, {"bpm": 128.0})})
    change_log.revert_change(db, change_id, context)
    assert writes == [(__file__, {"bpm": None})]


def test_trash_is_logged_and_put_back(db, tmp_path):
    music = tmp_path / "music"
    keep = _mp3(music / "a.mp3")
    copy = music / "sub" / "a copy.mp3"
    copy.parent.mkdir()
    copy.write_bytes(keep.read_bytes())
    root = db.add_root(music)
    for path in (keep, copy):
        db.upsert_track(root.id, path, path.stat().st_size, path.stat().st_mtime)
    db.commit()
    playlist = db.create_playlist("Friday", [str(copy)])
    bin_dir = tmp_path / "Trash"
    bin_dir.mkdir()

    def fake_trash(path: str) -> str:
        target = bin_dir / Path(path).name
        Path(path).rename(target)
        return str(target)

    plan = discard.plan_discard([DuplicateGroup(TIER_EXACT, "k", (str(keep), str(copy)))], [str(copy)])
    result = discard.move_to_trash(db, plan, fake_trash)
    assert result.trash_paths == {str(copy): str(bin_dir / "a copy.mp3")}
    change_id = change_log.record_trash(db, result.moved, result.trash_paths)
    discard.repoint_playlists(db, result.moved)
    assert db.get_track_by_path(copy) is None

    revert = change_log.revert_change(db, change_id)
    assert revert.reverted == [str(copy)] and copy.is_file() and not (bin_dir / "a copy.mp3").exists()
    assert db.get_track_by_path(copy).missing is False
    # Repointed playlists stay on the kept copy.
    assert db.playlist_paths(playlist) == [str(keep)]
    assert db.get_change(revert.log_id).kind == change_log.KIND_RESTORE
    assert not change_log.is_revertible(db.get_change(revert.log_id))


def test_trash_revert_refuses_unknown_location_or_occupied_path(db, tmp_path):
    occupied = _mp3(tmp_path / "a.mp3")
    in_bin = _mp3(tmp_path / "bin" / "a.mp3")
    change_id = change_log.record_trash(
        db, [(str(occupied), "/k"), ("/nowhere/b.mp3", "/k")], {str(occupied): str(in_bin)}
    )
    result = change_log.revert_change(db, change_id)
    reasons = dict(result.failed)
    assert reasons[str(occupied)] == "a file already exists at its original location"
    assert "unknown" in reasons["/nowhere/b.mp3"]
    assert in_bin.is_file()


def test_rename_revert_moves_back_and_relinks(db, tmp_path):
    music = tmp_path / "music"
    old = _mp3(music / "old.mp3")
    new = music / "new name.mp3"
    old.rename(new)
    root = db.add_root(music)
    db.upsert_track(root.id, new, new.stat().st_size, new.stat().st_mtime)
    db.commit()
    playlist = db.create_playlist("P", [str(new)])
    change_id = change_log.record_renames(db, [(str(old), str(new))])
    result = change_log.revert_change(db, change_id)
    assert result.reverted == [str(old)] and old.is_file() and not new.exists()
    assert db.get_track_by_path(old) is not None and db.get_track_by_path(new) is None
    assert db.playlist_paths(playlist) == [str(old)]


def test_unknown_kinds_and_registered_reverters(db):
    change_id = change_log.record_change(db, "custom", "Custom write", [ChangeItem("/a", {}, {})])
    assert not change_log.is_revertible(db.get_change(change_id))
    with pytest.raises(ValueError, match="can't be reverted"):
        change_log.revert_change(db, change_id)
    with pytest.raises(ValueError, match="no change"):
        change_log.revert_change(db, 999)
    calls = []

    def revert_custom(_db, item, _ctx):
        calls.append(item.path)
        return ChangeItem(item.path, item.after, item.before)

    change_log.register_reverter("custom", revert_custom)
    try:
        with pytest.raises(ValueError, match="already registered"):
            change_log.register_reverter("custom", revert_custom)
        with pytest.raises(ValueError, match="already registered"):
            change_log.register_reverter(change_log.KIND_COVER, revert_custom)
        assert change_log.revert_change(db, change_id).reverted == ["/a"] and calls == ["/a"]
    finally:
        change_log._REVERTERS.pop("custom")


# --- cover art (issue #279) ----------------------------------------------

PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x02" * 40


def test_cover_state_keeps_data_only_when_asked():
    from djmidi.library.cover_art import CoverArt

    cover = CoverArt(PNG, "image/png", "front")
    full = change_log.cover_state(cover)
    light = change_log.cover_state(cover, keep_data=False)
    assert full["sha256"] == light["sha256"] and full["size"] == len(PNG) and "data" not in light
    assert change_log.cover_from_state(full) == cover
    assert change_log.cover_state(None) == {"sha256": None}
    assert change_log.cover_from_state({"sha256": None}) is None
    with pytest.raises(change_log.RevertSkipped, match="wasn't kept"):
        change_log.cover_from_state(light)


def test_cover_change_is_logged_and_reverted_on_a_real_file(db, tmp_path):
    from djmidi.library.cover_art import CoverArt, read_front_cover, write_cover_art

    track = _mp3(tmp_path / "a.mp3", title="Alpha")
    old, new = CoverArt(JPEG, "image/jpeg"), CoverArt(PNG, "image/png")
    write_cover_art(track, old)
    write_cover_art(track, new)
    clock = _clock()
    change_id = change_log.record_cover_change(db, str(track), old, new, now=clock)
    [item] = db.get_change(change_id).items
    assert db.get_change(change_id).summary == "Set cover of a.mp3"
    assert "data" in item.before and "data" not in item.after

    result = change_log.revert_change(db, change_id, now=clock)
    assert result.reverted == [str(track)] and read_front_cover(track).data == JPEG
    assert read_metadata(str(track)).title == "Alpha"
    # The revert is logged with the cover it replaced, so it can be reverted too.
    revert_entry = db.get_change(result.log_id)
    assert revert_entry.kind == change_log.KIND_COVER
    assert change_log.revert_change(db, result.log_id, now=clock).reverted == [str(track)]
    assert read_front_cover(track).data == PNG


def test_cover_revert_removes_an_added_cover_and_skips_one_changed_since(db, tmp_path):
    from djmidi.library.cover_art import CoverArt, read_front_cover, write_cover_art

    added = _mp3(tmp_path / "added.mp3")
    write_cover_art(added, CoverArt(PNG, "image/png"))
    edited = _mp3(tmp_path / "edited.mp3")
    write_cover_art(edited, CoverArt(PNG, "image/png"))
    first = change_log.record_cover_change(db, str(added), None, CoverArt(PNG, "image/png"))
    second = change_log.record_cover_change(db, str(edited), None, CoverArt(PNG, "image/png"))
    write_cover_art(edited, CoverArt(JPEG, "image/jpeg"))  # e.g. replaced in Serato

    assert change_log.revert_change(db, first).reverted == [str(added)]
    assert read_front_cover(added) is None
    result = change_log.revert_change(db, second)
    assert result.failed == [(str(edited), "its cover changed since")]
    assert read_front_cover(edited).data == JPEG
    assert db.get_change(second).reverted_at is None


def test_cover_revert_already_done_and_injected_io(db):
    from djmidi.library.cover_art import CoverArt

    writes = []
    current = {"cover": CoverArt(PNG, "image/png")}
    context = change_log.RevertContext(
        cover_reader=lambda path: current["cover"],
        cover_writer=lambda path, cover: writes.append((path, cover)),
    )
    change_id = change_log.record_cover_change(db, __file__, None, CoverArt(PNG, "image/png"), summary="S")
    assert change_log.revert_change(db, change_id, context).reverted == [__file__]
    assert writes == [(__file__, None)]
    current["cover"] = None
    again = change_log.record_cover_change(db, __file__, None, CoverArt(PNG, "image/png"))
    result = change_log.revert_change(db, again, context)
    assert result.already == [__file__] and len(writes) == 1
