"""The Find function panel (issue #185) and how MainWindow reacts to it."""

from pathlib import Path

from PySide6.QtWidgets import QApplication

from djmidi import catalog
from djmidi.gui import layout as layout_mod
from djmidi.gui.function_search_view import FunctionSearchView
from djmidi.gui.main_window import MainWindow
from djmidi.gui.mapping_group import MappingGroup
from djmidi.gui.tree_model import NODE_ROLE
from djmidi.parser import parse_file

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _loaded_window() -> MainWindow:
    window = MainWindow()
    window.resize(1100, 700)
    window.show()
    window.config = parse_file(FIXTURE)
    window.current_path = FIXTURE
    window._load_tree()
    QApplication.processEvents()
    return window


def _keys_for(result) -> set:
    return {
        layout_mod.presentation_key_for_hit(hit)
        for trigger in result.triggers
        for hit in catalog.lookup(trigger.channel, trigger.event_type, trigger.control)
    }


def test_view_without_a_mapping_says_so():
    view = FunctionSearchView()
    view.set_query("loop")
    assert view.result_count() == 0
    assert "Open a mapping" in view.summary.text()


def test_view_lists_matches_with_location_physical_control_and_trigger():
    view = FunctionSearchView()
    view.set_config(parse_file(FIXTURE))
    view.set_query("loop roll deck 2 slot 3")
    assert view.result_count() == 1
    first, second = view.results.item(0).text().split("\n")
    assert first == "Loop roll · Deck 2 · Slot 3"
    # The raw Serato tag stays in the tooltip.
    assert "auto_loop_roll_specific_length" in view.results.item(0).toolTip()
    assert second.startswith("ch") and " → " in second
    # Several controllers resolve the same trigger: the row names one, the
    # tooltip lists them all.
    assert "(+" in second
    assert "DDJ-XP2: " in view.results.item(0).toolTip()
    view.set_query("loop banana")
    assert view.result_count() == 0
    assert "No function matches" in view.summary.text()


def test_selecting_a_result_navigates_and_highlights_on_by_channel():
    window = _loaded_window()
    try:
        window.left_tabs.setCurrentIndex(window._tab_indexes["channel"])
        panel = window.function_search_view
        panel.set_query("loop roll deck 2 slot 3")
        panel.select_row(0)
        QApplication.processEvents()
        result = panel.result_at(0)
        assert window.left_tabs.currentIndex() == window._tab_indexes["channel"]
        assert window.edit_panel.current_node is result.controls[0]
        assert window.layout_view._selected_keys == _keys_for(result)
    finally:
        window.close()


def test_selecting_a_result_on_by_deck_selects_its_own_deck_slot_row():
    window = _loaded_window()
    try:
        window.left_tabs.setCurrentIndex(window._tab_indexes["deck"])
        panel = window.function_search_view
        panel.set_query("loop roll deck 3 slot 5")
        panel.select_row(0)
        QApplication.processEvents()
        result = panel.result_at(0)
        assert window.left_tabs.currentIndex() == window._tab_indexes["deck"]
        group = window.edit_panel.current_node
        assert isinstance(group, MappingGroup)
        assert (group.deck_id, group.slot_id, group.tag) == ("3", "5", result.tag)
        selected = [
            view.currentIndex().data(NODE_ROLE) for view in window._deck_tree_views if view.currentIndex().isValid()
        ]
        assert group in selected
    finally:
        window.close()


def test_a_result_with_several_controls_outlines_all_of_them():
    window = _loaded_window()
    try:
        panel = window.function_search_view
        panel.set_query("auto loop specific length output deck 0 slot 6")
        assert panel.result_count() == 1
        result = panel.result_at(0)
        assert len(result.triggers) > 1
        panel.select_row(0)
        QApplication.processEvents()
        keys = _keys_for(result)
        single = {
            layout_mod.presentation_key_for_hit(hit)
            for hit in catalog.lookup(result.controls[0].channel, result.controls[0].event_type, result.controls[0].control)
        }
        assert keys > single
        for view in (window.layout_view, window.deck_layout_view, window.controller_layout_view):
            assert view._selected_keys == keys
    finally:
        window.close()


def test_selecting_a_result_on_by_controller_stays_there_and_edits_that_control():
    window = _loaded_window()
    try:
        window.left_tabs.setCurrentIndex(window._tab_indexes["controller"])
        panel = window.function_search_view
        # A left-deck function: the By Controller tree has no row for a
        # right-side (" (R)") cell, and since #338 every controller the
        # fixture's pads resolve on splits its pad grid by side.
        panel.set_query("codfather fx deck 0 slot 0")
        panel.select_row(0)
        QApplication.processEvents()
        result = panel.result_at(0)
        assert window.left_tabs.currentIndex() == window._tab_indexes["controller"]
        assert window.edit_panel.current_node is result.controls[0]
        assert window.controller_layout_view._selected_keys == _keys_for(result)
    finally:
        window.close()
