from pathlib import Path

from djmidi.gui.tree_model import (
    NODE_ROLE,
    build_channel_columns,
    build_tree_model,
)
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


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


def test_channel_columns_one_per_channel_no_channel_wrapper():
    config = parse_file(FIXTURE)
    columns = build_channel_columns(config)
    assert [c for c, _model, _n in columns] == ["8", "10", "12", "14"]
    _channel, model, _node_to_item = columns[0]
    assert model.horizontalHeaderItem(0).text() == "Channel 8"
    # Top level is Note/Control groups directly (no extra "Channel 8" wrapper row).
    top_labels = [model.item(i).text() for i in range(model.rowCount())]
    assert all(label.startswith("Note/Control ") for label in top_labels)
    assert model.rowCount() == 16


def test_channel_columns_node_to_item_covers_only_that_channels_controls():
    config = parse_file(FIXTURE)
    columns = build_channel_columns(config)
    channel, _model, node_to_item = columns[0]
    controls_in_column = [c for c in config.controls if c.channel == channel]
    assert len(controls_in_column) == len(node_to_item.keys() & {id(c) for c in controls_in_column})
    other_controls = [c for c in config.controls if c.channel != channel]
    assert not any(id(c) in node_to_item for c in other_controls)


def test_mapping_rows_show_readable_names_with_the_raw_tag_in_the_tooltip():
    from djmidi.gui.tree_model import mapping_label, mapping_tooltip
    from djmidi.model import MappingElement

    mapping = MappingElement("auto_loop_roll_specific_length", deck_id="2", slot_id="3")
    assert mapping_label(mapping) == "Loop roll  (deck 2, slot 3)"
    assert "auto_loop_roll_specific_length" in mapping_tooltip(mapping)
    unknown = MappingElement("play", deck_id="1", slot_id="0")
    assert mapping_label(unknown) == "play  (deck 1, slot 0)"


def test_channel_filter_still_matches_the_raw_tag():
    from djmidi.gui.tree_model import MappingFilterProxy

    _channel, model, _index = build_channel_columns(parse_file(FIXTURE))[0]
    proxy = MappingFilterProxy()
    proxy.setRecursiveFilteringEnabled(True)
    proxy.setSourceModel(model)
    proxy.setFilterCaseSensitivity(proxy.filterCaseSensitivity().CaseInsensitive)
    proxy.setFilterFixedString("codfather_st")
    assert proxy.rowCount() > 0  # rows now read "Codfather ST", the tag still matches
    proxy.setFilterFixedString("Codfather ST")
    assert proxy.rowCount() > 0
    proxy.setFilterFixedString("no_such_tag_anywhere")
    assert proxy.rowCount() == 0
