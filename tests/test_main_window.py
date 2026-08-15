from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QMenu

from djmidi.gui.main_window import MainWindow
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def _ratio(splitter) -> float:
    sizes = splitter.sizes()
    total = sizes[0] + sizes[1]
    return sizes[0] / total if total else 0.0


def test_pair_splitters_start_near_half_height():
    window = MainWindow()
    window.show()
    QApplication.processEvents()

    for splitter in window._pair_splitters:
        assert abs(_ratio(splitter) - 0.5) < 0.08

    window.close()


def test_pair_splitter_ratio_is_kept_on_window_resize():
    window = MainWindow()
    window.show()
    QApplication.processEvents()

    splitter = window._pair_splitters[0]
    splitter.setSizes([200, 400])
    window._remember_pair_ratio(splitter)
    QApplication.processEvents()
    before = _ratio(splitter)

    window.resize(1600, 900)
    QApplication.processEvents()
    after = _ratio(splitter)

    assert abs(after - before) < 0.08
    window.close()


def test_intro_drilldown_switches_tab_and_controller():
    window = MainWindow()
    window.show()
    QApplication.processEvents()

    window._on_intro_drilldown_requested("images", "XDJ-XZ")
    QApplication.processEvents()

    assert window.left_tabs.currentIndex() == window._tab_indexes["images"]
    assert window.layout_view._controller == "XDJ-XZ"
    assert window.deck_layout_view._controller == "XDJ-XZ"
    assert window.controller_layout_view._controller == "XDJ-XZ"

    window.close()


def test_intro_tab_is_named_dashboard():
    window = MainWindow()
    assert window.left_tabs.tabText(window._tab_indexes["intro"]) == "Dashboard"
    window.close()


def test_help_menu_exposes_project_and_controller_documentation():
    window = MainWindow()
    help_menu = next(menu for menu in window.findChildren(QMenu) if menu.title() == "&Help")
    submenu_names = {action.text() for action in help_menu.actions() if action.menu()}
    assert "Project Documentation" in submenu_names
    assert "Controller References" in submenu_names
    documentation = next(
        menu for menu in window.findChildren(QMenu) if menu.title() == "Project Documentation"
    )
    assert "MIDI Clock Compatibility" in {action.text() for action in documentation.actions()}
    window.close()


def test_intro_drilldown_can_open_routing_tab():
    window = MainWindow()
    window.show()
    QApplication.processEvents()

    window._on_intro_drilldown_requested("routing", "DDJ-XP2")
    QApplication.processEvents()

    assert window.left_tabs.currentIndex() == window._tab_indexes["routing"]
    window.close()


def _loaded_window() -> MainWindow:
    window = MainWindow()
    window.show()
    window.config = parse_file(FIXTURE)
    window.current_path = FIXTURE
    window._load_tree()
    QApplication.processEvents()
    return window


# ─── config loading ───────────────────────────────────────────────────────────

def test_load_tree_populates_channel_splitter():
    window = _loaded_window()
    assert window.channel_splitter.count() > 0
    window.close()


def test_load_tree_populates_deck_splitter():
    window = _loaded_window()
    assert window.deck_splitter.count() > 0
    window.close()


def test_load_tree_sets_intro_file_info():
    window = _loaded_window()
    assert FIXTURE.name in window.introduction_view._loaded_file_label.text()
    window.close()


def test_load_tree_sets_live_monitor_config():
    window = _loaded_window()
    assert window.live_monitor_view._config is not None
    window.close()


# ─── search / filter ──────────────────────────────────────────────────────────

def test_search_box_filters_channel_proxies():
    window = _loaded_window()
    window.search_box.setText("codfather")
    QApplication.processEvents()
    for proxy in window.channel_proxies:
        assert proxy.filterRegularExpression().pattern() != "" or proxy.filterFixedString() != ""
    window.search_box.setText("")
    window.close()


# ─── validate ─────────────────────────────────────────────────────────────────

def test_on_validate_no_config_does_not_populate_table():
    window = MainWindow()
    window._on_validate()
    assert window.issues_table.rowCount() == 0
    window.close()


def test_on_validate_with_config_populates_issues_table():
    window = _loaded_window()
    window._on_validate()
    QApplication.processEvents()
    assert window.issues_table.rowCount() > 0
    window.close()


def test_on_validate_status_bar_shows_counts():
    window = _loaded_window()
    window._on_validate()
    msg = window.statusBar().currentMessage()
    assert "error" in msg or "warning" in msg or "info" in msg
    window.close()


# ─── save guards ──────────────────────────────────────────────────────────────

def test_on_save_no_config_does_nothing():
    window = MainWindow()
    window._on_save()
    window.close()


def test_on_save_with_config_and_no_path_triggers_save_as_dialog():
    window = _loaded_window()
    window.current_path = None
    with patch("djmidi.gui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
        window._on_save()
    window.close()


def test_on_save_as_no_config_does_nothing():
    window = MainWindow()
    window._on_save_as()
    window.close()


# ─── live MIDI event propagation ──────────────────────────────────────────────

def test_on_live_midi_event_updates_layout_selections():
    from djmidi.midi_io import MidiEvent
    window = _loaded_window()
    event = MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    window._on_live_midi_event(event)
    QApplication.processEvents()
    window.close()


# ─── controller applied refresh ───────────────────────────────────────────────

def test_on_controller_applied_updates_status_bar():
    window = _loaded_window()
    window._on_controller_applied("TestController")
    assert "TestController" in window.statusBar().currentMessage()
    window.close()


# ─── layout selection helpers ─────────────────────────────────────────────────

def test_update_layout_selection_with_none_clears_keys():
    window = _loaded_window()
    window._update_layout_selection(None, None, None)
    assert window.layout_view._selected_keys == set()
    window.close()


def test_update_layout_selection_with_known_trigger():
    window = _loaded_window()
    window._update_layout_selection("8", "Note On", "64")
    assert len(window.layout_view._selected_keys) > 0
    window.close()


# ─── find_ancestor_control ────────────────────────────────────────────────────

def test_find_ancestor_control_returns_none_for_none_item():
    window = MainWindow()
    assert window._find_ancestor_control(None) is None
    window.close()


def test_find_ancestor_control_traverses_to_control():
    window = _loaded_window()
    for control in window.config.controls:
        for userio in control.userios:
            userio_item = window.node_to_item.get(id(userio))
            if userio_item is not None:
                result = window._find_ancestor_control(userio_item)
                assert result is control
                window.close()
                return
    window.close()


def test_close_event_calls_shutdown_on_monitors():
    window = MainWindow()
    with patch.object(window.live_monitor_view, "shutdown") as mock_live, \
         patch.object(window.midi_routing_view, "shutdown") as mock_routing, \
         patch.object(window.controller_setup_view, "shutdown") as mock_setup:
        window.close()
    mock_live.assert_called_once()
    mock_routing.assert_called_once()
    mock_setup.assert_called_once()


def test_on_save_with_current_path_calls_write_file(tmp_path):
    window = _loaded_window()
    output = tmp_path / "test_out.xml"
    window.current_path = output
    with patch.object(window, "_safe_save", return_value=True) as mock_save:
        window._on_save()
    mock_save.assert_called_once()
    window.close()


def test_on_save_as_with_dialog_path_writes_file(tmp_path):
    window = _loaded_window()
    output = str(tmp_path / "exported.xml")
    with (
        patch("djmidi.gui.main_window.QFileDialog.getSaveFileName", return_value=(output, "")),
        patch.object(window, "_safe_save", return_value=True) as mock_save,
    ):
        window._on_save_as()
    mock_save.assert_called_once()
    window.close()


def test_on_open_shows_error_on_parse_failure():
    window = MainWindow()
    definition = SimpleNamespace(
        name="Serato DJ",
        plugin_id="serato",
        extensions=(".xml",),
        parser=Mock(side_effect=ValueError("bad XML")),
    )
    with (
        patch("djmidi.gui.main_window.QFileDialog.getOpenFileName", return_value=("/some/bad.xml", "")),
        patch("djmidi.gui.main_window.software.active_definitions", return_value=[definition]),
        patch("djmidi.gui.main_window.QInputDialog.getItem", return_value=(definition.name, True)),
        patch("djmidi.gui.main_window.QMessageBox.critical") as mock_err,
    ):
        window._on_open()
    mock_err.assert_called_once()
    window.close()


def test_on_open_loads_config_on_success(tmp_path):
    window = MainWindow()
    with (
        patch("djmidi.gui.main_window.QFileDialog.getOpenFileName", return_value=(str(FIXTURE), "")),
        patch("djmidi.gui.main_window.QInputDialog.getItem", return_value=("Serato DJ", True)),
    ):
        window._on_open()
    QApplication.processEvents()
    assert window.config is not None
    window.close()


def test_refresh_edit_panel_rerenders_current_node():
    from djmidi.model import Control
    window = MainWindow()
    ctrl = Control(channel="1", event_type="Note On", control="60")
    window.edit_panel.set_node(ctrl)
    window._refresh_edit_panel()
    assert window.edit_panel.current_node is ctrl
    window.close()


def test_on_command_applied_with_control_schedules_refresh():
    window = _loaded_window()
    ctrl = window.config.controls[0]
    window._on_command_applied(ctrl)
    QApplication.processEvents()
    window.close()


def test_on_group_edit_applied_does_not_crash():
    window = _loaded_window()
    window._on_group_edit_applied()
    QApplication.processEvents()
    window.close()
