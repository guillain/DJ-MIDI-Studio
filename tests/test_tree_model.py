from pathlib import Path

from seratomidiconf.gui.tree_model import NODE_ROLE, build_tree_model
from seratomidiconf.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def test_top_level_is_grouped_by_channel():
    config = parse_file(FIXTURE)
    model, _ = build_tree_model(config)
    labels = [model.item(i).text() for i in range(model.rowCount())]
    assert labels == ["Channel 8", "Channel 10", "Channel 12", "Channel 14"]


def test_channel_groups_are_grouped_by_note_then_control():
    config = parse_file(FIXTURE)
    model, _ = build_tree_model(config)
    channel_item = model.item(0)
    assert channel_item.rowCount() == 16  # 16 distinct pad notes on this channel
    note_item = channel_item.child(0)
    assert note_item.text().startswith("Note/Control ")
    assert note_item.rowCount() == 10  # the known 10x duplication
    control_item = note_item.child(0)
    assert control_item.data(NODE_ROLE) is not None


def test_group_headers_are_not_selectable():
    config = parse_file(FIXTURE)
    model, _ = build_tree_model(config)
    channel_item = model.item(0)
    assert not channel_item.isSelectable()
    assert channel_item.data(NODE_ROLE) is None


def test_node_to_item_still_indexes_every_control_userio_mapping():
    config = parse_file(FIXTURE)
    _model, node_to_item = build_tree_model(config)
    for control in config.controls:
        assert id(control) in node_to_item
        for userio in control.userios:
            assert id(userio) in node_to_item
            for mapping in userio.mappings:
                assert id(mapping) in node_to_item
