from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from djmidi.gui.main_window import MainWindow


def test_settings_menu_is_removed_in_favor_of_a_corner_icon():
    window = MainWindow()
    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert not any("Settings" in title for title in menu_titles)


def test_preferences_corner_widget_opens_preferences():
    window = MainWindow()
    button = window.menuBar().cornerWidget(Qt.Corner.TopRightCorner)
    assert button is not None

    window._on_preferences = Mock()
    button.click()
    window._on_preferences.assert_called_once()


def test_dock_reduce_toggle_hides_and_restores_the_widget():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    dock = window._tool_docks["monitor"]
    dock.show()
    widget = dock.widget()

    dock._dj_reduce_action.trigger()
    assert not widget.isVisible()
    assert dock._dj_reduced is True

    dock._dj_reduce_action.trigger()
    assert widget.isVisible()
    assert dock._dj_reduced is False
    window.close()


def test_dock_maximize_toggle_floats_and_restores():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    dock = window._tool_docks["routing"]
    dock.show()
    assert not dock.isFloating()

    dock._dj_maximize_action.trigger()
    assert dock.isFloating()
    assert dock._dj_maximized is True

    dock._dj_maximize_action.trigger()
    assert dock._dj_maximized is False
    window.close()


def test_snap_dock_to_area_moves_it_and_clears_floating():
    window = MainWindow()
    dock = window._tool_docks["clock"]
    dock.setFloating(True)

    window._snap_dock_to_area(dock, Qt.DockWidgetArea.LeftDockWidgetArea)

    assert not dock.isFloating()
    assert window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea


def test_snap_dock_clears_reduced_and_maximized_state():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    dock = window._tool_docks["metronome"]
    dock.show()
    dock._dj_reduce_action.trigger()
    dock._dj_maximize_action.trigger()
    assert dock._dj_reduced is True
    assert dock._dj_maximized is True

    window._snap_dock_to_area(dock, Qt.DockWidgetArea.BottomDockWidgetArea)

    assert dock._dj_reduced is False
    assert dock._dj_maximized is False
    assert dock.widget().isVisible()
    window.close()


def test_emulator_dock_also_gets_window_control_actions():
    window = MainWindow()
    dock = window._create_emulator_instance()
    assert hasattr(dock, "_dj_reduce_action")
    assert hasattr(dock, "_dj_maximize_action")
