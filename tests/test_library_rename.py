"""Template-based file renaming (issue #260). Every file renamed here lives
under pytest's tmp_path."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

from djmidi.library import rename
from djmidi.library.db import LibraryDB
from djmidi.library.metadata import TrackMetadata
from djmidi.library.rename import (
    STATUS_CONFLICT,
    STATUS_MISSING_TAGS,
    STATUS_REFUSED,
    STATUS_RENAME,
    STATUS_UNCHANGED,
    RenameSource,
    TemplateError,
)


def _file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    return path


def _source(track_id: int, path: Path, **tags: object) -> RenameSource:
    return RenameSource(track_id, str(path), TrackMetadata(**tags))


@pytest.fixture
def music(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    return root


# --- templates --------------------------------------------------------------


def test_parse_template_fields():
    assert rename.parse_template("{artist} - {title} [{BPM}]") == ["artist", "title", "bpm"]


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("{artist}/{title}", "/"),
        ("{artist}\\{title}", "/"),
        ("{artist - {title}", "Unbalanced"),
        ("{artist}} x", "Unbalanced"),
        ("plain name", "no field"),
        ("{artist} - {year}", "Unknown field {year}"),
    ],
)
def test_bad_templates_are_rejected(template, message):
    with pytest.raises(TemplateError, match=message):
        rename.parse_template(template)


def test_render_stem_sanitizes_and_formats():
    values = rename.field_values(
        "/m/old name.mp3", TrackMetadata(artist="AC/DC", title=' Back: In "Black"? ', bpm=172.0, key="Am")
    )
    assert rename.render_stem("{artist} - {title} {bpm} {camelot}", values) == (
        "AC_DC - Back_ In _Black__ 172 8A",
        [],
    )
    assert rename.render_stem("{filename} ({bpm})", rename.field_values("/m/x.mp3", TrackMetadata(bpm=128.5))) == (
        "x (128.5)",
        [],
    )


def test_render_stem_reports_missing_fields():
    values = rename.field_values("/m/a.mp3", TrackMetadata(title="T", artist="  "))
    assert rename.render_stem("{artist} - {title} - {album}", values) == (None, ["artist", "album"])


def test_sanitize_strips_dots_and_whitespace():
    assert rename.sanitize("  ..hidden \t name.  ") == "hidden name"
    assert rename.sanitize("a\x00b") == "a_b"


def test_long_names_are_truncated_to_fit_the_file_system():
    stem, _ = rename.render_stem("{title}", {"title": "é" * 300})
    assert len(stem.encode("utf-8")) <= 240
    assert stem == "é" * 120


# --- planning ---------------------------------------------------------------


def test_plan_renames_statuses(music, tmp_path):
    ok = _file(music / "a" / "01.mp3")
    same = _file(music / "a" / "Bee - Song.flac")
    untagged = _file(music / "a" / "02.mp3")
    outside = _file(tmp_path / "elsewhere" / "03.mp3")
    serato = _file(music / "_Serato_" / "04.mp3")
    gone = music / "a" / "05.mp3"
    plan = rename.plan_renames(
        [
            _source(1, ok, artist="Ay", title="One"),
            _source(2, same, artist="Bee", title="Song"),
            _source(3, untagged, title="Only title"),
            _source(4, outside, artist="X", title="Y"),
            _source(5, serato, artist="X", title="Z"),
            _source(6, gone, artist="X", title="W"),
        ],
        "{artist} - {title}",
        [music],
    )
    statuses = [(Path(item.old_path).name, item.status, item.reason) for item in plan.items]
    assert statuses == [
        ("01.mp3", STATUS_RENAME, ""),
        ("Bee - Song.flac", STATUS_UNCHANGED, "already named this way"),
        ("02.mp3", STATUS_MISSING_TAGS, "no artist tag"),
        ("03.mp3", STATUS_REFUSED, "outside the library folders"),
        ("04.mp3", STATUS_REFUSED, "inside a DJ software folder"),
        ("05.mp3", STATUS_REFUSED, "file not found"),
    ]
    assert plan.renames == [(str(ok), str(music / "a" / "Ay - One.mp3"))]
    assert plan.count(STATUS_REFUSED) == 3


def test_plan_keeps_the_extension_and_folder(music):
    track = _file(music / "deep" / "er" / "x.AIFF")
    [item] = rename.plan_renames([_source(1, track, artist="A", title="B")], "{artist} - {title}", [music]).items
    assert item.new_path == str(music / "deep" / "er" / "A - B.AIFF")


def test_a_root_itself_is_not_within_roots(music):
    assert rename.is_within_roots(music / "x.mp3", [music])
    assert not rename.is_within_roots(music, [music])
    assert not rename.is_within_roots(music.parent / "musicology" / "x.mp3", [music])


def test_protected_folders_are_case_insensitive():
    assert rename.in_protected_folder("/Volumes/USB/pioneer/rekordbox/x.mp3")
    assert rename.in_protected_folder("/m/Native Instruments/x.mp3")
    assert not rename.in_protected_folder("/m/Tek/Serato tracks/x.mp3")


def test_plan_conflicts(music):
    a = _file(music / "a.mp3")
    b = _file(music / "b.mp3")
    c = _file(music / "c.mp3")
    _file(music / "Taken - Name.mp3")
    indexed = music / "Indexed - Name.mp3"
    plan = rename.plan_renames(
        [
            _source(1, a, artist="Dup", title="Name"),
            _source(2, b, artist="dup", title="NAME"),
            _source(3, c, artist="Taken", title="Name"),
            _source(4, _file(music / "d.mp3"), artist="Indexed", title="Name"),
        ],
        "{artist} - {title}",
        [music],
        indexed_paths=[str(indexed)],
    )
    reasons = [(item.status, item.reason) for item in plan.items]
    assert reasons == [
        (STATUS_CONFLICT, "1 other selected track(s) get the same name"),
        (STATUS_CONFLICT, "1 other selected track(s) get the same name"),
        (STATUS_CONFLICT, "a file with this name already exists"),
        (STATUS_CONFLICT, "this name is already in the library index"),
    ]
    assert plan.renames == []


def test_case_only_rename_of_the_same_file_is_allowed(music):
    track = _file(music / "dj - track.mp3")
    [item] = rename.plan_renames([_source(1, track, artist="DJ", title="Track")], "{artist} - {title}", [music]).items
    assert item.status == STATUS_RENAME
    assert item.new_path == str(music / "DJ - Track.mp3")


def test_plan_rejects_a_bad_template(music):
    with pytest.raises(TemplateError):
        rename.plan_renames([], "{nope}", [music])


# --- applying -----------------------------------------------------------------


@pytest.fixture
def indexed(music):
    db = LibraryDB(":memory:")
    root = db.add_root(music)
    paths = [_file(music / "Tek" / "01.mp3"), _file(music / "Tek" / "02.mp3")]
    for path in paths:
        stat = path.stat()
        db.upsert_track(root.id, path, stat.st_size, stat.st_mtime)
    db.commit()
    for (record, _meta), title in zip(db.list_tracks_with_metadata(), ("One", "Two"), strict=True):
        db.set_cached_metadata(record.id, record.mtime, TrackMetadata(artist="Zed", title=title))
    db.commit()
    yield db, music, paths
    db.close()


def test_plan_from_db_uses_cached_tags_and_roots(indexed):
    db, music, paths = indexed
    plan = rename.plan_from_db(db, [str(p) for p in paths] + ["/not/indexed.mp3"], "{artist} - {title}")
    assert plan.renames == [
        (str(paths[0]), str(music / "Tek" / "Zed - One.mp3")),
        (str(paths[1]), str(music / "Tek" / "Zed - Two.mp3")),
    ]


def test_apply_renames_moves_files_index_and_playlists_and_undo_restores(indexed):
    db, music, paths = indexed
    playlist = db.create_playlist("Friday", [str(paths[1]), str(paths[0])])
    record_id = db.get_track_by_path(paths[0]).id
    plan = rename.plan_from_db(db, [str(p) for p in paths], "{artist} - {title}")

    result = rename.apply_renames(db, plan.renames)

    assert result.failed == []
    new_one, new_two = music / "Tek" / "Zed - One.mp3", music / "Tek" / "Zed - Two.mp3"
    assert new_one.is_file() and new_two.is_file()
    assert not paths[0].exists() and not paths[1].exists()
    track = db.get_track_by_path(new_one)
    assert track is not None and track.id == record_id and not track.missing
    assert db.get_cached_metadata(record_id)[1].title == "One"
    assert db.playlist_paths(playlist) == [str(new_two), str(new_one)]

    undo = rename.apply_renames(db, [(new, old) for old, new in reversed(result.renamed)])
    assert undo.failed == []
    assert paths[0].is_file() and paths[1].is_file()
    assert db.get_track_by_path(paths[0]).id == record_id
    assert db.playlist_paths(playlist) == [str(paths[1]), str(paths[0])]


def test_apply_renames_rechecks_each_pair(indexed):
    db, music, paths = indexed
    taken = _file(music / "Tek" / "taken.mp3")
    calls = []

    def failing_rename(old, new):
        calls.append(old)
        raise OSError("disk says no")

    result = rename.apply_renames(
        db,
        [
            (str(paths[0]), str(taken)),
            (str(paths[0]), str(music / "elsewhere.mp3")),
            (str(music / "Tek" / "gone.mp3"), str(music / "Tek" / "x.mp3")),
            (str(paths[1]), str(music / "Tek" / "new.mp3")),
        ],
        rename=failing_rename,
    )
    assert result.renamed == []
    assert [reason for _path, reason in result.failed] == [
        "taken.mp3 already exists",
        "a file is only renamed inside its own folder",
        "file not found",
        "disk says no",
    ]
    assert calls == [str(paths[1])]
    assert paths[0].is_file() and taken.is_file()


def test_apply_renames_refuses_dj_software_folders(indexed):
    db, music, _paths = indexed
    crate = _file(music / "_Serato_" / "Subcrates" / "x.crate")
    result = rename.apply_renames(db, [(str(crate), str(crate.with_name("y.crate")))])
    assert result.failed == [(str(crate), "inside a DJ software folder")]
    assert crate.is_file()


def test_rename_track_paths_skips_unknown_and_taken(indexed):
    db, _music, paths = indexed
    assert db.rename_track_paths([("/nope.mp3", "/other.mp3"), (str(paths[0]), str(paths[1]))]) == 0
    assert db.get_track_by_path(paths[0]) is not None


# --- CSV ------------------------------------------------------------------------


def test_mapping_csv(tmp_path):
    pairs = [("/m/a, b.mp3", "/m/A - B.mp3"), ("/m/é.mp3", "/m/E.mp3")]
    text = rename.mapping_to_csv(pairs)
    assert list(csv.reader(text.splitlines())) == [["old_path", "new_path"], ["/m/a, b.mp3", "/m/A - B.mp3"], ["/m/é.mp3", "/m/E.mp3"]]
    target = tmp_path / "out.csv"
    assert rename.export_mapping_csv(target, pairs) == 2
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    assert os.fspath(target).endswith(".csv")
