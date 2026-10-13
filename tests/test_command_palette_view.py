"""The command palette popup and how MainWindow runs its entries (issue #222)."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenuBar

from djmidi.command_palette import (
    KIND_ACTION,
    KIND_FUNCTION,
    KIND_TAB,
    PaletteEntry,
    PaletteIndex,
)
from djmidi.gui.command_palette import CommandPaletteDialog, menu_entries
from djmidi.gui.main_window import MainWindow
from djmidi.parser import parse_file

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_menu_entries_flatten_enabled_leaves_with_their_path():
    bar = QMenuBar()
    file_menu = bar.addMenu("&File")
    file_menu.addAction(QAction("&Open Mapping...", bar))
    disabled = QAction("&Save", bar)
    disabled.setEnabled(False)
    file_menu.addAction(disabled)
    file_menu.addSeparator()
    export = file_menu.addMenu("&Export")
    export.addAction(QAction("Cheat Sheet (PDF)...", bar))
    toggle = QAction("Performance Mode", bar, checkable=True)
    skipped = QAction("Command Palette...", bar)
    view = bar.addMenu("&View")
    view.addAction(toggle)
    view.addAction(skipped)

    entries = menu_entries(bar, skip={skipped})
    assert [(e.title, e.detail) for e in entries] == [
        ("Open Mapping", "File"),
        ("Cheat Sheet (PDF)", "File › Export"),
        ("Performance Mode (off)", "View"),
    ]
    assert all(e.kind == KIND_ACTION for e in entries)


def test_dialog_is_keyboard_driven():
    entries = [PaletteEntry(KIND_ACTION, name, payload=name) for name in ("Alpha", "Beta", "Gamma")]
    dialog = CommandPaletteDialog(PaletteIndex(entries))
    chosen = []
    dialog.entryChosen.connect(chosen.append)
    dialog.show()
    assert dialog.result_count() == 3
    assert dialog.current_entry().payload == "Alpha"
    QTest.keyClick(dialog.search_field, Qt.Key.Key_Down)
    QTest.keyClick(dialog.search_field, Qt.Key.Key_Down)
    QTest.keyClick(dialog.search_field, Qt.Key.Key_Down)  # clamps at the end
    assert dialog.current_entry().payload == "Gamma"
    QTest.keyClick(dialog.search_field, Qt.Key.Key_Up)
    assert dialog.current_entry().payload == "Beta"
    QTest.keyClicks(dialog.search_field, "gam")
    assert dialog.result_count() == 1
    QTest.keyClick(dialog.search_field, Qt.Key.Key_Return)
    assert [entry.payload for entry in chosen] == ["Gamma"]
    assert dialog.chosen_entry().payload == "Gamma"
    assert not dialog.isVisible()


def test_dialog_says_when_nothing_matches():
    dialog = CommandPaletteDialog(PaletteIndex([PaletteEntry(KIND_ACTION, "Alpha")]))
    dialog.set_query("zzz")
    assert dialog.result_count() == 0
    assert dialog.current_entry() is None
    dialog.choose_current()  # nothing to run, stays harmless
    assert dialog.chosen_entry() is None
    assert "Nothing matches" in dialog.hint.text()


def _window() -> MainWindow:
    window = MainWindow()
    window.resize(1100, 700)
    window.show()
    QApplication.processEvents()
    return window


def test_ctrl_k_action_is_in_the_view_menu():
    window = _window()
    action = window._command_palette_action
    assert action.shortcut().toString() == "Ctrl+K"
    assert action.shortcutContext() == Qt.ShortcutContext.ApplicationShortcut
    action.trigger()
    QApplication.processEvents()
    dialog = window._command_palette
    assert dialog.isVisible()
    # The palette doesn't list itself.
    dialog.set_query("command palette")
    assert all(entry.payload is not action for entry in (dialog.entry_at(i) for i in range(dialog.result_count())))
    dialog.close()


def test_palette_switches_tabs_and_runs_menu_actions():
    window = _window()
    dialog = window.open_command_palette("by deck")
    first = dialog.current_entry()
    assert first.kind == KIND_TAB
    dialog.choose_current()
    assert window.left_tabs.currentIndex() == window._tab_indexes["deck"]

    dialog = window.open_command_palette("performance mode")
    assert dialog.current_entry().payload is window._performance_mode_action
    dialog.choose_current()
    assert window._performance_mode_action.isChecked()
    window._performance_mode_action.setChecked(False)


def test_palette_disabled_actions_appear_once_a_mapping_is_loaded():
    window = _window()
    dialog = window.open_command_palette("cheat sheet")
    assert not any(dialog.entry_at(i).kind == KIND_ACTION for i in range(dialog.result_count()))
    dialog.close()
    window.config = parse_file(FIXTURE)
    window.current_path = FIXTURE
    window._load_tree()
    window._refresh_file_actions()  # what the real open path does after loading
    dialog = window.open_command_palette("cheat sheet")
    assert dialog.current_entry().payload is window._cheat_sheet_action
    dialog.close()


def test_palette_selects_a_mapping_function():
    window = _window()
    window.config = parse_file(FIXTURE)
    window.current_path = FIXTURE
    window._load_tree()
    QApplication.processEvents()
    dialog = window.open_command_palette("loop roll deck 2 slot 3")
    entry = dialog.current_entry()
    assert entry.kind == KIND_FUNCTION
    dialog.choose_current()
    QApplication.processEvents()
    assert window.left_tabs.currentIndex() in {
        window._tab_indexes[key] for key in ("channel", "deck", "controller")
    }
    assert "Loop roll" in window.statusBar().currentMessage()


def test_palette_has_no_tracks_until_the_library_is_open():
    window = _window()
    assert window.music_library_view._db is None
    assert window._palette_track_entries() == []


def test_palette_opens_a_library_track_even_when_filtered_out():
    from djmidi.library import workspace
    from djmidi.library.metadata import TrackMetadata

    window = _window()
    library = window.music_library_view
    library.ensure_open()
    rows = [
        workspace.LibraryRow(1, "/music/a.mp3", False, TrackMetadata(title="Zebra Dub", artist="Ana", bpm=140.0), "8A", None),
        workspace.LibraryRow(2, "/music/b.mp3", False, TrackMetadata(title="Other", artist="Bob"), None, None),
    ]
    library.table_model.set_rows(rows)
    library.filter_edit.setText("Bob")  # hides the track we want
    QApplication.processEvents()
    dialog = window.open_command_palette("zebra")
    entry = dialog.current_entry()
    assert entry.title == "Ana – Zebra Dub"
    assert "140 BPM" in entry.detail and "8A" in entry.detail
    dialog.choose_current()
    assert window.left_tabs.currentIndex() == window._tab_indexes["library"]
    assert library._current_row().path == "/music/a.mp3"
    # Rows unchanged: the entries are cached, not rebuilt.
    assert window._palette_track_entries() is window._palette_track_entries()
