from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TBPM, TCON, TIT2, TKEY, TPE1
from PySide6.QtWidgets import QInputDialog, QMessageBox

from djmidi import taxonomy
from djmidi.gui import music_library_view as mlv
from djmidi.gui.music_library_view import (
    ALL_CATEGORIES,
    UNCATEGORIZED,
    MusicLibraryView,
)
from djmidi.library import workspace
from djmidi.library.metadata import read_metadata
from djmidi.library.serato_library import parse_crate


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
    _mp3(music / "Tek" / "Tribe" / "a.mp3", title="Alpha", artist="Zed", bpm="172", key="Am", genre="Techno")
    _mp3(music / "Tek" / "Tribe" / "b.mp3", title="Bravo", artist="Yan", bpm="175", key="Em", genre="Techno")
    _mp3(music / "misc" / "c.mp3", title="Charlie", artist="Xu", bpm="80", key="C", genre="Psytrancee")
    view = MusicLibraryView(db_path=":memory:")
    view.add_root(music)
    view.start_scan()
    view.run_pending_job()
    yield view, music, tmp_path
    view.close_db()


def test_db_opens_lazily():
    view = MusicLibraryView(db_path=":memory:")
    assert view._db is None
    view.show()
    assert view._db is not None
    view.close_db()


def test_scan_fills_consolidated_table(library):
    view, _music, _ = library
    assert view.is_busy() is False
    assert view.roots_list.count() == 1
    assert view.table_model.rowCount() == 3
    rows = {row.title: row for row in view.table_model.rows()}
    assert rows["Alpha"].camelot_key == "8A"
    assert rows["Alpha"].category == "Tek%%Tribe"
    assert rows["Charlie"].category is None
    assert rows["Charlie"].category_suggestion == "Tek%%PsyTrance"
    assert "Scan done: 3 new" in view.status_label.text()
    assert view.count_label.text() == "3 / 3 tracks"


def test_scan_without_roots_asks_for_a_folder():
    view = MusicLibraryView(db_path=":memory:")
    view.start_scan()
    assert view.is_busy() is False
    assert "Add a music folder" in view.status_label.text()
    view.close_db()


def test_text_and_category_filters(library):
    view, _, _ = library
    view.filter_edit.setText("bravo")
    assert [row.title for row in view.visible_rows()] == ["Bravo"]
    view.filter_edit.setText("")
    view.category_filter.setCurrentIndex(view.category_filter.findData(UNCATEGORIZED))
    assert [row.title for row in view.visible_rows()] == ["Charlie"]
    view.category_filter.setCurrentIndex(view.category_filter.findData("Tek%%Tribe"))
    assert sorted(row.title for row in view.visible_rows()) == ["Alpha", "Bravo"]
    view.category_filter.setCurrentIndex(view.category_filter.findData(ALL_CATEGORIES))
    assert len(view.visible_rows()) == 3


def test_bpm_column_sorts_numerically(library):
    view, _, _ = library
    view.table.sortByColumn(mlv._COLUMN_INDEX["bpm"], mlv.Qt.SortOrder.AscendingOrder)
    assert [row.bpm for row in view.visible_rows()] == [80, 172, 175]


def test_select_track_populates_panel(library):
    view, _, _ = library
    assert view.select_path(next(r.path for r in view.table_model.rows() if r.title == "Alpha"))
    assert view.field_edits["title"].text() == "Alpha"
    assert view.field_edits["bpm"].text() == "172"
    assert view.camelot_label.text() == "8A"
    assert view.category_value_label.text() == "Tek / Tribe"
    assert view.apply_button.isEnabled()
    assert not view.accept_suggestion_button.isEnabled()


def test_write_tags_is_undoable(library):
    view, music, _ = library
    path = str(music / "Tek" / "Tribe" / "a.mp3")
    view.select_path(path)
    view.field_edits["title"].setText("Alpha (Edit)")
    view.field_edits["bpm"].setText("172.5")
    assert view.pending_track_edits() == {"title": "Alpha (Edit)", "bpm": 172.5}
    assert view.apply_track_edits()
    assert read_metadata(path).title == "Alpha (Edit)"
    assert view.field_edits["title"].text() == "Alpha (Edit)"
    assert view.undo_button.isEnabled()
    view.undo_stack.undo()
    assert read_metadata(path).title == "Alpha"
    assert {r.title for r in view.table_model.rows()} == {"Alpha", "Bravo", "Charlie"}
    view.undo_stack.redo()
    assert read_metadata(path).title == "Alpha (Edit)"


def test_write_tags_noop_and_invalid_bpm(library, monkeypatch):
    view, music, _ = library
    view.select_path(str(music / "misc" / "c.mp3"))
    assert view.apply_track_edits() is False
    assert "No tag changes" in view.status_label.text()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    view.field_edits["bpm"].setText("fast")
    assert view.apply_track_edits() is False
    assert warnings


def test_confirm_suggestion_adds_alias(library):
    view, music, _ = library
    view.select_path(str(music / "misc" / "c.mp3"))
    assert view.accept_suggestion_button.isEnabled()
    view.confirm_category_suggestion()
    assert "Psytrancee" in taxonomy.get_category("Tek%%PsyTrance").aliases
    row = next(r for r in view.table_model.rows() if r.title == "Charlie")
    assert row.category == "Tek%%PsyTrance"
    # Persisted, so it survives a restart.
    saved, _removed = view.db.category_overrides()
    assert any(s.canonical == "Tek%%PsyTrance" and "Psytrancee" in s.aliases for s in saved)


def _select_category(view, canonical):
    for i in range(view.category_tree.topLevelItemCount()):
        family = view.category_tree.topLevelItem(i)
        for j in range(family.childCount()):
            if family.child(j).data(0, mlv.Qt.ItemDataRole.UserRole) == canonical:
                view.category_tree.setCurrentItem(family.child(j))
                return family.child(j)
    raise AssertionError(canonical)


def test_category_tree_counts_tracks(library):
    view, _, _ = library
    item = _select_category(view, "Tek%%Tribe")
    assert item.text(1) == "2"


def test_category_buttons(library, monkeypatch):
    view, _, _ = library
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Dub", True))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Roots", True))
    view._on_new_category_clicked()
    assert taxonomy.get_category("Dub%%Roots")

    _select_category(view, "Dub%%Roots")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Roots Reggae", True))
    view._on_add_alias_clicked()
    assert "Roots Reggae" in taxonomy.get_category("Dub%%Roots").aliases

    _select_category(view, "Dub%%Roots")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("RootsDub", True))
    view._on_rename_category_clicked()
    assert "Roots" in taxonomy.get_category("Dub%%RootsDub").aliases

    _select_category(view, "Tek%%BarBass")
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Tek / HardTek", True))
    view._on_merge_clicked()
    assert "BarBass" in taxonomy.get_category("Tek%%HardTek").aliases

    _select_category(view, "Dub%%RootsDub")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    view._on_delete_category_clicked()
    assert "Dub%%RootsDub" not in {c.canonical for c in taxonomy.all_categories()}
    assert "Deleted" in view.status_label.text()


def test_duplicate_category_shows_warning(library, monkeypatch):
    view, _, _ = library
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Tek", True))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Tribe", True))
    view._on_new_category_clicked()
    assert warnings


def test_playlists_from_selection_generation_and_match(library, monkeypatch):
    view, music, _ = library
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("My set", True))
    view.table.selectAll()
    view._on_new_playlist_clicked()
    assert view.playlist_list.count() == 1
    assert view.playlist_tracks.count() == 3

    view._on_generate_clicked()
    generated = view.db.playlist_paths(view.selected_playlist_id())
    # Category, then BPM range, then key -- uncategorized sorts last.
    assert [Path(p).name for p in generated] == ["a.mp3", "b.mp3", "c.mp3"]

    view.select_path(str(music / "Tek" / "Tribe" / "a.mp3"))
    view._on_match_clicked()
    matched = view.db.playlist_paths(view.selected_playlist_id())
    assert [Path(p).name for p in matched] == ["a.mp3", "b.mp3"]
    assert view.playlist_list.count() == 3


def test_playlist_rename_delete_and_crate_export(library, monkeypatch):
    view, music, tmp_path = library
    playlist_id = view.create_playlist("Set", [str(music / "misc" / "c.mp3")])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed", True))
    view._on_rename_playlist_clicked()
    assert view.db.list_playlists()[0].name == "Renamed"

    crate = tmp_path / "out" / "Renamed.crate"
    crate.parent.mkdir()
    view.export_playlist_as_crate(playlist_id, str(crate))
    assert workspace.read_serato_crate(crate) == [str((music / "misc" / "c.mp3").resolve())]
    assert parse_crate(crate)[0].startswith(str(music.resolve()).lstrip("/"))

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    view._on_delete_playlist_clicked()
    assert view.playlist_list.count() == 0


def test_import_serato_crate_feeds_category_hints(library, monkeypatch):
    view, music, tmp_path = library
    crate = tmp_path / "Tek%%HardTek%%Friday.crate"
    workspace.export_serato_crate(crate, [str((music / "misc" / "c.mp3").resolve())])
    monkeypatch.setattr(mlv.QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(crate)], ""))
    view._on_import_serato_clicked()
    assert view.playlist_list.count() == 1
    assert "serato" in view.playlist_list.item(0).text()
    row = next(r for r in view.table_model.rows() if r.title == "Charlie")
    # The crate's resolved path matches the indexed one only if both are
    # canonical; macOS tmp dirs live behind a /private symlink.
    if row.path == str((music / "misc" / "c.mp3").resolve()):
        assert row.category == "Tek%%HardTek"


def test_import_traktor_and_bad_file(library, monkeypatch, tmp_path):
    view, _, _ = library
    nml = tmp_path / "collection.nml"
    nml.write_text(
        '<?xml version="1.0"?><NML VERSION="20"><COLLECTION ENTRIES="0"></COLLECTION>'
        '<PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="1">'
        '<NODE TYPE="PLAYLIST" NAME="Set"><PLAYLIST ENTRIES="1" TYPE="LIST">'
        '<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="NoVol/:m/:a.mp3"/></ENTRY>'
        "</PLAYLIST></NODE></SUBNODES></NODE></PLAYLISTS></NML>",
        encoding="utf-8",
    )
    monkeypatch.setattr(mlv.QFileDialog, "getOpenFileName", lambda *a, **k: (str(nml), ""))
    view._on_import_traktor_clicked()
    assert view.playlist_list.count() == 1
    assert view.playlist_tracks.count() == 1

    bad = tmp_path / "bad.nml"
    bad.write_text("<not xml", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(mlv.QFileDialog, "getOpenFileName", lambda *a, **k: (str(bad), ""))
    view._on_import_traktor_clicked()
    assert warnings


def test_remove_root_clears_index(library, monkeypatch):
    view, _, _ = library
    view.roots_list.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    view._on_remove_root_clicked()
    assert view.roots_list.count() == 0
    assert view.table_model.rowCount() == 0


def test_missing_root_is_skipped(tmp_path):
    view = MusicLibraryView(db_path=":memory:")
    view.add_root(tmp_path / "gone")
    view.start_scan()
    view.run_pending_job()
    assert "Scan done: 0 new" in view.status_label.text()
    view.close_db()


def test_clean_noise_frames_flow(library, monkeypatch):
    view, music, _ = library
    from mutagen.id3 import COMM

    path = music / "misc" / "c.mp3"
    tags = ID3(path)
    tags.add(COMM(encoding=3, lang="eng", desc="ID3v1 Comment", text=["junk"]))
    tags.save(path)
    view.select_path(str(path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    view._on_clean_clicked()
    assert not [f for f in ID3(path).getall("COMM") if f.desc == "ID3v1 Comment"]
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: infos.append(args))
    view._on_clean_clicked()
    assert infos


def test_main_window_has_music_library_tab():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    index = window._tab_indexes["library"]
    assert window.left_tabs.tabText(index) == "Music Library"
    assert window.left_tabs.widget(index) is window.music_library_view
    window.left_tabs.setCurrentIndex(index)
    assert not window._right_splitter.isVisible()
    window.close()
