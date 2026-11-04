"""Auto-organize library files into category folders (issue #406). Every
file moved here lives under pytest's tmp_path."""

from __future__ import annotations

from pathlib import Path

import pytest

from djmidi.library import organize
from djmidi.library.db import LibraryDB
from djmidi.library.organize import (
    STATUS_CONFLICT,
    STATUS_MOVE,
    STATUS_NO_CATEGORY,
    STATUS_REFUSED,
    STATUS_UNCHANGED,
    OrganizeSource,
)


def _file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    return path


@pytest.fixture
def music(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    return root


# --- paths ------------------------------------------------------------------


def test_category_folder_splits_and_sanitizes():
    assert organize.category_folder("Tek%%PsyTrance") == ("Tek", "PsyTrance")
    assert organize.category_folder("A/B%%C:D") == ("A_B", "C_D")


def test_category_folder_falls_back_to_other_for_an_empty_half():
    assert organize.category_folder("%%Name") == ("Other", "Name")
    assert organize.category_folder("Family%%") == ("Family", "Other")


def test_target_path():
    assert organize.target_path("/music/misc/a.mp3", "/music", "Tek%%PsyTrance") == str(
        Path("/music/Tek/PsyTrance/a.mp3")
    )


def test_root_for_path_finds_the_owning_root(music):
    other = music.parent / "elsewhere"
    assert organize.root_for_path(music / "a.mp3", [str(music), str(other)]) == str(music)
    assert organize.root_for_path(str(other / "b.mp3"), [str(music)]) is None
    # A root itself (not something under it) doesn't match itself.
    assert organize.root_for_path(music, [str(music)]) is None


# --- planning -----------------------------------------------------------------


def test_plan_organize_moves_a_categorized_track(music):
    path = _file(music / "misc" / "a.mp3")
    source = OrganizeSource(1, str(path), "Tek%%PsyTrance", str(music))
    plan = organize.plan_organize([source])
    assert plan.moves == [(str(path), str(music / "Tek" / "PsyTrance" / "a.mp3"))]
    assert plan.count(STATUS_MOVE) == 1


def test_plan_organize_refuses_missing_or_dj_software_or_outside_root(music):
    gone = OrganizeSource(1, str(music / "gone.mp3"), "Tek%%PsyTrance", str(music))
    crate = OrganizeSource(2, str(_file(music / "_Serato_" / "x.crate")), "Tek%%PsyTrance", str(music))
    outside = OrganizeSource(3, str(_file(music.parent / "elsewhere" / "b.mp3")), "Tek%%PsyTrance", str(music))
    no_root = OrganizeSource(4, str(_file(music / "c.mp3")), "Tek%%PsyTrance", None)
    plan = organize.plan_organize([gone, crate, outside, no_root])
    assert [item.status for item in plan.items] == [STATUS_REFUSED] * 4
    assert plan.moves == []


def test_plan_organize_flags_no_category(music):
    path = _file(music / "a.mp3")
    plan = organize.plan_organize([OrganizeSource(1, str(path), None, str(music))])
    assert plan.items[0].status == STATUS_NO_CATEGORY


def test_plan_organize_already_in_place_is_unchanged(music):
    path = _file(music / "Tek" / "PsyTrance" / "a.mp3")
    plan = organize.plan_organize([OrganizeSource(1, str(path), "Tek%%PsyTrance", str(music))])
    assert plan.items[0].status == STATUS_UNCHANGED


def test_plan_organize_conflicts(music):
    existing = _file(music / "Tek" / "PsyTrance" / "a.mp3")
    moving = _file(music / "misc" / "a.mp3")
    two_to_one_a = _file(music / "misc2" / "b.mp3")
    two_to_one_b = _file(music / "misc3" / "b.mp3")
    indexed_elsewhere = _file(music / "misc4" / "c.mp3")
    sources = [
        OrganizeSource(1, str(moving), "Tek%%PsyTrance", str(music)),  # "a.mp3" already exists there
        OrganizeSource(2, str(two_to_one_a), "Tek%%PsyTrance", str(music)),
        OrganizeSource(3, str(two_to_one_b), "Tek%%PsyTrance", str(music)),  # same target as #2
        OrganizeSource(4, str(indexed_elsewhere), "Tek%%PsyTrance", str(music)),
    ]
    indexed = [str(music / "Tek" / "PsyTrance" / "c.mp3")]
    plan = organize.plan_organize(sources, indexed)
    statuses = {item.track_id: item.status for item in plan.items}
    assert statuses == {1: STATUS_CONFLICT, 2: STATUS_CONFLICT, 3: STATUS_CONFLICT, 4: STATUS_CONFLICT}
    assert existing.is_file()  # nothing touched during planning


def test_plan_organize_case_only_move_of_the_same_file_is_allowed(music):
    # Not a real rename case here since the filename never changes, but a
    # case-insensitive filesystem could still report the target as
    # "existing" when it's the very file being organized.
    path = _file(music / "Tek" / "psytrance" / "a.mp3")
    plan = organize.plan_organize([OrganizeSource(1, str(path), "Tek%%PsyTrance", str(music))])
    # On a case-sensitive filesystem this is a genuine move (different folder
    # casing); either way it must not be reported as a conflict with itself.
    assert plan.items[0].status in (STATUS_MOVE, STATUS_UNCHANGED)


# --- plan_from_rows -----------------------------------------------------------


def test_plan_from_rows_resolves_each_row_s_root(music):
    from djmidi.library.workspace import LibraryRow

    db = LibraryDB(":memory:")
    db.add_root(music)
    path = _file(music / "misc" / "a.mp3")
    row = LibraryRow(track_id=1, path=str(path), missing=False, metadata=None, camelot_key=None, category="Tek%%PsyTrance")
    plan = organize.plan_from_rows(db, [row])
    assert plan.moves == [(str(path), str(music / "Tek" / "PsyTrance" / "a.mp3"))]
    db.close()


# --- apply ----------------------------------------------------------------


@pytest.fixture
def indexed(music):
    db = LibraryDB(":memory:")
    root = db.add_root(music)
    paths = [_file(music / "misc" / "01.mp3"), _file(music / "misc" / "02.mp3")]
    for path in paths:
        stat = path.stat()
        db.upsert_track(root.id, path, stat.st_size, stat.st_mtime)
    db.commit()
    yield db, music, paths
    db.close()


def test_apply_organize_moves_files_index_and_playlists_and_undo_restores(indexed):
    db, music, paths = indexed
    playlist = db.create_playlist("Friday", [str(paths[1]), str(paths[0])])
    record_id = db.get_track_by_path(paths[0]).id
    pairs = [
        (str(paths[0]), str(music / "Tek" / "PsyTrance" / "01.mp3")),
        (str(paths[1]), str(music / "Tek" / "PsyTrance" / "02.mp3")),
    ]

    result = organize.apply_organize(db, pairs)

    assert result.failed == []
    new_one, new_two = Path(pairs[0][1]), Path(pairs[1][1])
    assert new_one.is_file() and new_two.is_file()
    assert not paths[0].exists() and not paths[1].exists()
    track = db.get_track_by_path(new_one)
    assert track is not None and track.id == record_id and not track.missing
    assert db.playlist_paths(playlist) == [str(new_two), str(new_one)]

    undo = organize.apply_organize(db, [(new, old) for old, new in reversed(result.renamed)])
    assert undo.failed == []
    assert paths[0].is_file() and paths[1].is_file()
    assert db.get_track_by_path(paths[0]).id == record_id
    assert db.playlist_paths(playlist) == [str(paths[1]), str(paths[0])]


def test_apply_organize_creates_the_category_folders(indexed):
    db, music, paths = indexed
    target = music / "Tek" / "Tribe" / "01.mp3"
    assert not target.parent.exists()
    organize.apply_organize(db, [(str(paths[0]), str(target))])
    assert target.is_file()


def test_apply_organize_rechecks_each_pair(indexed):
    db, music, paths = indexed
    taken = _file(music / "Tek" / "taken.mp3")
    calls = []

    def failing_move(old, new):
        calls.append(old)
        raise OSError("disk says no")

    result = organize.apply_organize(
        db,
        [
            (str(paths[0]), str(taken)),
            (str(music / "gone.mp3"), str(music / "Tek" / "x.mp3")),
            (str(paths[1]), str(music / "Tek" / "02.mp3")),
        ],
        move=failing_move,
    )
    assert result.renamed == []
    assert [reason for _path, reason in result.failed] == [
        "taken.mp3 already exists at the target path",
        "file not found",
        "disk says no",
    ]
    assert calls == [str(paths[1])]
    assert paths[0].is_file() and taken.is_file()


def test_apply_organize_refuses_dj_software_folders(indexed):
    db, music, _paths = indexed
    crate = _file(music / "_Serato_" / "Subcrates" / "x.crate")
    result = organize.apply_organize(db, [(str(crate), str(music / "Tek" / "x.crate"))])
    assert result.failed == [(str(crate), "inside a DJ software folder")]
    assert crate.is_file()
