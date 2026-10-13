"""Issue #208: discarding duplicate copies. Only tmp_path files, and a fake
`trash` that moves files into another tmp_path folder -- never the real
system Trash or real music."""

from __future__ import annotations

from pathlib import Path

import pytest

from djmidi.library import discard
from djmidi.library.db import LibraryDB
from djmidi.library.duplicates import (
    TIER_EXACT,
    TIER_METADATA,
    TIER_VERSIONS,
    DuplicateGroup,
)


def _group(tier: str, *paths: Path) -> DuplicateGroup:
    return DuplicateGroup(tier=tier, key="k", paths=tuple(str(p) for p in paths))


@pytest.fixture
def setup(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    files = {}
    for name in ("a.mp3", "a copy.mp3", "b.mp3", "b2.mp3"):
        path = music / name
        path.write_bytes(b"audio " + name.encode())
        files[name] = path
    db = LibraryDB(":memory:")
    root = db.add_root(music)
    for path in files.values():
        stat = path.stat()
        db.upsert_track(root.id, path, stat.st_size, stat.st_mtime)
    db.commit()
    bin_dir = tmp_path / "Trash"
    bin_dir.mkdir()
    trashed: list[str] = []

    def fake_trash(path: str) -> bool:
        trashed.append(path)
        Path(path).rename(bin_dir / Path(path).name)
        return True

    yield db, files, fake_trash, trashed, bin_dir
    db.close()


def test_plan_pairs_each_copy_with_a_kept_one(setup):
    _db, files, *_ = setup
    groups = [
        _group(TIER_METADATA, files["a.mp3"], files["a copy.mp3"], files["b.mp3"]),
        _group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"]),
    ]
    plan = discard.plan_discard(groups, [str(files["a.mp3"]), str(files["a.mp3"])])
    assert plan.ok
    assert plan.refused == ()
    # Exact groups are preferred for the kept copy, whatever the list order.
    assert plan.discards == ((str(files["a.mp3"]), str(files["a copy.mp3"])),)


def test_plan_refuses_a_group_that_keeps_nothing(setup):
    _db, files, *_ = setup
    exact = _group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"])
    other = _group(TIER_EXACT, files["b.mp3"], files["b2.mp3"])
    plan = discard.plan_discard([exact, other], [str(files["a.mp3"]), str(files["a copy.mp3"]), str(files["b.mp3"])])
    assert plan.refused == (exact,)
    assert not plan.ok


def test_plan_ignores_version_suggestions(setup):
    """Issue #257: another version of a song is never a kept copy, and a
    versions group never refuses or enables a discard on its own."""
    _db, files, *_ = setup
    versions = _group(TIER_VERSIONS, files["a.mp3"], files["b.mp3"])
    plan = discard.plan_discard([versions], [str(files["a.mp3"]), str(files["b.mp3"])])
    assert plan.discards == ()
    assert plan.refused == ()
    assert not plan.ok
    exact = _group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"])
    plan = discard.plan_discard([versions, exact], [str(files["a.mp3"])])
    assert plan.discards == ((str(files["a.mp3"]), str(files["a copy.mp3"])),)


def test_plan_with_nothing_ticked_is_not_ok(setup):
    _db, files, *_ = setup
    plan = discard.plan_discard([_group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"])], [])
    assert plan.discards == () and not plan.ok


def test_move_to_trash_moves_and_flags_missing(setup):
    db, files, fake_trash, trashed, bin_dir = setup
    plan = discard.plan_discard([_group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"])], [str(files["a copy.mp3"])])
    result = discard.move_to_trash(db, plan, fake_trash)
    assert result.moved == [(str(files["a copy.mp3"]), str(files["a.mp3"]))]
    assert result.failed == []
    assert trashed == [str(files["a copy.mp3"])]
    assert (bin_dir / "a copy.mp3").is_file()
    assert files["a.mp3"].is_file()
    assert db.get_track_by_path(files["a copy.mp3"]).missing is True
    assert db.get_track_by_path(files["a.mp3"]).missing is False


def test_move_to_trash_refused_plan_moves_nothing(setup):
    db, files, fake_trash, trashed, _bin = setup
    plan = discard.plan_discard(
        [_group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"])], [str(files["a.mp3"]), str(files["a copy.mp3"])]
    )
    result = discard.move_to_trash(db, plan, fake_trash)
    assert result.moved == [] and trashed == []
    assert all(path.is_file() for path in files.values())


def test_move_to_trash_reports_failures_and_continues(setup):
    db, files, fake_trash, _trashed, _bin = setup
    groups = [
        _group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"]),
        _group(TIER_EXACT, files["b.mp3"], files["b2.mp3"]),
    ]
    plan = discard.plan_discard(groups, [str(files["a copy.mp3"]), str(files["b2.mp3"])])

    def flaky(path: str) -> bool:
        if path.endswith("a copy.mp3"):
            raise OSError("permission denied")
        return fake_trash(path)

    result = discard.move_to_trash(db, plan, flaky)
    assert result.failed == [(str(files["a copy.mp3"]), "permission denied")]
    assert [path for path, _ in result.moved] == [str(files["b2.mp3"])]
    assert db.get_track_by_path(files["a copy.mp3"]).missing is False

    # A trash that says no, a vanished file, a vanished kept copy.
    plan = discard.plan_discard(groups, [str(files["a copy.mp3"])])
    assert discard.move_to_trash(db, plan, lambda _p: False).failed[0][1] == "could not move it to the Trash"
    files["a.mp3"].unlink()
    assert "kept copy is gone" in discard.move_to_trash(db, plan, fake_trash).failed[0][1]
    plan = discard.plan_discard(groups, [str(files["b2.mp3"])])
    assert discard.move_to_trash(db, plan, fake_trash).failed == [(str(files["b2.mp3"]), "file not found")]


def test_repoint_playlists_to_the_kept_copy(setup):
    db, files, fake_trash, _trashed, _bin = setup
    copy, kept = str(files["a copy.mp3"]), str(files["a.mp3"])
    first = db.create_playlist("Set 1", [str(files["b.mp3"]), copy])
    db.create_playlist("Other", [str(files["b2.mp3"])])
    plan = discard.plan_discard([_group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"])], [copy])
    result = discard.move_to_trash(db, plan, fake_trash)

    assert discard.playlists_referencing(db, result.moved) == {copy: ["Set 1"]}
    assert discard.repoint_playlists(db, result.moved) == 1
    assert db.playlist_paths(first) == [str(files["b.mp3"]), kept]
    # relink_tracks folds the stale row into the kept one.
    assert db.get_track_by_path(copy) is None
    assert discard.playlists_referencing(db, result.moved) == {}
    # Nothing left to repoint the second time.
    assert discard.repoint_playlists(db, result.moved) == 0


def test_repoint_does_not_list_the_kept_copy_twice(setup):
    db, files, fake_trash, _trashed, _bin = setup
    copy, kept = str(files["a copy.mp3"]), str(files["a.mp3"])
    b, b2 = str(files["b.mp3"]), str(files["b2.mp3"])
    copy_first = db.create_playlist("Copy first", [b, copy, b2, kept])
    kept_first = db.create_playlist("Kept first", [kept, b, copy])
    only_copy = db.create_playlist("Only copy", [copy, b])
    plan = discard.plan_discard([_group(TIER_EXACT, files["a.mp3"], files["a copy.mp3"])], [copy])
    result = discard.move_to_trash(db, plan, fake_trash)

    assert discard.repoint_playlists(db, result.moved) == 1
    # The first occurrence keeps its position, the other entry is dropped.
    assert db.playlist_paths(copy_first) == [b, kept, b2]
    assert db.playlist_paths(kept_first) == [kept, b]
    assert db.playlist_paths(only_copy) == [kept, b]


def test_mark_paths_missing_never_deletes(setup):
    db, files, *_ = setup
    assert db.mark_paths_missing([str(files["b.mp3"]), "/nowhere.mp3"]) == 1
    assert db.mark_paths_missing([str(files["b.mp3"])]) == 0
    assert db.get_track_by_path(files["b.mp3"]).missing is True
