from __future__ import annotations

import pytest

from djmidi.library import duplicates
from djmidi.library.db import LibraryDB
from djmidi.library.duplicates import (
    PREFIX_BYTES,
    TIER_EXACT,
    TIER_METADATA,
    exact_candidate_count,
    find_exact_duplicates,
    find_metadata_duplicates,
    iter_exact_duplicates,
    metadata_key,
    normalize_artist,
    normalize_title,
)
from djmidi.library.metadata import TrackMetadata


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Daft Punk", "daft punk"),
        ("  BEYONCÉ ", "beyonce"),
        ("Artist feat. Guest", "artist"),
        ("Artist ft Guest", "artist"),
        ("Artist (Featuring Guest)", "artist"),
        ("Simon & Garfunkel", "simon garfunkel"),
        ("AC/DC", "ac dc"),
        ("Craft", "craft"),
        (None, ""),
    ],
)
def test_normalize_artist(raw, expected):
    assert normalize_artist(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Alpha (Original Mix)", "alpha"),
        ("Alpha - Original Mix", "alpha"),
        ("Alpha [Original]", "alpha"),
        ("Alpha (original version)", "alpha"),
        ("Alpha (feat. Guest)", "alpha"),
        ("Alpha feat. Guest", "alpha"),
        ("Alpha (feat. Guest) (Original Mix)", "alpha"),
        ("Don't Stop!", "don t stop"),
        # Different versions stay different.
        ("Alpha (Extended Mix)", "alpha extended mix"),
        ("Alpha (Radio Edit)", "alpha radio edit"),
        ("Alpha (Zed Remix)", "alpha zed remix"),
        ("The Original", "the original"),
        ("Left", "left"),
    ],
)
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


def test_metadata_key_needs_artist_and_title():
    assert metadata_key("Zed", "Alpha") == ("zed", "alpha")
    assert metadata_key(None, "Alpha") is None
    assert metadata_key("Zed", "  ") is None
    assert metadata_key("!!", "Alpha") is None


def test_find_metadata_duplicates_groups_normalized_matches():
    groups = find_metadata_duplicates(
        [
            ("/m/a.mp3", "Zed", "Alpha (Original Mix)"),
            ("/m/b.flac", "ZED feat. Yan", "alpha"),
            ("/m/c.mp3", "Zed", "Alpha (Extended Mix)"),
            ("/m/d.mp3", None, "Alpha"),
            ("/m/e.mp3", "Xu", "Bravo"),
            ("/m/f.wav", "xu", "Bravo!"),
            ("/m/g.wav", "Xu", "bravo"),
        ]
    )
    assert [(g.tier, g.paths) for g in groups] == [
        (TIER_METADATA, ("/m/e.mp3", "/m/f.wav", "/m/g.wav")),
        (TIER_METADATA, ("/m/a.mp3", "/m/b.flac")),
    ]
    assert groups[1].key == "zed — alpha"
    assert groups[1].label == "Zed — Alpha (Original Mix)"


def _write(path, data: bytes):
    path.write_bytes(data)
    return str(path)


def test_exact_duplicates_only_reads_same_size_files(tmp_path, monkeypatch):
    a = _write(tmp_path / "a.mp3", b"x" * 100)
    b = _write(tmp_path / "b.mp3", b"x" * 100)
    c = _write(tmp_path / "c.mp3", b"y" * 100)  # same size, other content
    lonely = _write(tmp_path / "d.mp3", b"x" * 7)
    empty1 = _write(tmp_path / "e.mp3", b"")
    empty2 = _write(tmp_path / "f.mp3", b"")
    opened: list[str] = []
    real_open = open

    def tracking_open(path, *args, **kwargs):
        opened.append(str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", tracking_open)
    entries = [(p, (tmp_path / p).stat().st_size) for p in (a, b, c, lonely, empty1, empty2)]
    groups = find_exact_duplicates(entries)
    assert [(g.tier, g.paths, g.size) for g in groups] == [(TIER_EXACT, (a, b), 100)]
    assert sorted(set(opened)) == sorted([a, b, c])
    assert exact_candidate_count(entries) == 3


def test_exact_duplicates_large_files_need_full_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(duplicates, "CHUNK_BYTES", 4096)
    head = b"h" * PREFIX_BYTES
    a = _write(tmp_path / "a.wav", head + b"tail-1")
    b = _write(tmp_path / "b.wav", head + b"tail-2")  # same prefix, differs at the end
    c = _write(tmp_path / "c.wav", head + b"tail-1")
    groups = find_exact_duplicates([(p, PREFIX_BYTES + 6) for p in (a, b, c)])
    assert [g.paths for g in groups] == [(a, c)]
    assert len(groups[0].key) == 40


def test_iter_exact_duplicates_yields_progress_and_skips_unreadable(tmp_path, caplog):
    a = _write(tmp_path / "a.mp3", b"z" * 50)
    b = _write(tmp_path / "b.mp3", b"z" * 50)
    gone = str(tmp_path / "gone.mp3")
    steps = iter_exact_duplicates([(a, 50), (b, 50), (gone, 50)])
    progress = []
    while True:
        try:
            progress.append(next(steps))
        except StopIteration as done:
            groups = done.value
            break
    assert progress[-1] == 3
    assert progress == sorted(progress)
    assert [g.paths for g in groups] == [(a, b)]
    assert "unreadable" in caplog.text


def test_entries_from_db_skip_missing_and_untagged(tmp_path):
    db = LibraryDB()
    root = db.add_root(tmp_path)
    for name, size in (("a.mp3", 10), ("b.mp3", 10), ("c.mp3", 20)):
        db.upsert_track(root.id, str(tmp_path / name), size, 1.0)
    db.commit()
    tracks = {t.path: t for t in db.list_tracks()}
    db.set_cached_metadata(tracks[str(tmp_path / "a.mp3")].id, 1.0, TrackMetadata(artist="Zed", title="Alpha"))
    db.mark_missing_except(root.id, [str(tmp_path / "a.mp3"), str(tmp_path / "c.mp3")])
    assert duplicates.metadata_entries(db) == [(str(tmp_path / "a.mp3"), "Zed", "Alpha")]
    assert duplicates.size_entries(db) == [(str(tmp_path / "a.mp3"), 10), (str(tmp_path / "c.mp3"), 20)]
    db.close()


def test_audio_bitrate_unknown_file(tmp_path):
    assert duplicates.audio_bitrate(tmp_path / "nope.mp3") is None
    assert duplicates.audio_bitrate(_write(tmp_path / "junk.mp3", b"not audio")) is None
