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
    window = StageWindow(config_provider=lambda: None)
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
