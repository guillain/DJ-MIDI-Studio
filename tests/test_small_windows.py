"""Issue #282: small-window audit of the windows added in v0.48.90–v0.48.103.

Issue #19's rule, checked the way `test_no_button_is_squeezed_below_its_minimum`
checks the Music Library: at its default size and dragged to its minimum,
no window crushes a control below its own minimum, clips a word-wrapped
label, collapses its main table/list to a sliver, or needs more than a
900x600 screen.
"""

from contextlib import contextmanager
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.theme import apply_theme
from djmidi.gui.window_size import (
    fit_size,
    fit_to_screen,
    keep_wrapped_text_visible,
    wrapped_minimum,
)

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"

# A 900x600 screen; a window's minimum must fit in it.
SMALL_SCREEN = (900, 600)
# Smallest height a window's main table/list/chart keeps at minimum size.
USABLE_VIEW_HEIGHT = 80


def test_fit_size_caps_to_the_available_screen_share():
    assert fit_size((1100, 640), (1000, 650)) == (920, 585)
    assert fit_size((560, 420), (1000, 650)) == (560, 420)
    assert fit_size((900, 520), None) == (900, 520)
    assert fit_size((900, 520), (1000, 1000), width_ratio=0.5, height_ratio=1.0) == (500, 520)


def test_fit_to_screen_never_exceeds_the_screen():
    widget = QWidget()
    fit_to_screen(widget, 5000, 5000)
    available = widget.screen().availableGeometry()
    assert widget.width() <= available.width()
    assert widget.height() <= available.height()


def test_wrapped_text_raises_the_minimum_height():
    window = QWidget()
    layout = QVBoxLayout(window)
    label = QLabel("A long explanation that has to wrap over several lines in a narrow window. " * 3)
    label.setWordWrap(True)
    layout.addWidget(label)
    layout.addWidget(QComboBox())
    window.setMinimumWidth(200)
    keep_wrapped_text_visible(window)
    window.show()
    QApplication.processEvents()
    width, height = wrapped_minimum(window, (200, 0))
    assert window.minimumWidth() == width >= 200
    assert window.minimumHeight() == height >= layout.totalMinimumHeightForWidth(width)
    assert height > layout.totalMinimumSize().height()
    window.close()


def test_wrapped_minimum_is_none_without_wrapping():
    window = QWidget()
    QVBoxLayout(window).addWidget(QComboBox())
    assert wrapped_minimum(window) is None
    assert wrapped_minimum(QWidget()) is None


# --- every window of the batch --------------------------------------------


def _in_scroll_area(widget: QWidget) -> bool:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return True
        parent = parent.parentWidget()
    return False


def _layout_problems(window: QWidget) -> list[str]:
    problems = []
    for widget in window.findChildren(QWidget):
        if not widget.isVisible() or _in_scroll_area(widget):
            continue
        if isinstance(widget, QLabel) and widget.wordWrap() and widget.text():
            needed = widget.heightForWidth(widget.width())
            if widget.height() < needed - 2:
                problems.append(f"clipped label {widget.text()[:40]!r}: {widget.height()} < {needed}")
        elif isinstance(widget, (QAbstractButton, QComboBox, QLineEdit, QAbstractSpinBox)):
            if isinstance(widget, QLineEdit) and isinstance(widget.parentWidget(), QAbstractSpinBox):
                continue  # a spin box's own editor; the spin box is checked
            hint = widget.minimumSizeHint()
            if widget.width() < hint.width() - 1 or widget.height() < hint.height() - 1:
                name = widget.text() if hasattr(widget, "text") else widget.objectName()
                problems.append(f"squeezed {type(widget).__name__} {name!r}: {widget.size().toTuple()} < {hint.toTuple()}")
    return problems


def _wizard():
    from djmidi.gui.first_run_wizard import FirstRunWizard

    return FirstRunWizard(lambda: ["PIONEER DDJ-XP2", "Mystery Box"], home=Path("/nonexistent-home"))


def _layer_map():
    from djmidi.gui.layer_map_dialog import LayerMapDialog
    from djmidi.parser import parse_file

    config = parse_file(FIXTURE)
    return LayerMapDialog(lambda: config, [("DDJ-XP2", 64), ("XDJ-XZ", 16)], "DDJ-XP2")


def _live_ready():
    from djmidi.gui.live_ready_dialog import LiveReadyDialog
    from djmidi.live_ready import check_live_ready
    from djmidi.parser import parse_file

    return LiveReadyDialog(check_live_ready(parse_file(FIXTURE)))


def _latency():
    from djmidi.gui.midi_latency_dialog import MidiLatencyDialog

    @contextmanager
    def ports(_output, _input):
        yield (lambda *_args: None), list

    return MidiLatencyDialog(
        port_pair_factory=ports,
        start_thread=lambda _target: None,
        list_outputs=lambda: ["IAC Driver Bus 1", "DDJ-XP2"],
        list_inputs=lambda: ["DDJ-XP2"],
    )


def _stats():
    from djmidi.gui.library_stats_dialog import LibraryStatsDialog
    from djmidi.library.stats import compute_library_stats

    return LibraryStatsDialog(compute_library_stats([]), "all indexed tracks")


def _smart_playlist():
    from djmidi.gui.music_library_view import SmartPlaylistDialog
    from djmidi.library.smart_playlist import SmartRules

    return SmartPlaylistDialog("Mine", SmartRules(), has_history=False)


def _rename():
    from djmidi.gui.rename_files_dialog import RenameFilesDialog
    from djmidi.library.rename import RenamePlan

    return RenameFilesDialog(lambda template: RenamePlan(template, ()), "{artist} - {title}")


def _change_history():
    from djmidi.gui.change_history_dialog import ChangeHistoryDialog
    from djmidi.library.db import LibraryDB

    return ChangeHistoryDialog(LibraryDB(":memory:"))


def _palette():
    from djmidi.command_palette import KIND_ACTION, PaletteEntry, PaletteIndex
    from djmidi.gui.command_palette import CommandPaletteDialog

    return CommandPaletteDialog(PaletteIndex([PaletteEntry(KIND_ACTION, name) for name in ("Alpha", "Beta")]))


def _profile_library():
    from djmidi.catalog.library import LIBRARY_DIR, list_library_profiles
    from djmidi.gui.profile_library_dialog import ProfileLibraryDialog

    return ProfileLibraryDialog(list_library_profiles(LIBRARY_DIR), Path("/nonexistent-controllers"))


def _geometry_editor():
    from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register
    from djmidi.gui.geometry_editor import GeometryEditorDialog

    name = "Small-window profile"
    register(
        ControllerDefinition(name=name, static_entries=[ControlInfo(name, "Deck", "Sync", "NOTE", ("1",), "88")]),
        replace=True,
    )
    return GeometryEditorDialog(name, Path("/nonexistent/profile.json"))


def _profile_check():
    from djmidi.gui.profile_check_dialog import ProfileCheckDialog

    return ProfileCheckDialog(["DDJ-XP2", "XDJ-XZ"], ["PIONEER DDJ-XP2"], initial="DDJ-XP2")


def _route_transform():
    from djmidi.gui.midi_route_transform_dialog import MidiRouteTransformDialog
    from djmidi.midi_router import CC, NOTE, MidiValueTransform, RemapRule

    return MidiRouteTransformDialog(MidiValueTransform(remaps=(RemapRule(NOTE, 1, 40, CC, 2, 7),)))


def _deck_copy():
    from djmidi.gui.deck_copy_dialog import DeckCopyDialog
    from djmidi.parser import parse_file

    return DeckCopyDialog(parse_file(FIXTURE))


def _snapshots():
    from datetime import UTC, datetime

    from djmidi.gui.snapshots_dialog import SnapshotsDialog
    from djmidi.snapshots import Snapshot

    snapshot = Snapshot("before the club gig", datetime(2026, 10, 1, tzinfo=UTC).isoformat(), "a.xml", "serato",
                        FIXTURE)  # fmt: skip
    return SnapshotsDialog("mapping.xml", lambda: [snapshot])


def _mixxx_export():
    from djmidi.gui.mixxx_export_dialog import MixxxExportDialog

    return MixxxExportDialog(["DDJ-FLX4", "XDJ-XZ"], initial="DDJ-FLX4")


WINDOWS = {
    "first-run wizard": _wizard,
    "layer map": _layer_map,
    "ready for live": _live_ready,
    "midi latency": _latency,
    "library statistics": _stats,
    "smart playlist": _smart_playlist,
    "rename files": _rename,
    "change history": _change_history,
    "command palette": _palette,
    "controller profile library": _profile_library,
    "geometry editor": _geometry_editor,
    "profile check": _profile_check,
    "route transform": _route_transform,
    "deck copy": _deck_copy,
    "snapshots": _snapshots,
    "mixxx export": _mixxx_export,
}


def _pages(window):
    """Each page of a wizard (one 'page' otherwise)."""
    from PySide6.QtWidgets import QWizard

    if not isinstance(window, QWizard):
        yield
        return
    for _page_id in window.pageIds():
        yield
        window.next()


@pytest.mark.parametrize("name", list(WINDOWS))
def test_window_is_usable_at_default_and_minimum_size(name):
    apply_theme(QApplication.instance())
    window = WINDOWS[name]()
    window.show()
    try:
        QApplication.processEvents()
        available = window.screen().availableGeometry()
        assert window.width() <= available.width() and window.height() <= available.height()
        for _page in _pages(window):
            for size in (window.size().toTuple(), (1, 1)):
                window.resize(*size)
                QApplication.processEvents()
                QApplication.processEvents()
                assert _layout_problems(window) == [], (name, size)
                views = [
                    view
                    for view in window.findChildren(QAbstractItemView)
                    if view.isVisible() and not isinstance(view, QHeaderView)
                ]
                assert all(view.height() >= USABLE_VIEW_HEIGHT for view in views), (name, size)
            minimum = window.minimumSize()
            assert minimum.width() <= SMALL_SCREEN[0] and minimum.height() <= SMALL_SCREEN[1], (name, minimum)
    finally:
        window.close()


@pytest.mark.parametrize("size", [(1280, 820), (1000, 650), (900, 600), (1, 1)])
def test_stage_window_is_usable_at_small_sizes(size):
    from djmidi.gui.stage_window import StageWindow

    apply_theme(QApplication.instance())
    from djmidi.library.set_prep import SetTrack, analyze_set

    tracks = [
        SetTrack("/a.mp3", "A long track title, extended mix", "Some artist", 124.0, "8A", 5),
        SetTrack("/b.mp3", "Next one", "Other artist", 140.0, "3B"),
    ]
    window = StageWindow(config_provider=lambda: None, set_provider=lambda: (tracks, analyze_set(tracks)))
    window.show()
    try:
        window.resize(*size)
        QApplication.processEvents()
        QApplication.processEvents()
        assert _layout_problems(window) == [], size
        assert window.emulator_view.width() >= 400 and window.emulator_view.height() >= 300
        minimum = window.minimumSize()
        assert minimum.width() <= SMALL_SCREEN[0] and minimum.height() <= SMALL_SCREEN[1]
    finally:
        window.close()


# --- issue #290: the same windows in French, plus the tab bars ------------


@pytest.fixture
def french():
    """The French catalogue installed, as `gui.app.run` does at launch."""
    from PySide6.QtCore import QTranslator

    from djmidi import i18n

    app = QApplication.instance()
    translator = QTranslator()
    assert translator.load(str(i18n.translation_file("fr")))
    app.installTranslator(translator)
    try:
        yield
    finally:
        app.removeTranslator(translator)


@pytest.mark.parametrize("name", list(WINDOWS))
def test_window_is_usable_in_french(name, french):
    # Longer French labels clipped the wizard's checkbox and pushed Layer
    # Map's minimum past a 900 px screen; only checked on macOS before.
    test_window_is_usable_at_default_and_minimum_size(name)


@pytest.mark.parametrize("language", ["en", "fr"])
def test_preferences_minimum_ignores_the_workspace_path_length(language, monkeypatch, request):
    from djmidi import user_paths
    from djmidi.gui.preferences_dialog import PreferencesDialog
    from djmidi.plugins.preferences import PluginPreferences

    if language == "fr":
        request.getfixturevalue("french")
    # A real path can be long (a network home, a nested Documents folder):
    # it once set the dialog's minimum to 1118 px (1243 in French).
    long_path = Path("/Users/someone-with-a-long-name/Library/Mobile Documents/" + "nested-folder/" * 8)
    monkeypatch.setattr(user_paths, "workspace_dir", lambda: long_path)
    apply_theme(QApplication.instance())
    dialog = PreferencesDialog(PluginPreferences())
    dialog.show()
    try:
        dialog.resize(1, 1)
        QApplication.processEvents()
        minimum = dialog.minimumSizeHint().expandedTo(dialog.minimumSize())
        assert minimum.width() <= SMALL_SCREEN[0], minimum
        assert _layout_problems(dialog) == []
    finally:
        dialog.close()


def test_tab_titles_are_never_elided(french):
    """macOS cut the main tabs to "Pa…" / "Pa…" in French and the dashboard's
    controller tabs to "DD…": every crowded tab bar keeps whole titles."""
    from PySide6.QtCore import Qt

    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        tab_widgets = [
            window.left_tabs,
            window.introduction_view._controller_tabs,
            window.music_library_view.side_tabs,
        ]
        for tabs in tab_widgets:
            assert tabs.elideMode() == Qt.TextElideMode.ElideNone
        assert window.left_tabs.usesScrollButtons()
        assert window.introduction_view._controller_tabs.usesScrollButtons()
        # The side tabs grow instead (their panel is in a scroll area).
        assert not window.music_library_view.side_tabs.usesScrollButtons()
        assert window.left_tabs.tabText(window._tab_indexes["library"]) == "Bibliothèque"
    finally:
        window.close()
