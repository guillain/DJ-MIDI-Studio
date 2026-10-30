"""Music Library tab: smart playlists (issue #259)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TBPM, TCON, TIT2, TKEY
from PySide6.QtWidgets import QDialog

from djmidi.gui import music_library_view as mlv
from djmidi.gui.music_library_view import MusicLibraryView, SmartPlaylistDialog
from djmidi.library import history
from djmidi.library.serato_library import parse_crate
from djmidi.library.smart_playlist import SORT_BPM, SORT_PATH, SOURCE_SMART, SmartRules


def _mp3(path: Path, **tags: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((frame + b"\x00" * (417 - len(frame))) * 20)
    id3 = ID3()
    frames = {"title": TIT2, "genre": TCON, "bpm": TBPM, "key": TKEY}
    for name, value in tags.items():
        id3.add(frames[name](encoding=3, text=[value]))
    id3.save(path)
    return path


@pytest.fixture
def library(tmp_path):
    music = tmp_path / "music"
    _mp3(music / "Tek" / "Tribe" / "a.mp3", title="Alpha", bpm="172", key="Am")
    _mp3(music / "Tek" / "Tribe" / "b.mp3", title="Bravo", bpm="175", key="Em")
    _mp3(music / "misc" / "c.mp3", title="Charlie", bpm="80", key="C")
    view = MusicLibraryView(db_path=":memory:")
    view.add_root(music)
    view.start_scan()
    view.run_pending_job()
    yield view, music, tmp_path
    view.close_db()


def _names(paths):
    return [Path(p).name for p in paths]


def test_new_smart_playlist_is_evaluated_and_listed(library, monkeypatch):
    view, _music, _ = library
    rules = SmartRules(category="Tek", bpm_min=170, bpm_max=180, camelot_key="8A", sort=SORT_PATH)
    monkeypatch.setattr(view, "_ask_smart_rules", lambda name, current: ("Fast Tek", rules))
    view._on_new_smart_clicked()
    playlist_id = view.selected_playlist_id()
    record = next(p for p in view.db.list_playlists() if p.id == playlist_id)
    assert (record.name, record.source) == ("Fast Tek", SOURCE_SMART)
    # 8A = Am; Em (9A) is compatible with it.
    assert _names(view.db.playlist_paths(playlist_id)) == ["a.mp3", "b.mp3"]
    assert view.playlist_tracks.count() == 2
    assert "BPM 170–180" in view.playlist_list.currentItem().toolTip()


def test_scan_refreshes_smart_playlists(library):
    view, music, _ = library
    playlist_id = view.create_smart_playlist("Fast", SmartRules(bpm_min=170, sort=SORT_BPM))
    assert _names(view.db.playlist_paths(playlist_id)) == ["a.mp3", "b.mp3"]
    _mp3(music / "new" / "d.mp3", title="Delta", bpm="171")
    view.start_scan()
    view.run_pending_job()
    assert _names(view.db.playlist_paths(playlist_id)) == ["d.mp3", "a.mp3", "b.mp3"]
    assert "1 smart playlist(s) refreshed" in view.status_label.text()


def test_edit_rules_renames_and_re_evaluates(library, monkeypatch):
    view, _music, _ = library
    playlist_id = view.create_smart_playlist("Fast", SmartRules(bpm_min=170))
    seen = []

    def ask(name, current):
        seen.append((name, current))
        return "Slow", SmartRules(bpm_max=100)

    monkeypatch.setattr(view, "_ask_smart_rules", ask)
    view._on_edit_smart_clicked()
    assert seen == [("Fast", SmartRules(bpm_min=170).normalized())]
    assert _names(view.db.playlist_paths(playlist_id)) == ["c.mp3"]
    assert view.playlist_list.currentItem().text().startswith("Slow")
    assert view.playlist_tracks.count() == 1


def test_edit_needs_a_smart_playlist(library, monkeypatch):
    view, _music, _ = library
    view.create_playlist("Hand-made", [])
    monkeypatch.setattr(view, "_ask_smart_rules", lambda *a: pytest.fail("dialog shown"))
    view._on_edit_smart_clicked()
    assert view.status_label.text() == "Select a smart playlist first."


def test_loaded_history_feeds_the_not_played_rule(library, monkeypatch):
    view, music, _ = library
    playlist_id = view.create_smart_playlist("Rested", SmartRules(not_played_days=90, sort=SORT_PATH))
    assert len(view.db.playlist_paths(playlist_id)) == 3
    recent = datetime.now(UTC) - timedelta(days=3)
    session = history.HistorySession(
        "serato", "1", [history.PlayedEntry(str(music / "Tek" / "Tribe" / "a.mp3"), recent, "serato", "1")]
    )
    monkeypatch.setattr(history, "read_history", lambda dirs: [session])
    view.load_history({"serato": "/unused"})
    assert view.db.has_play_stats()
    assert _names(view.db.playlist_paths(playlist_id)) == ["b.mp3", "c.mp3"]
    # An empty read keeps the stored counts.
    monkeypatch.setattr(history, "read_history", lambda dirs: [])
    view.load_history({"serato": "/unused"})
    assert view.db.has_play_stats()


def test_smart_playlist_exports_like_any_playlist(library):
    view, _music, tmp_path = library
    playlist_id = view.create_smart_playlist("Fast", SmartRules(bpm_min=170, sort=SORT_PATH))
    crate = tmp_path / "out" / "Fast.crate"
    crate.parent.mkdir()
    view.export_playlist_as_crate(playlist_id, str(crate))
    assert [Path(p).name for p in parse_crate(crate)] == ["a.mp3", "b.mp3"]


def test_refresh_button_and_delete(library):
    view, _music, _ = library
    view._on_refresh_smart_clicked()
    assert view.status_label.text() == "No smart playlist to refresh."
    playlist_id = view.create_smart_playlist("Fast", SmartRules(bpm_min=170))
    view._on_refresh_smart_clicked()
    assert view.status_label.text() == "Refreshed 1 smart playlist(s)."
    view.db.delete_playlist(playlist_id)
    assert view.db.list_smart_rules() == {}


def test_dialog_round_trips_rules(library):
    view, _music, _ = library
    rules = SmartRules(
        category="Tek", genre="tek", text="alp", bpm_min=170, bpm_max=180, camelot_key="8A",
        key_compatible=False, not_played_days=90, sort=SORT_BPM, limit=20,
    ).normalized()
    dialog = SmartPlaylistDialog("Mine", rules, has_history=False, parent=view)
    assert dialog.name() == "Mine"
    assert dialog.rules() == rules
    assert dialog.history_note.text().startswith("No DJ history loaded")
    dialog.name_edit.setText("  ")
    assert not dialog._ok_button.isEnabled()
    empty = SmartPlaylistDialog("x", SmartRules(), has_history=True, parent=view)
    assert empty.rules() == SmartRules().normalized()


def test_ask_smart_rules_cancel(library, monkeypatch):
    view, _music, _ = library
    monkeypatch.setattr(mlv.SmartPlaylistDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    view._on_new_smart_clicked()
    assert view.db.list_smart_rules() == {}
    monkeypatch.setattr(mlv.SmartPlaylistDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    view._on_new_smart_clicked()
    assert len(view.db.list_smart_rules()) == 1


def test_export_all_smart_playlists_remembers_its_choices(library, monkeypatch):
    from djmidi.gui.smart_export_dialog import SmartExportDialog
    from djmidi.library.smart_playlist import SmartExportOptions, load_export_options

    view, _music, tmp_path = library
    view._on_export_smart_clicked()  # none yet: just says so
    assert "No smart playlist" in view.status_label.text()
    monkeypatch.setattr(view, "_ask_smart_rules", lambda name, current: ("Fast", SmartRules(bpm_min=170)))
    view._on_new_smart_clicked()
    out = tmp_path / "exports"
    chosen = SmartExportOptions(str(out), serato=True, traktor=False)

    class _Accepting:
        def __init__(self, options, count, parent):
            assert count == 1 and options == SmartExportOptions()

        def exec(self):
            return QDialog.DialogCode.Accepted

        def options(self):
            return chosen

    view.smart_export_dialog_factory = _Accepting
    view._on_export_smart_clicked()
    assert _names(parse_crate(out / "Fast.crate")) == ["a.mp3", "b.mp3"]
    assert "1 smart playlist(s): 1 file(s)" in view.status_label.text()
    assert load_export_options(view.db) == chosen

    dialog = SmartExportDialog(chosen, 1, choose_folder=lambda start: str(tmp_path / "other"))
    assert dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()
    dialog.serato_box.setChecked(False)
    assert not dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()
    dialog.traktor_box.setChecked(True)
    dialog._browse()
    assert dialog.options() == SmartExportOptions(str(tmp_path / "other"), serato=False, traktor=True)
    dialog.close()
