from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TBPM, TCON, TIT2, TKEY, TPE1
from PySide6.QtCore import QPoint

from djmidi.gui.library_stats_dialog import BarChart, LibraryStatsDialog
from djmidi.gui.music_library_view import MusicLibraryView
from djmidi.library import history
from djmidi.library.stats import Bucket, compute_library_stats


def _mp3(path: Path, **tags: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((frame + b"\x00" * (417 - len(frame))) * 20)
    id3 = ID3()
    frames = {"title": TIT2, "artist": TPE1, "genre": TCON, "bpm": TBPM, "key": TKEY}
    for name, value in tags.items():
        id3.add(frames[name](encoding=3, text=[value]))
    id3.save(path)
    return path


@pytest.fixture
def library(tmp_path):
    music = tmp_path / "music"
    _mp3(
        music / "Tek" / "Tribe" / "a.mp3",
        title="Alpha",
        artist="Zed",
        bpm="172",
        key="Am",
        genre="Techno",
    )
    _mp3(
        music / "Tek" / "Tribe" / "b.mp3",
        title="Bravo",
        artist="Yan",
        bpm="175",
        key="Em",
        genre="techno",
    )
    _mp3(
        music / "misc" / "c.mp3",
        title="Charlie",
        artist="Xu",
        bpm="80",
        key="C",
        genre="Dub",
    )
    view = MusicLibraryView(db_path=":memory:")
    view.add_root(music)
    view.start_scan()
    view.run_pending_job()
    yield view, music
    view.close_db()


def test_bar_chart_sizes_with_buckets_and_maps_positions():
    buckets = [Bucket("one", 1), Bucket("two", 4), Bucket("three", 0)]
    rows = BarChart(buckets)
    columns = BarChart(buckets, vertical=True)
    assert (
        rows.minimumSizeHint().height()
        > BarChart(buckets[:1]).minimumSizeHint().height()
    )
    assert (
        columns.minimumSizeHint().width()
        > BarChart(buckets[:1], vertical=True).minimumSizeHint().width()
    )
    rows.resize(400, 200)
    assert rows.bucket_at(rows.bucket_rect(1).center()) == 1
    assert rows.bucket_at(QPoint(5, 199)) is None
    rows.grab()  # paints without error
    columns.resize(columns.minimumSizeHint())
    columns.grab()
    BarChart().grab()  # empty state


def test_dialog_without_history_explains_plays():
    stats = compute_library_stats([])
    dialog = LibraryStatsDialog(stats, "all indexed tracks")
    assert set(dialog.charts) == {
        "categories",
        "genres",
        "bpm",
        "keys",
        "added",
        "plays",
    }
    assert dialog.charts["plays"].buckets == ()
    assert "No play history" in dialog.notes["plays"].text()
    assert dialog.tabs.count() == 6
    dialog.close()


def test_statistics_button_without_scan_asks_for_one():
    view = MusicLibraryView(db_path=":memory:")
    view.show_statistics()
    assert view.stats_dialog is None
    assert "Scan" in view.status_label.text()
    view.close_db()


def test_statistics_follow_filters_and_history(library):
    view, music = library
    before = {p: p.read_bytes() for p in music.rglob("*.mp3")}
    view.show_statistics()
    dialog = view.stats_dialog
    assert dialog is not None and dialog.isVisible()
    stats = dialog.stats
    assert stats.total == 3 and stats.most_played is None
    assert {b.label: b.count for b in stats.by_genre} == {"Techno": 2, "Dub": 1}
    assert {b.label: b.count for b in stats.by_category}["Tek / Tribe"] == 2
    assert {b.label: b.count for b in stats.by_camelot}["8A"] == 1
    assert sum(b.count for b in stats.bpm_histogram) == 3
    assert sum(b.count for b in stats.added_per_month) == 3
    assert "all indexed tracks" in dialog.summary_label.text()

    # Filters narrow the statistics; play history adds the play counts.
    view.filter_edit.setText("Alpha")
    alpha = str(music / "Tek" / "Tribe" / "a.mp3")
    when = datetime(2025, 5, 1).astimezone()
    session = history.HistorySession(history.SOURCE_SERATO, "s1")
    session.entries = [
        history.PlayedEntry(alpha, when, history.SOURCE_SERATO, "s1"),
        history.PlayedEntry(alpha, when, history.SOURCE_SERATO, "s1"),
    ]
    view._history_sessions = [session]
    view.show_statistics()
    assert view.stats_dialog is not dialog
    dialog = view.stats_dialog
    assert dialog.stats.total == 1
    assert "1 of 3" in dialog.summary_label.text()
    assert [(t.label, t.play_count) for t in dialog.stats.most_played] == [
        ("Zed — Alpha", 2)
    ]
    assert dialog.stats.never_played == 0

    # Double-clicking a most-played bar selects that track in the table.
    view.reset_filters()
    dialog.charts["plays"].bucketActivated.emit(0)
    assert view._current_row().path == alpha
    assert {p: p.read_bytes() for p in music.rglob("*.mp3")} == before
