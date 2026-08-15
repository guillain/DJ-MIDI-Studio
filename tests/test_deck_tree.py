from pathlib import Path

from djmidi.gui.deck_tree import build_deck_columns, build_deck_tree
from djmidi.gui.mapping_group import MappingGroup
from djmidi.gui.tree_model import NODE_ROLE
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_deck_columns_one_per_deck_no_deck_wrapper():
    config = parse_file(FIXTURE)
    columns = build_deck_columns(config)
    assert [deck_id for deck_id, _model in columns] == ["0", "1", "2", "3"]
    _deck_id, model = columns[0]
    assert model.horizontalHeaderItem(0).text() == "Deck 0"
    # Top level is Slot groups directly (no extra "Deck 0" wrapper row).
    top_labels = [model.item(i).text() for i in range(model.rowCount())]
    assert all(label.startswith("Slot ") for label in top_labels)


def test_deck_columns_leaves_carry_mapping_groups_for_that_deck_only():
    config = parse_file(FIXTURE)
    columns = build_deck_columns(config)
    for deck_id, model in columns:
        for row in range(model.rowCount()):
            slot_item = model.item(row)
            for leaf_row in range(slot_item.rowCount()):
                group = slot_item.child(leaf_row).data(NODE_ROLE)
                assert isinstance(group, MappingGroup)
                assert group.deck_id == deck_id


def test_deck_columns_match_flat_deck_tree_content():
    config = parse_file(FIXTURE)
    flat = build_deck_tree(config)
    columns = build_deck_columns(config)
    assert flat.rowCount() == len(columns)
    for i, (deck_id, _model) in enumerate(columns):
        assert flat.item(i).text() == f"Deck {deck_id}"
