from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog, QMenu

from djmidi.gui.main_window import MainWindow
from djmidi.gui.tree_model import NODE_ROLE
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


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

    assert window._tool_docks["routing"].isVisible()
    window.close()


def test_midi_tools_are_independent_closable_docks():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    assert "monitor" not in window._tab_indexes
    assert "routing" not in window._tab_indexes
    assert not window._tool_docks["monitor"].isVisible()
    assert "clock" in window._tool_docks
    assert not window._tool_docks["clock"].isVisible()
    window._show_tool_dock("monitor")
    assert window._tool_docks["monitor"].isVisible()
    window._tool_docks["monitor"].close()
    assert not window._tool_docks["monitor"].isVisible()
    window.close()


def test_midi_clock_can_be_shown_and_floated_independently():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    window._show_tool_dock("clock")
    assert window._tool_docks["clock"].isVisible()
    window._set_tool_dock_floating("clock", True)
    QApplication.processEvents()
    assert window._tool_docks["clock"].isFloating()
    window.close()


def test_midi_tools_can_switch_between_docked_and_floating_windows():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    assert not window._tool_docks["monitor"].isFloating()
    window._set_tool_dock_floating("monitor", True)
    QApplication.processEvents()
    assert window._tool_docks["monitor"].isFloating()
    window._set_tool_dock_floating("monitor", False)
    QApplication.processEvents()
    assert not window._tool_docks["monitor"].isFloating()
    window.close()


def test_window_state_change_schedules_surface_refresh():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    with patch.object(window, "_refresh_window_surface") as refresh:
        window.changeEvent(QEvent(QEvent.Type.WindowStateChange))
        QApplication.processEvents()
    refresh.assert_called_once()
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


def test_load_tree_auto_starts_live_monitor_by_default(monkeypatch):
    window = MainWindow()
    calls = []
    monkeypatch.setattr(window.live_monitor_view, "ensure_monitoring_started", lambda: calls.append(True))
    window.config = parse_file(FIXTURE)
    window.current_path = FIXTURE
    window._load_tree()
    assert calls == [True]
    window.close()


def test_load_tree_does_not_auto_start_live_monitor_when_disabled(monkeypatch):
    window = MainWindow()
    window.preferences.auto_start_live_monitor = False
    calls = []
    monkeypatch.setattr(window.live_monitor_view, "ensure_monitoring_started", lambda: calls.append(True))
    window.config = parse_file(FIXTURE)
    window.current_path = FIXTURE
    window._load_tree()
    assert calls == []
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


def test_on_live_midi_event_records_the_value_for_knob_fader_animation():
    from djmidi.midi_io import MidiEvent
    window = _loaded_window()
    # DDJ-XP2 EFFECT 1 knob's real trigger; data2 is its 7-bit value.
    event = MidiEvent(direction="in", channel="5", event_type="Note On", data1="112", data2="99", timestamp=0.0)
    window._on_live_midi_event(event)
    QApplication.processEvents()
    assert 99 in window.layout_view._values.values()
    window.close()


def test_on_live_midi_event_flashes_the_resolved_layout_cells():
    from djmidi.midi_io import MidiEvent
    window = _loaded_window()
    event = MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    window._on_live_midi_event(event)
    QApplication.processEvents()
    assert window.layout_view._flash_keys
    assert window.deck_layout_view._flash_keys
    assert window.controller_layout_view._flash_keys
    window.close()


def test_on_live_midi_event_flashes_the_controller_image_overlay_for_the_shown_controller():
    """channel 8 / data1 64 is DDJ-XP2 deck-1 Pad 1 (PAD MODE 5) -- see
    catalog/ddj_xp2.py's pad_lookup note math."""
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window.controller_image_view.set_controller("DDJ-XP2")
    window.controller_image_view._geometry_checkbox.setChecked(True)
    event = MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    window._on_live_midi_event(event)
    QApplication.processEvents()
    item = window.controller_image_view._overlay_items_by_label["Pad 1"]
    assert item.brush().color() == QColor(255, 255, 255, 200)
    window.close()


def test_on_live_midi_event_does_not_flash_the_image_overlay_for_a_different_shown_controller():
    """channel 8 / data1 12 is DDJ-XP2 deck-1 Pad 13 (PAD MODE 1) -- a
    DDJ-XP2-only label, since XDJ-XZ's own pad grid only goes up to Pad 8."""
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window.controller_image_view.set_controller("XDJ-XZ")
    window.controller_image_view._geometry_checkbox.setChecked(True)
    event = MidiEvent(direction="in", channel="8", event_type="Note On", data1="12", data2="127", timestamp=0.0)
    window._on_live_midi_event(event)
    QApplication.processEvents()
    assert window.controller_image_view._overlay_items_by_label  # markers exist
    assert "Pad 13" not in window.controller_image_view._overlay_items_by_label  # DDJ-XP2-only label
    window.close()


def test_on_live_midi_event_flashes_an_open_controller_emulator_for_its_controller():
    from djmidi.gui.controller_emulator import ControllerEmulatorView
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    dock = window._create_emulator_instance("DDJ-XP2")
    view = dock.widget()
    assert isinstance(view, ControllerEmulatorView)
    event = MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    window._on_live_midi_event(event)
    QApplication.processEvents()
    assert view._emulator._flash_keys  # the pad the hit resolves to is lit
    window.close()


def test_on_live_midi_event_does_not_flash_an_emulator_showing_a_different_controller():
    from djmidi.gui.controller_emulator import ControllerEmulatorView
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    dock = window._create_emulator_instance("XDJ-XZ")
    view = dock.widget()
    assert isinstance(view, ControllerEmulatorView)
    # channel 5 / note 112 is DDJ-XP2's EFFECT 1 knob -- resolves to DDJ-XP2
    # only, so the XDJ-XZ emulator must not react.
    event = MidiEvent(direction="in", channel="5", event_type="Note On", data1="112", data2="99", timestamp=0.0)
    window._on_live_midi_event(event)
    QApplication.processEvents()
    assert not view._emulator._flash_keys
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


# ─── pad-side identity: cross-tab navigation and tree<->layout selection ──
# ─── must tell DDJ-XP2/XDJ-XZ's two physical pad grids apart too (the ─────
# ─── By Channel/Deck/Controller tabs' own follow-up to the Controller ─────
# ─── Emulator's identical fix) ─────────────────────────────────────────────


def test_update_layout_selection_selects_the_left_marker_for_a_deck_1_trigger():
    """channel 8 = DDJ-XP2's deck 1 pad channel (no shift) -- real fixture
    trigger, resolves to "Deck 1 Pad 1 (PAD MODE 5)"."""
    window = _loaded_window()
    window._update_layout_selection("8", "Note On", "64")
    assert ("DDJ-XP2", "PAD", "Pad 1") in window.layout_view._selected_keys
    assert ("DDJ-XP2", "PAD", "Pad 1 (R)") not in window.layout_view._selected_keys
    window.close()


def test_update_layout_selection_selects_the_right_marker_for_a_deck_2_trigger():
    """channel 10 = DDJ-XP2's deck 2 pad channel -- real fixture trigger,
    resolves to "Deck 2 Pad 8 (PAD MODE 5)"."""
    window = _loaded_window()
    window._update_layout_selection("10", "Note On", "71")
    assert ("DDJ-XP2", "PAD", "Pad 8 (R)") in window.layout_view._selected_keys
    assert ("DDJ-XP2", "PAD", "Pad 8") not in window.layout_view._selected_keys
    window.close()


def test_on_layout_cell_activated_finds_a_left_side_control_for_the_plain_key():
    window = _loaded_window()
    window._on_layout_cell_activated(("DDJ-XP2", "PAD", "Pad 1"), "channel")
    assert window.statusBar().currentMessage().startswith("'Pad 1':")
    assert "No control" not in window.statusBar().currentMessage()
    window.close()


def test_on_layout_cell_activated_finds_a_right_side_control_for_the_suffixed_key():
    window = _loaded_window()
    window._on_layout_cell_activated(("DDJ-XP2", "PAD", "Pad 8 (R)"), "channel")
    assert "No control" not in window.statusBar().currentMessage()
    # The control the click landed on must actually be the right-side one
    # (channel 10, deck 2's pad channel), not the left grid's deck 1/3
    # control sharing the merged "Pad 8" cell. (The same raw trigger also
    # happens to match other controllers' catalogs at this channel/data1 --
    # expected, unrelated to this fix -- so check membership, not equality.)
    assert ("DDJ-XP2", "PAD", "Pad 8 (R)") in window.layout_view._selected_keys
    assert ("DDJ-XP2", "PAD", "Pad 8") not in window.layout_view._selected_keys
    window.close()


def test_select_deck_group_matches_the_correct_physical_side():
    window = _loaded_window()
    assert window._select_deck_group(("DDJ-XP2", "PAD", "Pad 1")) is True
    assert window._select_deck_group(("DDJ-XP2", "PAD", "Pad 8 (R)")) is True
    window.close()


def test_select_deck_group_selects_a_group_on_the_requested_side_only():
    """The selected group's own real trigger must actually be on the
    requested side -- not just "a match was found somewhere"."""
    window = _loaded_window()
    window._select_deck_group(("DDJ-XP2", "PAD", "Pad 8 (R)"))
    # Find whichever deck tree actually ended up with a selection.
    group = None
    for view in window._deck_tree_views:
        indexes = view.selectionModel().selectedIndexes()
        if indexes:
            candidate = indexes[0].data(NODE_ROLE)
            if candidate is not None:
                group = candidate
                break
    assert group is not None
    assert group.channel == "10"  # DDJ-XP2's deck 2 pad channel -- the right side
    window.close()


def test_select_controller_cell_does_not_corrupt_selection_for_a_right_side_key():
    """A regression guard for a real bug caught during manual verification:
    _select_controller_cell() used to fall back to selecting the merged
    key's tree row when no exact match existed, but that row's own
    CELL_KEY_ROLE is the merged key -- selecting it re-triggers
    _on_controller_selection_changed -> _on_layout_cell_activated with the
    *merged* key, silently overwriting the correct side-aware selection
    with the merged cell's first (often left-side) match. Must return
    False and leave the already-correct selection alone instead."""
    window = _loaded_window()
    window._on_layout_cell_activated(("DDJ-XP2", "PAD", "Pad 3 (R)"), "controller")
    assert ("DDJ-XP2", "PAD", "Pad 3 (R)") in window.layout_view._selected_keys
    assert ("DDJ-XP2", "PAD", "Pad 3") not in window.layout_view._selected_keys
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


def test_on_open_mapping_requested_loads_config_and_switches_to_channel_tab():
    """Controller Setup's "open this XML for editing too" follow-up (emitted
    after an import) behaves like File -> Open on that path, and additionally
    lands on the By Channel tab so the loaded mapping is immediately visible."""
    window = MainWindow()
    window.left_tabs.setCurrentIndex(window._tab_indexes["setup"])
    with patch("djmidi.gui.main_window.QInputDialog.getItem", return_value=("Serato DJ", True)):
        window._on_open_mapping_requested(str(FIXTURE))
    QApplication.processEvents()
    assert window.config is not None
    assert window.left_tabs.currentIndex() == window._tab_indexes["channel"]
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


def test_on_preferences_without_custom_log_path_preserves_active_log_file():
    window = MainWindow()
    window.preferences.log_path = ""
    with patch("djmidi.gui.main_window.PreferencesDialog") as mock_dialog_cls, \
         patch("djmidi.gui.main_window.current_log_path", return_value=Path("/active/current.log")), \
         patch("djmidi.gui.main_window.configure_logging") as mock_configure, \
         patch.object(window.preferences, "save"):
        mock_dialog_cls.return_value.exec.return_value = QDialog.DialogCode.Accepted
        window._on_preferences()
    mock_configure.assert_called_once_with(window.preferences.log_level, Path("/active/current.log"))
    window.close()


def test_on_preferences_with_custom_log_path_uses_it_over_active_log_file():
    window = MainWindow()
    window.preferences.log_path = "/custom/preference.log"
    with patch("djmidi.gui.main_window.PreferencesDialog") as mock_dialog_cls, \
         patch("djmidi.gui.main_window.current_log_path", return_value=Path("/active/current.log")), \
         patch("djmidi.gui.main_window.configure_logging") as mock_configure, \
         patch.object(window.preferences, "save"):
        mock_dialog_cls.return_value.exec.return_value = QDialog.DialogCode.Accepted
        window._on_preferences()
    mock_configure.assert_called_once_with(window.preferences.log_level, "/custom/preference.log")
    window.close()


def test_default_window_size_is_larger_than_the_legacy_1100x700():
    window = MainWindow()
    size = window._default_window_size()
    assert size.width() >= 1100
    assert size.height() >= 720
    assert size.width() <= MainWindow._PREFERRED_WINDOW_SIZE.width()
    assert size.height() <= MainWindow._PREFERRED_WINDOW_SIZE.height()
    window.close()


def test_default_window_size_never_exceeds_the_available_screen():
    from PySide6.QtGui import QGuiApplication

    window = MainWindow()
    screen = window.screen() or QGuiApplication.primaryScreen()
    available = screen.availableGeometry()
    size = window._default_window_size()
    # Either it fits inside the usable screen, or it was floored at the
    # minimum sensible default because the screen is smaller than that.
    assert size.width() <= max(available.width(), MainWindow._MIN_DEFAULT_WINDOW_SIZE.width())
    assert size.height() <= max(available.height(), MainWindow._MIN_DEFAULT_WINDOW_SIZE.height())
    window.close()


def test_center_on_screen_keeps_the_frame_within_the_usable_area():
    from PySide6.QtGui import QGuiApplication

    window = MainWindow()
    window.resize(800, 600)
    window._center_on_screen()
    screen = window.screen() or QGuiApplication.primaryScreen()
    available = screen.availableGeometry()
    frame = window.frameGeometry()
    assert frame.left() >= available.left()
    assert frame.top() >= available.top()
    window.close()


def test_show_all_controllers_toggle_overrides_disabled_controllers():
    from djmidi import catalog

    window = MainWindow()
    try:
        definition = catalog.all_controller_definitions()[0]
        target = definition.name
        # Enablement is keyed by plugin_id (falling back to name), same as
        # _apply_plugin_preferences and the Preferences dialog.
        window.preferences.disable(definition.plugin_id or definition.name)
        window._show_all_controllers = False
        window._apply_plugin_preferences()
        assert target not in catalog.CONTROLLER_NAMES

        window._on_show_all_controllers_toggled(True)
        assert window._show_all_controllers is True
        assert target in catalog.CONTROLLER_NAMES
        assert catalog._registry._ENABLED_PLUGIN_IDS is None

        window._on_show_all_controllers_toggled(False)
        assert target not in catalog.CONTROLLER_NAMES
    finally:
        catalog.set_enabled_plugin_ids(None)
        window.close()


def test_show_all_controllers_toggle_persists_to_settings():
    from unittest.mock import Mock

    from djmidi import catalog

    window = MainWindow()
    fake_settings = Mock()
    try:
        with patch.object(window, "_layout_settings", return_value=fake_settings):
            window._on_show_all_controllers_toggled(True)
        fake_settings.setValue.assert_any_call("view/show_all_controllers", True)
    finally:
        catalog.set_enabled_plugin_ids(None)
        window.close()


def test_show_all_controllers_action_is_in_the_view_menu():
    from djmidi import catalog

    window = MainWindow()
    try:
        action = window._show_all_controllers_action
        assert action.isCheckable()
        assert not action.isChecked()
    finally:
        catalog.set_enabled_plugin_ids(None)
        window.close()


def test_performance_mode_action_is_in_the_view_menu():
    window = MainWindow()
    try:
        action = window._performance_mode_action
        assert action.isCheckable()
        assert not action.isChecked()
    finally:
        window.close()


def test_performance_mode_on_shrinks_tree_and_zooms_layout_views():
    from djmidi.gui.main_window import _PERFORMANCE_TREE_RATIO, _PERFORMANCE_ZOOM_FACTOR

    window = _loaded_window()
    try:
        window._on_performance_mode_toggled(True)
        for splitter in window._pair_splitters:
            assert window._pair_ratio_by_id[id(splitter)] == _PERFORMANCE_TREE_RATIO
        for view in (window.layout_view, window.deck_layout_view, window.controller_layout_view):
            assert view._view.transform().m11() == _PERFORMANCE_ZOOM_FACTOR
    finally:
        window.close()


def test_performance_mode_off_restores_prior_ratios_and_zoom():
    window = _loaded_window()
    try:
        for splitter in window._pair_splitters:
            window._pair_ratio_by_id[id(splitter)] = 0.7
        window._on_performance_mode_toggled(True)
        window._on_performance_mode_toggled(False)
        for splitter in window._pair_splitters:
            assert window._pair_ratio_by_id[id(splitter)] == 0.7
        # Reset means giving up performance mode's manual scale factor, not
        # necessarily an identity transform -- the resize-driven "maximize
        # space" auto-fit may still apply its own scale at factor 1.0 (see
        # test_layout_view.py's test_set_zoom_back_to_one_resets_the_transform).
        for view in (window.layout_view, window.deck_layout_view, window.controller_layout_view):
            assert view._manual_zoom_factor == 1.0
    finally:
        window.close()


def test_performance_mode_ratio_survives_a_resize():
    from djmidi.gui.main_window import _PERFORMANCE_TREE_RATIO

    window = _loaded_window()
    try:
        window._on_performance_mode_toggled(True)
        window.resize(window.width() + 50, window.height() + 50)
        QApplication.processEvents()
        for splitter in window._pair_splitters:
            assert window._pair_ratio_by_id[id(splitter)] == _PERFORMANCE_TREE_RATIO
    finally:
        window.close()


def test_no_emulator_instances_exist_until_requested():
    window = MainWindow()
    try:
        assert window._emulator_docks == {}
    finally:
        window.close()


def test_new_emulator_instance_creates_a_visible_dock():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    try:
        dock = window._create_emulator_instance()
        QApplication.processEvents()
        assert dock.isVisible()
        assert len(window._emulator_docks) == 1
    finally:
        window.close()


def test_multiple_emulator_instances_can_be_open_at_once_for_different_controllers():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    try:
        dock_a = window._create_emulator_instance("DDJ-XP2")
        dock_b = window._create_emulator_instance("XDJ-XZ")
        assert len(window._emulator_docks) == 2
        assert dock_a.widget().current_controller() == "DDJ-XP2"
        assert dock_b.widget().current_controller() == "XDJ-XZ"
    finally:
        window.close()


def test_closing_an_emulator_instance_removes_it_from_tracking():
    window = MainWindow()
    window.show()
    QApplication.processEvents()
    try:
        window._create_emulator_instance()
        (instance_id,) = window._emulator_docks.keys()
        window._close_emulator_instance(instance_id)
        assert window._emulator_docks == {}
    finally:
        window.close()


def test_new_controller_emulator_action_triggers_a_new_instance():
    window = MainWindow()
    try:
        assert window._new_emulator_action.text() == "New Controller Emulator…"
        window._new_emulator_action.trigger()
        assert len(window._emulator_docks) == 1
    finally:
        window.close()


def test_controller_emulator_instance_resolves_against_the_loaded_config():
    window = _loaded_window()
    try:
        dock = window._create_emulator_instance()
        assert dock.widget()._config_provider() is window.config
    finally:
        window.close()


def test_controller_applied_refreshes_every_emulator_instance_and_clears_reverse_lookup_cache(monkeypatch):
    from djmidi.gui import layout as layout_mod

    window = MainWindow()
    try:
        dock = window._create_emulator_instance()
        layout_mod.reverse_lookup("DDJ-XP2")  # populate the cache
        cleared = []
        monkeypatch.setattr(layout_mod, "clear_reverse_lookup_cache", lambda: cleared.append(True))
        refreshed = []
        monkeypatch.setattr(dock.widget(), "refresh_controllers", lambda: refreshed.append(True))
        window._on_controller_applied("DDJ-XP2")
        assert cleared == [True]
        assert refreshed == [True]
    finally:
        window.close()


def test_close_event_persists_open_emulator_controllers():
    window = MainWindow()
    window._create_emulator_instance("DDJ-XP2")
    window._create_emulator_instance("XDJ-XZ")
    fake_settings = Mock()
    with patch.object(window, "_layout_settings", return_value=fake_settings):
        window.close()
    saved_calls = {c.args[0]: c.args[1] for c in fake_settings.setValue.call_args_list}
    assert sorted(saved_calls["emulator/open_controllers"]) == ["DDJ-XP2", "XDJ-XZ"]


def test_restore_emulator_instances_reopens_saved_controllers():
    from unittest.mock import Mock

    window = MainWindow()
    try:
        fake_settings = Mock()
        fake_settings.value.return_value = ["DDJ-XP2", "XDJ-XZ"]
        window._restore_emulator_instances(fake_settings)
        controllers = sorted(dock.widget().current_controller() for dock in window._emulator_docks.values())
        assert controllers == ["DDJ-XP2", "XDJ-XZ"]
    finally:
        window.close()


def test_restore_emulator_instances_handles_a_single_saved_controller_as_a_bare_string():
    """QSettings can collapse a single-element string list back to a bare
    string on some platforms/backends."""
    from unittest.mock import Mock

    window = MainWindow()
    try:
        fake_settings = Mock()
        fake_settings.value.return_value = "DDJ-XP2"
        window._restore_emulator_instances(fake_settings)
        assert len(window._emulator_docks) == 1
    finally:
        window.close()


def test_edit_column_hidden_on_non_tree_tabs():
    from djmidi import catalog

    window = MainWindow()
    try:
        for key in ("intro", "setup", "images"):
            window.left_tabs.setCurrentIndex(window._tab_indexes[key])
            assert not window._right_splitter.isVisibleTo(window), key
        for key in ("channel", "deck", "controller"):
            window.left_tabs.setCurrentIndex(window._tab_indexes[key])
            assert window._right_splitter.isVisibleTo(window), key
    finally:
        catalog.set_enabled_plugin_ids(None)
        window.close()


def test_on_live_midi_event_holds_and_releases_the_active_highlight():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    press = MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    window._on_live_midi_event(press)
    QApplication.processEvents()
    assert window.layout_view._active_keys
    assert window.deck_layout_view._active_keys
    assert window.controller_layout_view._active_keys

    release = MidiEvent(direction="in", channel="8", event_type="Note Off", data1="64", data2="0", timestamp=0.1)
    window._on_live_midi_event(release)
    QApplication.processEvents()
    assert not window.layout_view._active_keys
    assert not window.controller_layout_view._active_keys
    window.close()


def test_on_live_midi_event_treats_velocity_zero_note_on_as_a_release():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.layout_view._active_keys
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="0", timestamp=0.1)
    )
    QApplication.processEvents()
    assert not window.layout_view._active_keys
    window.close()


def test_on_live_midi_event_holds_an_open_emulator_and_the_image_overlay():
    from djmidi.gui.controller_emulator import ControllerEmulatorView
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window.controller_image_view.set_controller("DDJ-XP2")
    window.controller_image_view._geometry_checkbox.setChecked(True)
    dock = window._create_emulator_instance("DDJ-XP2")
    emu = dock.widget()
    assert isinstance(emu, ControllerEmulatorView)

    press = MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    window._on_live_midi_event(press)
    QApplication.processEvents()
    assert emu._emulator._live_active_keys
    assert window.controller_image_view._active_labels

    release = MidiEvent(direction="in", channel="8", event_type="Note Off", data1="64", data2="0", timestamp=0.1)
    window._on_live_midi_event(release)
    QApplication.processEvents()
    assert not emu._emulator._live_active_keys
    assert not window.controller_image_view._active_labels
    window.close()


def test_output_direction_note_latches_an_led_highlight_without_flashing_or_selecting():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    on = MidiEvent(direction="out", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    window._on_live_midi_event(on)
    QApplication.processEvents()
    assert window.layout_view._led_keys
    assert window.deck_layout_view._led_keys
    assert window.controller_layout_view._led_keys
    # Output-direction feedback is passive state, not a user gesture:
    # no momentary held state, no flash pulse, no cross-tab selection.
    assert not window.layout_view._active_keys
    assert not window.layout_view._flash_keys
    assert not window.layout_view._selected_keys

    off = MidiEvent(direction="out", channel="8", event_type="Note Off", data1="64", data2="0", timestamp=0.1)
    window._on_live_midi_event(off)
    QApplication.processEvents()
    assert not window.layout_view._led_keys
    assert not window.controller_layout_view._led_keys
    window.close()


def test_output_direction_velocity_zero_note_on_clears_the_led():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window._on_live_midi_event(
        MidiEvent(direction="out", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.layout_view._led_keys
    window._on_live_midi_event(
        MidiEvent(direction="out", channel="8", event_type="Note On", data1="64", data2="0", timestamp=0.1)
    )
    QApplication.processEvents()
    assert not window.layout_view._led_keys
    window.close()


def test_output_direction_led_drives_the_emulator_and_image_overlay():
    from djmidi.gui.controller_emulator import ControllerEmulatorView
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window.controller_image_view.set_controller("DDJ-XP2")
    window.controller_image_view._geometry_checkbox.setChecked(True)
    dock = window._create_emulator_instance("DDJ-XP2")
    emu = dock.widget()
    assert isinstance(emu, ControllerEmulatorView)

    window._on_live_midi_event(
        MidiEvent(direction="out", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    )
    QApplication.processEvents()
    assert emu._emulator._led_keys
    assert window.controller_image_view._led_labels
    assert not emu._emulator._live_active_keys  # kept apart from the input-direction hold

    window._on_live_midi_event(
        MidiEvent(direction="out", channel="8", event_type="Note Off", data1="64", data2="0", timestamp=0.1)
    )
    QApplication.processEvents()
    assert not emu._emulator._led_keys
    assert not window.controller_image_view._led_labels
    window.close()


def test_output_direction_control_change_does_not_touch_led_state():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window._on_live_midi_event(
        MidiEvent(direction="out", channel="8", event_type="Control Change", data1="64", data2="127", timestamp=0.0)
    )
    QApplication.processEvents()
    assert not window.layout_view._led_keys
    window.close()


def test_live_jog_turn_spins_the_jog_glyph_without_moving_the_selection():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    key = ("XDJ-XZ", "DISPLAY", "Jog wheel")
    window.layout_view.set_selected_keys({("XDJ-XZ", "DECK", "PLAY/PAUSE")})
    before = set(window.layout_view._selected_keys)

    # XDJ-XZ deck-1 platter turn: CC 34 (0x22) on channel 1, value 0x45 = +5.
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="1", event_type="Control Change", data1="34", data2="69", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.layout_view._jog_angles.get(key)
    assert window.deck_layout_view._jog_angles.get(key)
    assert window.controller_layout_view._jog_angles.get(key)
    # A jog turn is motion feedback, not a "user picked this" gesture.
    assert window.layout_view._selected_keys == before
    window.close()


def test_live_jog_turn_drives_an_open_emulator_for_the_same_controller():
    from djmidi.gui.controller_emulator import ControllerEmulatorView
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    dock = window._create_emulator_instance("XDJ-XZ")
    emu = dock.widget()
    assert isinstance(emu, ControllerEmulatorView)
    other = window._create_emulator_instance("DDJ-XP2").widget()

    window._on_live_midi_event(
        MidiEvent(direction="in", channel="2", event_type="Control Change", data1="33", data2="60", timestamp=0.0)
    )
    QApplication.processEvents()
    # deck 2 -> right-tray jog on XDJ-XZ.
    assert emu._emulator._jog_angles.get(("XDJ-XZ", "DISPLAY", "Jog wheel (R)"))
    assert other._emulator._jog_angles == {}  # different controller, untouched
    window.close()


def test_non_jog_control_change_is_left_to_the_normal_lookup_path():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="1", event_type="Control Change", data1="7", data2="100", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.layout_view._jog_angles == {}
    window.close()


def test_live_jog_turn_spins_the_controller_images_overlay_when_it_shows_that_controller():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    window.controller_image_view.set_controller("XDJ-XZ")
    window.controller_image_view._geometry_checkbox.setChecked(True)

    # deck 2 -> right-tray jog; the overlay has only the one "Jog wheel"
    # entry, so the mirror suffix is stripped and it still spins.
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="2", event_type="Control Change", data1="34", data2="70", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.controller_image_view._jog_angles.get("Jog wheel")

    # A different controller on that tab -> untouched.
    window.controller_image_view.set_controller("DDJ-XP2")
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="1", event_type="Control Change", data1="34", data2="70", timestamp=0.1)
    )
    QApplication.processEvents()
    assert "Jog wheel" not in window.controller_image_view._jog_angles
    window.close()


def test_live_ddj_1000_jog_turn_spins_its_layout_jog_glyph():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    key = ("DDJ-1000", "DISPLAY", "Jog wheel")
    # DDJ-1000 platter, deck-1 channel, CC 0x21 ("33"), value 0x46 = +6.
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="1", event_type="Control Change", data1="33", data2="70", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.layout_view._jog_angles.get(key)
    assert window.controller_layout_view._jog_angles.get(key)
    window.close()


def test_live_ddj_flx10_jog_turn_spins_its_layout_jog_glyph():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    key = ("DDJ-FLX10", "DISPLAY", "Jog wheel")
    # DDJ-FLX10 platter (vinyl-off), deck-1 channel, CC 0x23 ("35"), 0x46 = +6.
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="1", event_type="Control Change", data1="35", data2="70", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.layout_view._jog_angles.get(key)
    assert window.controller_layout_view._jog_angles.get(key)
    window.close()


def test_live_ddj_rev1_jog_turn_spins_its_layout_jog_glyph():
    from djmidi.midi_io import MidiEvent

    window = _loaded_window()
    key = ("DDJ-REV1", "DISPLAY", "Jog wheel")
    # DDJ-REV1 wheel-side, deck-1 channel, CC 0x21 ("33"), value 0x3A = -6.
    window._on_live_midi_event(
        MidiEvent(direction="in", channel="1", event_type="Control Change", data1="33", data2="58", timestamp=0.0)
    )
    QApplication.processEvents()
    assert window.layout_view._jog_angles.get(key)
    assert window.controller_layout_view._jog_angles.get(key)
    window.close()
