from datetime import datetime

import pytest

from djmidi.library.history import TrackPlays
from djmidi.library.metadata import TrackMetadata
from djmidi.library.stats import (
    CAMELOT_ORDER,
    NO_GENRE_LABEL,
    UNCATEGORIZED_LABEL,
    Bucket,
    added_per_month,
    bpm_histogram,
    camelot_distribution,
    compute_library_stats,
    count_genres,
)
from djmidi.library.workspace import LibraryRow


def _row(
    path,
    *,
    genre=None,
    bpm=None,
    camelot=None,
    category=None,
    missing=False,
    title=None,
    artist=None,
):
    metadata = TrackMetadata(title=title, artist=artist, genre=genre, bpm=bpm)
    return LibraryRow(
        track_id=hash(path) & 0xFFFF,
        path=path,
        missing=missing,
        metadata=metadata,
        camelot_key=camelot,
        category=category,
    )


def _ts(year, month, day=15):
    return datetime(year, month, day, 12).timestamp()  # noqa: DTZ001 -- local time on purpose


def test_bpm_histogram_fills_gaps_and_counts_missing():
    bins, missing = bpm_histogram(
        [120.0, 124.9, 131.0, None, 0.0, float("nan")], bin_width=5
    )
    assert bins == (Bucket("120–124", 2), Bucket("125–129", 0), Bucket("130–134", 1))
    assert missing == 3


def test_bpm_histogram_empty_and_bad_width():
    assert bpm_histogram([None]) == ((), 1)
    with pytest.raises(ValueError):
        bpm_histogram([120.0], bin_width=0)


def test_camelot_distribution_lists_all_24_codes_in_wheel_order():
    keys, missing = camelot_distribution(["8A", "8a ", "9B", None, "Am"])
    assert [b.label for b in keys] == list(CAMELOT_ORDER)
    assert len(keys) == 24 and keys[0].label == "1A" and keys[-1].label == "12B"
    assert {b.label: b.count for b in keys}["8A"] == 2
    assert {b.label: b.count for b in keys}["9B"] == 1
    assert missing == 2


def test_added_per_month_is_contiguous():
    months = added_per_month([_ts(2024, 11), _ts(2024, 11, 2), _ts(2025, 2)])
    assert months == (
        Bucket("2024-11", 2),
        Bucket("2024-12", 0),
        Bucket("2025-01", 0),
        Bucket("2025-02", 1),
    )
    assert added_per_month([]) == ()


def test_genres_group_case_and_spaces_and_sort_by_count():
    rows = [
        _row("a", genre="Psy  Trance"),
        _row("b", genre="psy trance"),
        _row("c", genre="Dub"),
        _row("d"),
    ]
    assert count_genres(rows) == (
        Bucket("Psy Trance", 2),
        Bucket(NO_GENRE_LABEL, 1),
        Bucket("Dub", 1),
    )


def test_compute_stats_counts_present_tracks_only():
    rows = [
        _row("/m/a.mp3", category="Tek%%Tribe", bpm=170.0, camelot="8A", genre="Tribe"),
        _row("/m/b.mp3", category="Tek%%Tribe", bpm=172.0, camelot="8A", genre="Tribe"),
        _row("/m/c.mp3", bpm=None, camelot=None),
        _row("/m/gone.mp3", category="Electro%%Dub", bpm=80.0, missing=True),
    ]
    mtimes = {
        "/m/a.mp3": _ts(2025, 1),
        "/m/b.mp3": _ts(2025, 3),
        "/m/gone.mp3": _ts(2020, 1),
    }
    stats = compute_library_stats(rows, mtimes)
    assert stats.total == 3 and stats.missing == 1
    assert stats.by_category == (
        Bucket("Tek / Tribe", 2),
        Bucket(UNCATEGORIZED_LABEL, 1),
    )
    assert stats.bpm_histogram == (Bucket("170–174", 2),)
    assert stats.no_bpm == 1 and stats.no_key == 1
    assert [b.label for b in stats.added_per_month] == ["2025-01", "2025-02", "2025-03"]
    # No history: the play statistics are unknown, not zero.
    assert (
        stats.most_played is None
        and stats.never_played is None
        and stats.played is None
    )


def test_compute_stats_with_history():
    rows = [
        _row("/m/a.mp3", artist="A", title="One"),
        _row("/m/b.mp3", artist="B", title="Two"),
        _row("/m/c.mp3"),
        _row("/m/gone.mp3", missing=True),
    ]
    when = datetime(2025, 5, 1).astimezone()
    plays = {
        "/m/a.mp3": TrackPlays("/m/a.mp3", 2, when, when),
        "/m/b.mp3": TrackPlays("/m/b.mp3", 5, when, when),
        "/m/gone.mp3": TrackPlays("/m/gone.mp3", 9, when, when),
        "/elsewhere.mp3": TrackPlays("/elsewhere.mp3", 3, when, when),
    }
    stats = compute_library_stats(rows, plays=plays, top_played=1)
    assert [(t.label, t.play_count) for t in stats.most_played] == [("B — Two", 5)]
    assert stats.played == 2
    assert stats.never_played == 1


def test_compute_stats_empty_library():
    stats = compute_library_stats([], plays={})
    assert (
        stats.total == 0 and stats.bpm_histogram == () and stats.added_per_month == ()
    )
    assert stats.most_played == () and stats.never_played == 0
    assert all(bucket.count == 0 for bucket in stats.by_camelot)
