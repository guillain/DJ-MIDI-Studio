from seratomidiconf.gui.layout_view import ControllerLayoutView

_USAGE = {("DDJ-XP2", "PAD", "Pad 1"): {"0": {"codfather_st"}, "2": {"auto_loop_specific_length"}}}


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
