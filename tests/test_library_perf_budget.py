"""Performance budget for the Music Library (phase 6 item 4).

Seconds are useless as a CI budget (runner speed varies, coverage doubles
everything), so these count the operations that made the tab slow before
`v0.48.167`: Python `data()` calls while the table sorts and filters,
category resolutions per track, and pathlib work per track. Each budget is
far below what the old code paths did, and far above what the current ones
do, so it only trips on a real regression. `scripts/benchmark_library.py`
gives the wall-clock figures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QTableView

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark_library

from djmidi import taxonomy
from djmidi.gui import music_library_view as mlv
from djmidi.library import workspace
from djmidi.library.db import LibraryDB

TRACKS = 20_000


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    path = tmp_path_factory.mktemp("budget") / "library.sqlite3"
    benchmark_library.build_index(path, TRACKS)
    return path


def _count_calls(monkeypatch, owner, name):
    calls = [0]
    original = getattr(owner, name)

    def counted(*args, **kwargs):
        calls[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, counted)
    return calls


def test_consolidate_resolves_categories_per_folder_not_per_track(index, monkeypatch):
    resolutions = _count_calls(monkeypatch, taxonomy, "resolve_category")
    relative = _count_calls(monkeypatch, Path, "relative_to")
    db = LibraryDB(index)
    try:
        rows = workspace.consolidate(db)
    finally:
        db.close()
    assert len(rows) == TRACKS
    # Before v0.48.167: one resolution and one Path.relative_to per track.
    assert resolutions[0] < TRACKS // 3
    assert relative[0] == 0


def test_sorting_and_filtering_do_not_go_through_data(index, monkeypatch):
    db = LibraryDB(index)
    try:
        rows = workspace.consolidate(db)
    finally:
        db.close()
    model = mlv.LibraryTableModel()
    proxy = mlv.LibraryFilterProxy()
    proxy.setSourceModel(model)
    view = QTableView()  # never shown: no painting, only model work counts
    view.setModel(proxy)
    view.setSortingEnabled(True)
    calls = _count_calls(monkeypatch, mlv.LibraryTableModel, "data")
    model.set_rows(rows)
    view.sortByColumn(mlv._COLUMN_INDEX["bpm"], mlv.Qt.SortOrder.DescendingOrder)
    proxy.set_text_filter("artist 12")
    proxy.set_text_filter("")
    proxy.set_bpm_range(120, 130)
    # A proxy-side sort alone asked data() ~30 times per row (~600k here).
    assert calls[0] < TRACKS
    view.deleteLater()


def test_no_op_filter_changes_do_not_refilter(index, monkeypatch):
    model = mlv.LibraryTableModel()
    proxy = mlv.LibraryFilterProxy()
    proxy.setSourceModel(model)
    db = LibraryDB(index)
    try:
        model.set_rows(workspace.consolidate(db))
    finally:
        db.close()
    accepts = _count_calls(monkeypatch, mlv.LibraryFilterProxy, "filterAcceptsRow")
    for _ in range(3):
        proxy.set_genre_filter(None)
        proxy.set_key_filter(None)
        proxy.set_camelot_filter(None)
        proxy.set_bpm_range(None, None)
        proxy.set_category_filter(mlv.ALL_CATEGORIES)
        proxy.set_text_filter("")
    assert accepts[0] == 0
