from djmidi import catalog
from djmidi.catalog._registry import ControllerDefinition, register
from djmidi.gui.layout_view import ControllerLayoutView

_USAGE = {("DDJ-XP2", "PAD", "Pad 1"): {"0": {"codfather_st"}, "2": {"auto_loop_specific_length"}}}


def test_refresh_controllers_adds_newly_registered_controller_and_keeps_selection():
    view = ControllerLayoutView()
    for i in range(view._controller_tabs.count()):
        if view._controller_tabs.tabText(i) == "XDJ-XZ":
            view._controller_tabs.setCurrentIndex(i)
            break
    register(ControllerDefinition(name="__LayoutLiveTest__"))
    try:
        view.refresh_controllers()
        items = [view._controller_tabs.tabText(i) for i in range(view._controller_tabs.count())]
        assert "__LayoutLiveTest__" in items
        assert view._controller == "XDJ-XZ"
    finally:
        del catalog._registry._REGISTRY["__LayoutLiveTest__"]


def test_deck_filter_hidden_by_default():
    view = ControllerLayoutView()
    assert view._deck_combo is None


def test_deck_filter_populated_from_usage():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    items = [view._deck_combo.itemText(i) for i in range(view._deck_combo.count())]
    assert items == ["All decks", "Deck 0", "Deck 2"]


def test_deck_filter_narrows_selected_deck_only():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    view._deck_combo.setCurrentText("Deck 2")
    assert view._selected_deck_filter() == "2"
    view._deck_combo.setCurrentText("All decks")
    assert view._selected_deck_filter() is None


def test_all_decks_shows_union_of_tags():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    decks, tags = view._cell_decks_and_tags(("DDJ-XP2", "PAD", "Pad 1"), None)
    assert decks == {"0", "2"}
    assert tags == {"codfather_st", "auto_loop_specific_length"}


def test_deck_filter_narrows_tags_to_that_deck_only():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_usage(_USAGE)
    decks, tags = view._cell_decks_and_tags(("DDJ-XP2", "PAD", "Pad 1"), "0")
    assert decks == {"0"}
    assert tags == {"codfather_st"}


def test_unmapped_cell_returns_empty():
    view = ControllerLayoutView()
    view.set_usage(_USAGE)
    decks, tags = view._cell_decks_and_tags(("DDJ-XP2", "PAD", "Pad 99"), None)
    assert decks == set()
    assert tags == set()


def test_linked_cell_from_other_controller_is_stored_and_rendered():
    usage = {
        ("DDJ-XP2", "PAD", "Pad 13"): {"1": {"codfather_st"}},
        ("XDJ-XZ", "PAD", "Pad 5"): {"1": {"codfather_st"}},
    }
    linked = {("DDJ-XP2", "PAD", "Pad 13"): {("XDJ-XZ", "PAD", "Pad 5")}}
    view = ControllerLayoutView()
    view.set_usage(usage, linked)
    assert view._linked_cells == linked
    # Rebuilding must not crash with a populated split-cell (top + bottom half + divider).
    assert len(view._scene.items()) > 0


def test_cell_without_link_renders_placeholder_without_crashing():
    view = ControllerLayoutView()
    view.set_usage({("DDJ-XP2", "PAD", "Pad 1"): {"1": {"codfather_st"}}})
    assert view._linked_cells == {}
    assert len(view._scene.items()) > 0


def test_set_selected_keys_stores_and_triggers_rebuild():
    view = ControllerLayoutView()
    view.set_usage(_USAGE)
    view.set_selected_keys({("DDJ-XP2", "PAD", "Pad 1")})
    assert view._selected_keys == {("DDJ-XP2", "PAD", "Pad 1")}
    view.set_selected_keys(set())
    assert view._selected_keys == set()


def test_selection_history_fades_previous_layout_selection():
    view = ControllerLayoutView()
    first = ("DDJ-XP2", "PAD", "Pad 1")
    second = ("DDJ-XP2", "PAD", "Pad 2")
    view.set_selected_keys({first})
    view.set_selected_keys({second})
    assert view._selected_keys == {second}
    assert view._selection_history == [{first}]
    view.clear_selection_history()
    assert view._selection_history == []


def test_set_controller_switches_tab_when_name_exists():
    view = ControllerLayoutView()
    assert view.set_controller("XDJ-XZ") is True
    assert view._controller == "XDJ-XZ"


def test_controller_selector_is_horizontal_scrollable():
    view = ControllerLayoutView()
    assert view._controller_scroll.widget() is view._controller_tabs
    assert view._controller_scroll.horizontalScrollBarPolicy().name == "ScrollBarAsNeeded"
    assert view._controller_scroll.verticalScrollBarPolicy().name == "ScrollBarAlwaysOff"
    assert view.set_controller("__missing__") is False
