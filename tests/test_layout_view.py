from seratomidiconf.gui.layout_view import ControllerLayoutView


def test_deck_filter_hidden_by_default():
    view = ControllerLayoutView()
    assert view._deck_combo is None


def test_deck_filter_populated_from_usage():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_deck_usage({("DDJ-XP2", "PAD", "Pad 1"): {"0", "2"}})
    items = [view._deck_combo.itemText(i) for i in range(view._deck_combo.count())]
    assert items == ["All decks", "Deck 0", "Deck 2"]


def test_deck_filter_narrows_selected_deck_only():
    view = ControllerLayoutView(show_deck_filter=True)
    view.set_deck_usage({("DDJ-XP2", "PAD", "Pad 1"): {"0", "2"}})
    view._deck_combo.setCurrentText("Deck 2")
    assert view._selected_deck_filter() == "2"
    view._deck_combo.setCurrentText("All decks")
    assert view._selected_deck_filter() is None
