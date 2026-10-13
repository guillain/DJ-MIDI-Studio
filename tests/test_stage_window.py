"""Stage Mode window (issue #230) and its View-menu toggle in MainWindow."""

from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from djmidi import catalog
from djmidi.gui.main_window import MainWindow
from djmidi.gui.stage_window import StageWindow
from djmidi.midi_io import MidiEvent


def _press_escape(widget) -> None:
    target = QApplication.focusWidget() or widget
    for kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
        QApplication.sendEvent(target, QKeyEvent(kind, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def test_stage_window_shows_events_newest_first():
    window = StageWindow(config_provider=lambda: None, max_lines=2)
    try:
        for note in ("1", "2", "3"):
            window.add_event(MidiEvent("in", "16", "Note On", note, "127", 0.0), [])
        assert window.log_lines() == ["IN · Ch 16 Note On 3 · ON", "IN · Ch 16 Note On 2 · ON"]
        assert window._latest_label.text() == "IN · Ch 16 Note On 3 · ON"
        assert window._log_list.count() == 2
    finally:
        window.close()


def test_stage_window_esc_closes_it_and_emits_closed():
    window = StageWindow(config_provider=lambda: None)
    closed = []
    window.closed.connect(lambda: closed.append(True))
    window.show()
    window.activateWindow()
    QApplication.processEvents()
    _press_escape(window)
    assert closed == [True]
    assert not window.isVisible()


def test_stage_window_is_high_contrast():
    window = StageWindow(config_provider=lambda: None)
    try:
        assert "#000000" in window.styleSheet()
        assert window.objectName() == "stageWindow"
    finally:
        window.close()


def test_stage_mode_action_opens_and_closes_the_window():
    window = MainWindow()
    try:
        action = window._stage_mode_action
        assert action.isCheckable() and not action.isChecked()
        with patch.object(window.live_monitor_view, "ensure_monitoring_started") as start:
            action.setChecked(True)
        start.assert_called_once()
        stage = window._stage_window
        assert stage is not None and stage.isVisible()
        assert stage.isFullScreen() or stage.windowState() & Qt.WindowState.WindowFullScreen
        assert stage.emulator_view in window._emulator_views()

        action.setChecked(False)
        QApplication.processEvents()
        assert window._stage_window is None
    finally:
        window.close()


def test_closing_the_stage_window_unchecks_the_action():
    window = MainWindow()
    try:
        with patch.object(window.live_monitor_view, "ensure_monitoring_started"):
            window._stage_mode_action.setChecked(True)
        window._stage_window.close()
        QApplication.processEvents()
        assert window._stage_window is None
        assert not window._stage_mode_action.isChecked()
    finally:
        window.close()


def test_stage_window_starts_on_the_first_emulator_controller():
    window = MainWindow()
    try:
        controller = catalog.CONTROLLER_NAMES[-1]
        window._create_emulator_instance(controller)
        with patch.object(window.live_monitor_view, "ensure_monitoring_started"):
            window._stage_mode_action.setChecked(True)
        assert window._stage_window.emulator_view.current_controller() == controller
    finally:
        window.close()


def test_live_events_reach_the_stage_monitor_and_emulator():
    window = MainWindow()
    try:
        with patch.object(window.live_monitor_view, "ensure_monitoring_started"):
            window._stage_mode_action.setChecked(True)
        stage = window._stage_window
        hit = catalog.ControlInfo("XDJ-XZ", "DECK", "PLAY/PAUSE", "NOTE", ("1",), "11")
        with (
            patch.object(catalog, "lookup", return_value=[hit]),
            patch.object(stage.emulator_view, "flash_live_hit") as flash,
        ):
            window._on_live_midi_event(MidiEvent("in", "1", "Note On", "11", "127", 0.0, "XDJ-XZ"))
        assert stage.log_lines() == ["IN · XDJ-XZ PLAY/PAUSE · ON"]
        flash.assert_called_once_with(hit)
    finally:
        window.close()


def test_jog_ticks_stay_out_of_the_stage_monitor():
    window = MainWindow()
    try:
        with patch.object(window.live_monitor_view, "ensure_monitoring_started"):
            window._stage_mode_action.setChecked(True)
        with patch("djmidi.gui.main_window.jog_mod.jog_cell_keys_for_event", return_value=[("X", "", "Jog wheel")]):
            window._on_live_midi_event(MidiEvent("in", "1", "Control Change", "34", "65", 0.0))
        assert window._stage_window.log_lines() == []
    finally:
        window.close()


def test_main_window_close_also_closes_the_stage_window():
    window = MainWindow()
    with patch.object(window.live_monitor_view, "ensure_monitoring_started"):
        window._stage_mode_action.setChecked(True)
    closed = []
    window._stage_window.closed.connect(lambda: closed.append(True))
    window.close()
    QApplication.processEvents()
    assert closed == [True]
    assert window._stage_window is None


def test_stage_window_has_a_help_button():
    from PySide6.QtWidgets import QPushButton

    window = StageWindow(config_provider=lambda: None)
    try:
        assert any(button.property("help") for button in window.findChildren(QPushButton))
    finally:
        window.close()
