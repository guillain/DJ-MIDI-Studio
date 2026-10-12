from __future__ import annotations

from pathlib import Path

import pytest
from mutagen.id3 import ID3, TBPM, TCON, TIT2, TKEY, TPE1
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox

from djmidi import taxonomy
from djmidi.gui import music_library_view as mlv
from djmidi.gui.music_library_view import (
    ALL_CATEGORIES,
    UNCATEGORIZED,
    MusicLibraryView,
)
from djmidi.gui.set_preparation import SET_TRACKS_MIME, decode_paths
from djmidi.library import workspace
from djmidi.library.db import TrackRecord
from djmidi.library.metadata import read_metadata
from djmidi.library.relink import (
    MATCH_EXACT,
    MATCH_NAME,
    RelinkCandidate,
    RelinkProposal,
)
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


def test_path_playlist_with_leftovers(library, monkeypatch):
    view, music, _ = library
    monkeypatch.setattr(mlv.MixPathDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Path", True))
    view.select_path(str(music / "Tek" / "Tribe" / "a.mp3"))
    view._on_path_clicked()
    names = {record.name: record.id for record in view.db.list_playlists()}
    assert set(names) == {"Path", "Path (leftovers)"}
    assert [Path(p).name for p in view.db.playlist_paths(names["Path"])] == ["a.mp3", "b.mp3"]
    assert [Path(p).name for p in view.db.playlist_paths(names["Path (leftovers)"])] == ["c.mp3"]
    assert view.selected_playlist_id() == names["Path"]
    assert "leftovers" in view.status_label.text()


def test_mix_path_dialog_applies_and_remembers_options(library, monkeypatch):
    view, _music, _ = library
    shown = []

    def accept(dialog):
        shown.append(dialog)
        if len(shown) == 1:
            assert dialog.tolerance_spin.value() == 6.0
            assert dialog.length_spin.text() == "No limit"
            dialog.direction_combo.setCurrentText("Falling BPM")
            dialog.tolerance_spin.setValue(2.5)
            dialog.length_spin.setValue(1)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(mlv.MixPathDialog, "exec", accept)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Short", True))
    view._on_path_clicked()
    assert "3 track(s) the current filter shows" in shown[0].note_label.text()
    names = {record.name: record.id for record in view.db.list_playlists()}
    # Falling from the fastest track, cut after one: the rest are leftovers.
    assert [Path(p).name for p in view.db.playlist_paths(names["Short"])] == ["b.mp3"]
    assert len(view.db.playlist_paths(names["Short (leftovers)"])) == 2

    # Reopening pre-fills the last values.
    view._on_path_clicked()
    second = shown[1]
    assert second.direction_combo.currentText() == "Falling BPM"
    assert second.tolerance_spin.value() == 2.5
    assert second.length_spin.value() == 1
    assert workspace.load_mix_path_options(view.db) == workspace.MixPathOptions("down", 2.5, 1)


def test_mix_path_dialog_cancel_keeps_options(library, monkeypatch):
    view, _music, _ = library
    workspace.save_mix_path_options(view.db, workspace.MixPathOptions("flat", 4.0, 10))
    monkeypatch.setattr(mlv.MixPathDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    view._on_path_clicked()
    assert view.db.list_playlists() == []
    assert workspace.load_mix_path_options(view.db) == workspace.MixPathOptions("flat", 4.0, 10)


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


def test_export_playlist_as_traktor_nml(library, monkeypatch):
    view, music, tmp_path = library
    track = str(music / "misc" / "c.mp3")
    view.create_playlist("Set", [track])
    view.playlist_list.setCurrentRow(0)
    nml = tmp_path / "Set.nml"
    monkeypatch.setattr(mlv.QFileDialog, "getSaveFileName", lambda *a, **k: (str(nml), ""))
    view._on_export_traktor_clicked()
    assert workspace.read_traktor_playlists(nml) == {"Set": [track]}
    assert "Set.nml" in view.status_label.text()


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


@pytest.mark.parametrize("size", [(1100, 700), (700, 500), (320, 240)])
def test_no_button_is_squeezed_below_its_minimum(size):
    """Issue #19's rule for every tab: at small window sizes the Music
    Library scrolls rather than crushing its buttons into slivers."""
    from PySide6.QtWidgets import QAbstractButton

    from djmidi.gui.theme import apply_theme

    # The compact "?" buttons rely on the app theme (padding 0); apply it here
    # instead of depending on an earlier test having built a MainWindow.
    apply_theme(QApplication.instance())
    view = MusicLibraryView(db_path=":memory:")
    view.resize(*size)
    view.show()
    try:
        for tab in range(view.side_tabs.count()):
            view.side_tabs.setCurrentIndex(tab)
            QApplication.processEvents()
            squeezed = [
                button.text()
                for button in view.findChildren(QAbstractButton)
                if button.isVisible()
                and (
                    button.width() < button.minimumSizeHint().width() - 1
                    or button.height() < button.minimumSizeHint().height() - 1
                )
            ]
            assert squeezed == [], (size, tab, squeezed)
    finally:
        view.close_db()
        view.close()


def _select_paths(view, paths):
    view.table.clearSelection()
    view.select_path(paths[0])
    view.select_paths(paths)


def test_write_tags_to_selection_is_one_undo_step(library):
    view, music, _ = library
    a, b = str(music / "Tek" / "Tribe" / "a.mp3"), str(music / "Tek" / "Tribe" / "b.mp3")
    _select_paths(view, [a, b])
    assert {row.path for row in view.selected_rows()} == {a, b}
    assert view.write_selection_button.isEnabled()
    assert view.write_tags_to_selection({"genre": "Tribe", "album": "Free Party"}) == 2
    for path in (a, b):
        tags = read_metadata(path)
        assert (tags.genre, tags.album) == ("Tribe", "Free Party")
    assert read_metadata(a).title == "Alpha"  # unchecked fields are untouched
    assert {row.path for row in view.selected_rows()} == {a, b}  # selection survives the reload
    assert "2 track(s)" in view.status_label.text()
    assert view.undo_stack.count() == 1
    view.undo_stack.undo()
    assert read_metadata(a).genre == "Techno" and read_metadata(b).album is None



def test_write_tags_to_selection_shows_progress_and_stops_on_cancel(library, monkeypatch):
    """Writing tags to thousands of files is long: every pass gets a progress
    window, and Cancel keeps what's already written (undoable)."""
    view, music, _ = library
    a, b = str(music / "Tek" / "Tribe" / "a.mp3"), str(music / "Tek" / "Tribe" / "b.mp3")
    labels = []

    def fake_progress(label, total, cancellable=True):
        labels.append((label, total, cancellable))
        return lambda done, total, text=None: done < 1 if label == "Writing tags…" else True

    monkeypatch.setattr(view, "_tag_write_progress", fake_progress)
    _select_paths(view, [a, b])
    assert view.write_tags_to_selection({"genre": "Tribe"}) == 1
    assert labels[0] == ("Writing tags…", 2, True)
    assert "Stopped: tags written to 1 of 2" in view.status_label.text()
    assert [read_metadata(p).genre for p in (a, b)].count("Tribe") == 1
    view.undo_stack.undo()
    assert labels[-1][0] == "Restoring tags…"
    assert read_metadata(a).genre == read_metadata(b).genre == "Techno"



def test_reselecting_many_tracks_is_a_single_selection_change(library):
    """After a bulk write the rewritten tracks are re-selected in one
    select() call: row by row, each selection refreshed the Track panel and
    froze the window for minutes on a long list."""
    view, _music, _ = library
    paths = [row.path for row in view.table_model.rows()]
    changes = []
    view.table.selectionModel().selectionChanged.connect(lambda *_: changes.append(1))
    view.select_paths(paths)
    assert len(changes) == 1
    assert {row.path for row in view.selected_rows()} == set(paths)


def test_progress_window_stays_up_while_the_table_reloads(library, monkeypatch):
    view, music, _ = library
    a, b = str(music / "Tek" / "Tribe" / "a.mp3"), str(music / "Tek" / "Tribe" / "b.mp3")
    reported = []

    def fake_progress(label, total, cancellable=True):
        def report(done, total, text=None):
            reported.append((label, done, total, text))
            return True

        return report

    monkeypatch.setattr(view, "_tag_write_progress", fake_progress)
    _select_paths(view, [a, b])
    view.write_tags_to_selection({"genre": "Tribe"})
    read_back = [r for r in reported if r[0] == "Reading tags back…"]
    assert ("Reading tags back…", 2, 3, "Refreshing the table…") in read_back
    assert read_back[-1][1:3] == (3, 3)

def test_tag_write_progress_dialog_counts_files(library):
    view, _music, _ = library
    report = view._tag_write_progress("Writing tags…", 3)
    assert report(1, 3) is True
    from PySide6.QtWidgets import QProgressDialog

    dialog = view.findChildren(QProgressDialog)[-1]
    assert dialog.labelText() == "Writing tags… 1/3" and dialog.value() == 1
    dialog.cancel()
    assert report(2, 3) is False

def test_write_tags_to_selection_skips_unchanged_and_reports_failures(library, monkeypatch):
    view, music, _ = library
    a, c = str(music / "Tek" / "Tribe" / "a.mp3"), str(music / "misc" / "c.mp3")
    _select_paths(view, [a, c])
    assert view.write_tags_to_selection({"genre": "Techno"}) == 1  # a already has it
    assert read_metadata(c).genre == "Techno"
    assert view.write_tags_to_selection({"genre": "Techno"}) == 0
    assert "already have" in view.status_label.text()

    Path(c).write_bytes(b"not audio")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    assert view.write_tags_to_selection({"bpm": 140.0}) == 1
    assert warnings and "1 failed" in warnings[0][2]
    assert read_metadata(a).bpm == 140.0


def test_bulk_tag_dialog_values(library):
    view, music, _ = library
    view.select_path(str(music / "Tek" / "Tribe" / "a.mp3"))
    view.field_edits["genre"].setText("Tribe")
    values = {name: edit.text() for name, edit in view.field_edits.items()}
    dialog = mlv.BulkTagDialog(values, 3, set(view.pending_track_edits()))
    ok = dialog.buttons.button(mlv.QDialogButtonBox.StandardButton.Ok)
    assert dialog.checked_fields() == ["genre"] and ok.isEnabled()
    assert "3 track" in ok.text()
    assert not dialog.edits["title"].isEnabled()
    dialog.checks["comment"].setChecked(True)
    dialog.edits["comment"].setText("")
    assert dialog.values() == {"genre": "Tribe", "comment": None}
    dialog.checks["genre"].setChecked(False)
    dialog.checks["comment"].setChecked(False)
    assert not ok.isEnabled()
    dialog.checks["bpm"].setChecked(True)
    dialog.edits["bpm"].setText("fast")
    with pytest.raises(ValueError):
        dialog.values()


def test_write_selection_button_disabled_without_selection(library):
    view, _, _ = library
    view.table.clearSelection()
    assert not view.write_selection_button.isEnabled()


def _titles(view):
    return sorted(row.title for row in view.visible_rows())


def test_genre_and_key_filters_list_the_library_values(library):
    view, _, _ = library
    genres = [view.genre_filter.itemText(i) for i in range(view.genre_filter.count())]
    keys = [view.key_filter.itemText(i) for i in range(view.key_filter.count())]
    assert genres == [mlv.ALL_GENRES, "Psytrancee", "Techno"]
    assert keys == [mlv.ALL_KEYS, "Am", "C", "Em"]
    view.genre_filter.setCurrentIndex(view.genre_filter.findData("Techno"))
    assert _titles(view) == ["Alpha", "Bravo"]
    view.key_filter.setCurrentIndex(view.key_filter.findData("Em"))
    assert _titles(view) == ["Bravo"]
    assert view.count_label.text() == "1 / 3 tracks"


def test_bpm_range_filter_is_inclusive_and_open_ended(library):
    view, _, _ = library
    view.bpm_min_filter.setValue(172)
    assert _titles(view) == ["Alpha", "Bravo"]
    view.bpm_max_filter.setValue(172)
    assert _titles(view) == ["Alpha"]
    view.bpm_min_filter.setValue(0)
    view.bpm_max_filter.setValue(100)
    assert _titles(view) == ["Charlie"]


def test_camelot_filter_with_and_without_compatible_keys(library):
    view, _, _ = library
    # Alpha Am = 8A, Bravo Em = 9A, Charlie C = 8B.
    view.camelot_filter.setCurrentIndex(view.camelot_filter.findData("8A"))
    assert _titles(view) == ["Alpha"]
    view.camelot_compatible_check.setChecked(True)
    assert _titles(view) == ["Alpha", "Bravo", "Charlie"]
    view.camelot_filter.setCurrentIndex(view.camelot_filter.findData("10A"))
    assert _titles(view) == ["Bravo"]


def test_filters_combine_and_reset(library):
    view, _, _ = library
    view.filter_edit.setText("a")
    view.genre_filter.setCurrentIndex(view.genre_filter.findData("Techno"))
    view.bpm_min_filter.setValue(173)
    assert _titles(view) == ["Bravo"]
    assert view.proxy.has_track_filters()
    view.reset_filters()
    assert _titles(view) == ["Alpha", "Bravo", "Charlie"]
    assert view.filter_edit.text() == "" and view.genre_filter.currentIndex() == 0
    assert view.bpm_min_filter.value() == 0 and not view.proxy.has_track_filters()


def test_value_filters_survive_a_reload(library):
    view, _, _ = library
    view.genre_filter.setCurrentIndex(view.genre_filter.findData("Techno"))
    view.reload()
    assert view.genre_filter.currentData() == "Techno"
    assert _titles(view) == ["Alpha", "Bravo"]


def test_confirm_all_suggestions_records_every_visible_pair(library, monkeypatch):
    """One click confirms every suggested category among the shown tracks
    (each genre becomes an alias), after listing them."""
    view, _music, _ = library
    assert view.pending_suggestions() == {"Psytrancee": "Tek%%PsyTrance"}
    assert view.accept_all_suggestions_button.isEnabled()
    assert view.accept_all_suggestions_button.text() == "Confirm all suggestions (1)"
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: asked.append(args[2]) or QMessageBox.StandardButton.Yes
    )
    view.accept_all_suggestions_button.click()
    assert "Psytrancee" in asked[0]
    rows = {row.title: row for row in view.table_model.rows()}
    assert rows["Charlie"].category == "Tek%%PsyTrance" and rows["Charlie"].category_suggestion is None
    assert view.pending_suggestions() == {} and not view.accept_all_suggestions_button.isEnabled()


def test_confirm_all_suggestions_only_covers_the_filtered_tracks(library):
    view, _music, _ = library
    view.filter_edit.setText("Alpha")
    assert view.pending_suggestions() == {}
    assert view.confirm_all_suggestions() == 0


def test_relink_missing_tracks_flow(library, monkeypatch):
    view, music, _ = library
    old = music / "misc" / "c.mp3"
    new = music / "moved" / "c.mp3"
    new.parent.mkdir()
    old.rename(new)
    playlist = view.db.create_playlist("Set", [str(old)])
    view.start_scan()
    view.run_pending_job()

    reviewed = []
    monkeypatch.setattr(mlv.RelinkDialog, "exec", lambda self: reviewed.append(self) or QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    view.start_relink_search()
    assert view.relink_button.isEnabled() is False
    view.run_pending_job()
    QApplication.processEvents()

    [dialog] = reviewed
    assert [(m.path, c.path) for m, c in dialog.choices()] == [(str(old), str(new))]
    assert view.db.get_track_by_path(old) is None
    assert view.db.playlist_paths(playlist) == [str(new)]
    assert view.table_model.rowCount() == 3
    assert "Relinked 1 track" in view.status_label.text()


def test_relink_with_nothing_missing(library):
    view, _music, _ = library
    view.start_relink_search()
    view.run_pending_job()
    assert view.status_label.text() == "No missing tracks to relink."


def test_relink_dialog_choices():
    def candidate(path, match, indexed=True):
        return RelinkCandidate(path, 1, 1, 1.0, match, indexed=indexed)

    proposals = [
        RelinkProposal(TrackRecord(1, 1, "/old/a.mp3", 1, 1.0, True), [candidate("/new/a.mp3", MATCH_EXACT)], True),
        RelinkProposal(
            TrackRecord(2, 1, "/old/b.mp3", 1, 1.0, True),
            [candidate("/x/b.mp3", MATCH_NAME), candidate("/y/b.mp3", MATCH_NAME, indexed=False)],
        ),
        RelinkProposal(TrackRecord(3, 1, "/old/c.mp3", 1, 1.0, True), []),
    ]
    dialog = mlv.RelinkDialog(proposals)
    ok = dialog.buttons.button(mlv.QDialogButtonBox.StandardButton.Ok)
    assert [c.path for _m, c in dialog.choices()] == ["/new/a.mp3"]
    dialog.set_choice(0, False)
    assert ok.isEnabled() is False
    dialog.set_choice(1, True, candidate_index=1)
    assert [(m.id, c.path) for m, c in dialog.choices()] == [(2, "/y/b.mp3")]
    assert dialog.tree.topLevelItem(1).text(2) == "Same name, other size (not scanned yet)"
    assert dialog.tree.topLevelItem(2).text(1) == "No matching file found"


def test_find_duplicates_without_scan_asks_for_one():
    view = MusicLibraryView(db_path=":memory:")
    view.find_duplicates()
    assert view.duplicates_dialog is None
    assert "Scan" in view.status_label.text()
    view.close_db()


def test_find_duplicates_opens_read_only_dialog(library, monkeypatch):
    """Issue #184: exact copies and same-artist+title tracks are listed,
    revealable in Finder, and no file is touched."""
    from djmidi.gui import duplicates_dialog

    view, music, _ = library
    original = music / "Tek" / "Tribe" / "a.mp3"
    copy = music / "copies" / "a copy.mp3"
    copy.parent.mkdir()
    copy.write_bytes(original.read_bytes())
    _mp3(music / "misc" / "alpha2.mp3", title="Alpha (Original Mix)", artist="ZED")
    view.start_scan()
    view.run_pending_job()
    before = {p: p.read_bytes() for p in music.rglob("*.mp3")}

    view.find_duplicates()
    assert view.is_busy()
    assert not view.duplicates_button.isEnabled()
    view.run_pending_job()
    assert view.duplicates_button.isEnabled()
    dialog = view.duplicates_dialog
    assert dialog is not None and dialog.isVisible()
    exact = [g for g in dialog.groups if g.tier == "exact"]
    by_meta = [g for g in dialog.groups if g.tier == "metadata"]
    assert [g.paths for g in exact] == [tuple(sorted((str(original), str(copy))))]
    assert [len(g.paths) for g in by_meta] == [3]
    assert "1 group(s) of identical files" in view.status_label.text()

    items = dialog.file_items()
    assert len(items) == 5
    assert {item.text(1) for item in items} == {"MP3"}
    group_item = items[0].parent()
    group_item.setExpanded(True)
    assert all(group_item.child(i).text(3) != "…" for i in range(group_item.childCount()))

    revealed: list[str] = []
    monkeypatch.setattr(duplicates_dialog, "reveal_in_file_manager", revealed.append)
    assert not dialog.reveal_button.isEnabled()
    dialog.tree.setCurrentItem(items[0])
    assert dialog.reveal_button.isEnabled()
    dialog.reveal_button.click()
    assert revealed == [items[0].data(0, duplicates_dialog.PATH_ROLE)]
    # Read-only: every file is still there, byte for byte.
    assert {p: p.read_bytes() for p in music.rglob("*.mp3")} == before

    view.find_duplicates()
    view.run_pending_job()
    assert view.duplicates_dialog is not dialog


def test_discard_duplicates_moves_ticked_copies_to_trash(library, monkeypatch):
    """Issue #208: ticked copies go to the (here fake, tmp_path) Trash after
    a confirmation, a group keeping no copy is refused, moved rows turn
    missing and playlists can follow the kept copy."""
    from PySide6.QtCore import Qt

    view, music, tmp_path = library
    original = music / "Tek" / "Tribe" / "a.mp3"
    copy = music / "copies" / "a copy.mp3"
    copy.parent.mkdir()
    copy.write_bytes(original.read_bytes())
    view.start_scan()
    view.run_pending_job()
    playlist = view.db.create_playlist("Friday", [str(copy), str(music / "misc" / "c.mp3")])

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def fake_trash(path: str) -> bool:
        Path(path).rename(bin_dir / Path(path).name)
        return True

    monkeypatch.setattr(mlv, "trash_file", fake_trash)
    questions: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda _p, _t, text, *a, **k: questions.append(text) or QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a, **k: warnings.append(text))

    view.find_duplicates()
    view.run_pending_job()
    dialog = view.duplicates_dialog
    assert not dialog.trash_button.isEnabled()

    # Ticking every copy of the exact group is refused; nothing moves.
    dialog.set_checked(str(original), True)
    dialog.set_checked(str(copy), True)
    assert dialog.trash_button.isEnabled()
    dialog.trash_button.click()
    assert warnings and "untick at least one" in warnings[0]
    assert questions == []
    assert original.is_file() and copy.is_file()

    dialog.set_checked(str(original), False)
    assert dialog.checked_paths() == [str(copy)]
    dialog.trash_button.click()
    assert str(copy) in questions[0] and f"keeps {original}" in questions[0]
    assert "Friday" in questions[1]
    assert not copy.exists() and (bin_dir / "a copy.mp3").is_file()
    assert original.is_file()
    assert view.db.playlist_paths(playlist) == [str(original), str(music / "misc" / "c.mp3")]
    assert view.db.get_track_by_path(copy) is None
    assert "Moved 1 duplicate(s) to the Trash." in view.status_label.text()
    assert all(item.data(0, Qt.ItemDataRole.UserRole + 1) != str(copy) for item in dialog.file_items())
    assert [g for g in dialog.groups if g.tier == "exact"] == []


def test_discard_duplicates_cancelled_or_without_playlists(library, monkeypatch):
    view, music, _ = library
    original = music / "Tek" / "Tribe" / "a.mp3"
    copy = music / "a copy.mp3"
    copy.write_bytes(original.read_bytes())
    view.start_scan()
    view.run_pending_job()
    moved: list[str] = []
    monkeypatch.setattr(mlv, "trash_file", lambda path: moved.append(path) or Path(path).unlink() is None)
    answers = [QMessageBox.StandardButton.No]
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answers.pop(0))
    view.find_duplicates()
    view.run_pending_job()
    view.duplicates_dialog.set_checked(str(copy), True)
    view.duplicates_dialog.trash_button.click()
    assert moved == [] and copy.is_file()

    answers.append(QMessageBox.StandardButton.Yes)
    view.duplicates_dialog.trash_button.click()
    # No playlist lists the copy: no second question; the row stays, missing.
    assert moved == [str(copy)] and answers == []
    assert view.db.get_track_by_path(copy).missing is True


def test_format_size():
    from djmidi.gui.duplicates_dialog import format_size

    assert format_size(None) == ""
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(5 * 1024**3) == "5.0 GB"


def test_history_panel_lists_sessions_and_never_played(library):
    """Issue #227: Serato history read-only, never-played tracks selectable."""
    import struct

    from djmidi.library import history
    from djmidi.library.serato_library import write_chunks

    view, music, tmp_path = library
    played = str(music / "Tek" / "Tribe" / "a.mp3")

    def field(field_id: int, value: bytes) -> bytes:
        return struct.pack(">II", field_id, len(value)) + value

    row = b"".join(
        [
            field(2, (played + "\0").encode("utf-16-be")),
            field(6, "Alpha\0".encode("utf-16-be")),
            field(28, struct.pack(">Q", 1_700_000_000)),
            field(31, struct.pack(">I", 1)),
            field(50, b"\x01"),
        ]
    )
    sessions = tmp_path / "Sessions"
    sessions.mkdir()
    session_file = sessions / "1.session"
    session_file.write_bytes(write_chunks([("vrsn", b""), ("oent", write_chunks([("adat", row)]))]))
    before = session_file.read_bytes()

    assert view.load_history({history.SOURCE_SERATO: sessions}) == 1
    assert session_file.read_bytes() == before
    assert view.side_tabs.tabText(view.side_tabs.currentIndex()) == "History"
    assert view.history_tree.topLevelItemCount() == 1
    child = view.history_tree.topLevelItem(0).child(0)
    assert child.data(0, mlv.Qt.ItemDataRole.UserRole) == played
    assert "1 play(s) of 1 track(s)" in view.history_summary.text()
    assert "2 of 3 indexed track(s) never played" in view.history_summary.text()

    assert view.select_never_played() == 2
    assert {row.title for row in view.selected_rows()} == {"Bravo", "Charlie"}

    view._on_history_item_activated(child, 0)
    assert view._current_row().title == "Alpha"


def test_history_without_default_folders_explains(library, monkeypatch):
    from djmidi.library import history

    view, _music, _ = library
    monkeypatch.setattr(history, "default_history_dirs", dict)
    view._on_load_history_clicked()
    assert "Load from folder" in view.history_summary.text()
    assert not view.select_never_played_button.isEnabled()
def test_health_report_without_scan_asks_for_one():
    view = MusicLibraryView(db_path=":memory:")
    view.start_health_report()
    assert view.health_dialog is None
    assert "Scan" in view.status_label.text()
    view.close_db()


def test_health_report_lists_filters_and_exports(library, monkeypatch, tmp_path):
    """Issue #225: a read-only report of problem files, filterable by issue
    kind and text, exportable to CSV, and linked back to the table."""
    import csv

    from djmidi.gui import health_report_dialog
    from djmidi.library import health

    view, music, _ = library
    empty = music / "misc" / "empty.mp3"
    empty.write_bytes(b"")
    corrupt = music / "misc" / "corrupt.mp3"
    corrupt.write_bytes(b"not audio" * 50)
    view.start_scan()
    view.run_pending_job()
    before = {p: p.read_bytes() for p in music.rglob("*.mp3")}

    view.start_health_report()
    assert view.is_busy() and not view.health_button.isEnabled()
    view.run_pending_job()
    assert view.health_button.isEnabled()
    dialog = view.health_dialog
    assert dialog is not None and dialog.isVisible()
    report = dialog.report
    assert report.checked == 5
    by_path: dict[str, list[str]] = {}
    for issue in report.issues:
        by_path.setdefault(issue.path, []).append(issue.kind)
    assert by_path[str(empty)] == [health.ISSUE_ZERO_LENGTH]
    assert by_path[str(corrupt)] == [health.ISSUE_UNREADABLE]
    # The fixture's MP3s are 128 kbps and tagged, without a cover.
    assert sorted(by_path[str(music / "misc" / "c.mp3")]) == sorted(
        [health.ISSUE_NO_ARTWORK, health.ISSUE_LOW_BITRATE]
    )
    assert "5 of 5 file(s) with at least one issue" in view.status_label.text()
    assert {p: p.read_bytes() for p in music.rglob("*.mp3")} == before

    assert dialog.model.rowCount() == len(report.issues)
    for kind, checkbox in dialog.kind_checkboxes.items():
        checkbox.setChecked(kind == health.ISSUE_ZERO_LENGTH)
    assert [i.path for i in dialog.visible_issues()] == [str(empty)]
    for checkbox in dialog.kind_checkboxes.values():
        checkbox.setChecked(True)
    dialog.filter_edit.setText("tribe")
    assert {i.path for i in dialog.visible_issues()} == {
        str(music / "Tek" / "Tribe" / "a.mp3"),
        str(music / "Tek" / "Tribe" / "b.mp3"),
    }
    assert not dialog.kind_checkboxes[health.ISSUE_EMPTY_TITLE].isEnabled()

    target = tmp_path / "health.csv"
    assert dialog.export_to(str(target)) == 4
    with open(target, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["path", "issue", "detail"] and len(rows) == 5

    monkeypatch.setattr(
        health_report_dialog.QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "ui.csv"), "")
    )
    dialog.export_button.click()
    assert (tmp_path / "ui.csv").exists()

    revealed: list[str] = []
    monkeypatch.setattr(health_report_dialog, "reveal_in_file_manager", revealed.append)
    assert not dialog.show_button.isEnabled()
    dialog.table.setCurrentIndex(dialog.model.index(0, 0))
    assert dialog.show_button.isEnabled()
    target_path = dialog.current_issue().path
    dialog.reveal_button.click()
    assert revealed == [target_path]
    # A table filter hiding the track is cleared to show it.
    view.filter_edit.setText("charlie")
    dialog.show_button.click()
    assert view._current_row().path == target_path
    assert view.filter_edit.text() == ""

    view.start_health_report()
    view.run_pending_job()
    assert view.health_dialog is not dialog
# --- background BPM/key analysis (issue #224) ----------------------------


@pytest.fixture
def untagged_library(tmp_path):
    music = tmp_path / "music"
    _mp3(music / "tagged.mp3", title="Tagged", bpm="172", key="Am")
    _mp3(music / "bare.mp3", title="Bare")
    view = MusicLibraryView(db_path=":memory:")
    view.add_root(music)
    view.start_scan()
    view.run_pending_job()
    yield view, music
    view.close_db()


def test_analyse_button_explains_when_librosa_is_missing(monkeypatch):
    monkeypatch.setattr(mlv, "analysis_available", lambda: False)
    view = MusicLibraryView(db_path=":memory:")
    assert not view.analyse_button.isEnabled()
    assert "analysis" in view.analyse_button.toolTip()
    view.start_analysis()
    assert not view.is_busy()
    view.close_db()


def test_analysis_job_stores_suggestions_without_writing_files(untagged_library):
    view, music = untagged_library
    bare = str(music / "bare.mp3")
    view.start_analysis(analyser=lambda path, want_bpm, want_key: (140.0, "Dm"))
    assert view.is_analysing()
    assert view.analyse_button.text() == "Stop analysis"
    view.run_pending_job()
    assert not view.is_busy()
    assert view.analyse_button.text() == "Analyse BPM/key"
    assert "estimates for 1 of 1" in view.status_label.text()
    row = next(row for row in view.table_model.rows() if row.path == bare)
    assert (row.bpm_suggestion, row.key_suggestion) == (140.0, "Dm")
    assert read_metadata(bare).bpm is None
    # Shown as "? value" in the BPM / Key / Camelot cells, amber.
    source_row = view.table_model.rows().index(row)
    cell = view.table_model.index(source_row, mlv._COLUMN_INDEX["bpm"])
    assert cell.data() == "? 140"
    assert view.table_model.index(source_row, mlv._COLUMN_INDEX["camelot"]).data() == "? 7A"
    # Nothing left to analyse on a second run.
    view.start_analysis(analyser=lambda *args: pytest.fail("should not re-analyse"))
    assert not view.is_busy()


def test_stopping_the_analysis_keeps_what_was_found(untagged_library):
    view, music = untagged_library
    _mp3(music / "bare2.mp3", title="Bare 2")
    view.start_scan()
    view.run_pending_job()
    view.start_analysis(analyser=lambda path, want_bpm, want_key: (140.0, None))
    view._job_timer.stop()  # step by hand: a whole slice would finish both
    next(view._job)  # announce
    next(view._job)  # one track
    view.stop_analysis()
    assert not view.is_busy()
    assert "stopped" in view.status_label.text()
    assert sum(row.bpm_suggestion is not None for row in view.table_model.rows()) == 1


def test_apply_analysis_suggestions_is_one_undoable_write(untagged_library):
    view, music = untagged_library
    bare, tagged = str(music / "bare.mp3"), str(music / "tagged.mp3")
    view.start_analysis(analyser=lambda path, want_bpm, want_key: (140.0, "Dm"))
    view.run_pending_job()
    _select_paths(view, [bare, tagged])
    assert view.apply_analysis_button.isEnabled()
    assert view.apply_analysis_suggestions() == 1
    tags = read_metadata(bare)
    assert (tags.bpm, tags.key) == (140.0, "Dm")
    assert read_metadata(tagged).bpm == 172.0  # tagged tracks are never overwritten
    row = next(row for row in view.table_model.rows() if row.path == bare)
    assert not row.has_analysis_suggestion  # the tag now holds the value
    view.undo_stack.undo()
    tags = read_metadata(bare)
    assert (tags.bpm, tags.key) == (None, None)
    # The estimate survives this app's own tag writes, so undo brings it back.
    row = next(row for row in view.table_model.rows() if row.path == bare)
    assert (row.bpm_suggestion, row.key_suggestion) == (140.0, "Dm")
# --- Set panel (issue #221) ----------------------------------------------


def _paths_by_title(view) -> dict[str, str]:
    return {row.title: row.path for row in view.table_model.rows()}


def test_set_panel_flags_incompatible_transitions(library):
    view, _music, _ = library
    panel = view.set_panel
    by_title = _paths_by_title(view)
    panel.insert_paths([by_title["Alpha"], by_title["Bravo"], by_title["Charlie"]])
    assert [t.status for t in panel.transitions] == ["ok", "incompatible"]
    assert panel.list.count() == 3
    assert panel.list.item(1).text().startswith("2. Yan — Bravo")
    assert panel.list.item(2).text().startswith("⚠ 3. Xu — Charlie")
    assert "BPM jump" in panel.list.item(2).toolTip()
    assert "1 incompatible transition(s)" in panel.summary_label.text()
    assert len(panel.curve.tracks) == 3
    # Dropping Charlie first leaves only compatible transitions.
    panel.list.item(2).setSelected(True)
    panel.move_selected(-5)
    assert panel.paths()[0] == by_title["Charlie"]
    assert panel.list.item(0).isSelected()
    assert [t.status for t in panel.transitions] == ["incompatible", "ok"]


def test_set_panel_drag_payload_and_internal_reorder(library):
    view, _music, _ = library
    panel = view.set_panel
    indexes = [view.table_model.index(row, 0) for row in range(view.table_model.rowCount())]
    mime = view.table_model.mimeData(indexes)
    paths = decode_paths(mime.data(SET_TRACKS_MIME).data())
    assert paths == [row.path for row in view.table_model.rows()]
    assert view.table_model.flags(indexes[0]) & Qt.ItemFlag.ItemIsDragEnabled
    panel.list.pathsDropped.emit(paths[:2], 0)
    panel.list.pathsDropped.emit([paths[2], paths[0]], 1)
    assert panel.paths() == [paths[0], paths[2], paths[1]]
    # An internal drag reorders the widget; the panel follows its order.
    item = panel.list.takeItem(0)
    panel.list.insertItem(2, item)
    panel.list.orderChanged.emit()
    assert panel.paths() == [paths[2], paths[1], paths[0]]


def test_set_draft_survives_reopen_and_saves_as_playlist(tmp_path, monkeypatch):
    music = tmp_path / "music"
    a = _mp3(music / "a.mp3", title="Alpha", bpm="140", key="Am")
    b = _mp3(music / "b.mp3", title="Bravo", bpm="141", key="Em")
    db_path = tmp_path / "library.sqlite3"
    view = MusicLibraryView(db_path=db_path)
    view.add_root(music)
    view.start_scan()
    view.run_pending_job()
    view.set_panel.insert_paths([str(b), str(a)])
    view.set_panel.tolerance_spin.setValue(3.0)
    view.close_db()

    reopened = MusicLibraryView(db_path=db_path)
    reopened.ensure_open()
    panel = reopened.set_panel
    assert panel.paths() == [str(b), str(a)]
    assert panel.tolerance_spin.value() == 3.0
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Friday", True))
    panel.save_button.click()
    record = next(p for p in reopened.db.list_playlists() if p.name == "Friday")
    assert record.source == "set"
    assert reopened.db.playlist_paths(record.id) == [str(b), str(a)]
    # Loading a playlist replaces the draft.
    panel.clear()
    assert panel.paths() == []
    panel.load_button.click()
    assert panel.paths() == [str(b), str(a)]
    crate = tmp_path / "out.crate"
    panel.export_crate(str(crate))
    assert [Path(p).name for p in parse_crate(crate)] == ["b.mp3", "a.mp3"]
    reopened.close_db()
