"""Music Library speed-ups (phase 5 item 7): same results, faster paths."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt

from djmidi import taxonomy
from djmidi.gui.music_library_view import COLUMNS, LibraryFilterProxy, LibraryTableModel
from djmidi.library import workspace
from djmidi.library.metadata import TrackMetadata
from djmidi.library.workspace import LibraryRow, folder_hint


def _slow_folder_hint(track_path, root_path):
    parent = Path(track_path).parent
    if root_path:
        try:
            relative = parent.relative_to(root_path)
        except ValueError:
            relative = None
        if relative is not None:
            return relative.as_posix() if relative.parts else None
    return parent.name or None


@pytest.mark.parametrize(
    ("track", "root"),
    [
        ("/Music/Tek/PsyTrance/Album/t.mp3", "/Music"),
        ("/Music/Tek/PsyTrance/Album/t.mp3", "/Music/"),
        ("/Music/t.mp3", "/Music"),
        ("/Other/Tek/t.mp3", "/Music"),
        ("/Music2/Tek/t.mp3", "/Music"),
        ("/Music/Tek//Album/t.mp3", "/Music"),
        ("/Music/Tek/../Dub/t.mp3", "/Music"),
        ("/Music/Tek/./Dub/t.mp3", "/Music"),
        ("/Music/Tek/t.mp3", None),
        ("t.mp3", "/Music"),
    ],
)
def test_folder_hint_fast_path_matches_pathlib(track, root):
    if os.sep != "/":
        pytest.skip("POSIX paths")
    assert folder_hint(track, root) == _slow_folder_hint(track, root)


@pytest.mark.parametrize(
    "hints",
    [
        ("House", "Tek/PsyTrance/Some Album/CD1", None),
        ("Techno", "Unsorted/PsyTrance/Album", None),
        ("Psytrance", "Misc/Incoming/Batch 3", None),
        (None, "Electro/Drum & Bass/x", "Tek%%HardTek%%Playlist"),
        ("Drum n bass", "Incoming/New/Stuff", None),
        (None, "Tek/A%%B/c", None),
        ("Dub", "Electro", None),
    ],
)
def test_memoized_resolution_matches_the_direct_call(hints):
    genre, folder, crate = hints
    direct = taxonomy.resolve_category(genre, folder_hint=folder, crate_hint=crate)
    cached = workspace._resolve(hints, {})
    assert (cached.category, cached.confidence) == (direct.category, direct.confidence)


def _rows():
    def row(number, artist, title, bpm):
        return LibraryRow(number, f"/m/{number}.mp3", False, TrackMetadata(title=title, artist=artist, bpm=bpm), None, None)

    return [row(1, "Charlie", "Zed", 128.0), row(2, "alpha", "Yak", None), row(3, "Bravo", "Xylo", 90.5)]


def test_the_model_sorts_itself_and_keeps_the_selection():
    from PySide6.QtWidgets import QTableView

    model = LibraryTableModel()
    proxy = LibraryFilterProxy()
    proxy.setSourceModel(model)
    view = QTableView()
    view.setModel(proxy)
    view.setSortingEnabled(True)
    model.set_rows(_rows())
    artist = next(i for i, (_h, key) in enumerate(COLUMNS) if key == "artist")
    bpm = next(i for i, (_h, key) in enumerate(COLUMNS) if key == "bpm")
    view.sortByColumn(artist, Qt.SortOrder.AscendingOrder)
    assert [r.metadata.artist for r in model.rows()] == ["alpha", "Bravo", "Charlie"]
    view.selectionModel().select(
        proxy.index(2, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    )
    view.sortByColumn(bpm, Qt.SortOrder.DescendingOrder)
    assert [r.bpm for r in model.rows()] == [128.0, 90.5, None]
    selected = view.selectionModel().selectedRows()
    assert [proxy.index(i.row(), 0).data(Qt.ItemDataRole.DisplayRole) for i in selected] == ["Zed"]
    model.set_rows(_rows())  # a reload keeps the chosen order
    assert [r.bpm for r in model.rows()] == [128.0, 90.5, None]
    view.deleteLater()


def test_text_filter_matches_any_column_case_insensitively():
    model = LibraryTableModel()
    proxy = LibraryFilterProxy()
    proxy.setSourceModel(model)
    model.set_rows(_rows())
    proxy.set_text_filter("BRAVO")
    assert proxy.rowCount() == 1 and proxy.is_filtering()
    proxy.set_text_filter("90.5")
    assert proxy.rowCount() == 1
    proxy.set_text_filter("/m/")
    assert proxy.rowCount() == 3
    proxy.set_text_filter("")
    assert proxy.rowCount() == 3 and not proxy.is_filtering()
