from seratomidiconf.gui.controller_tree import CELL_KEY_ROLE, build_controller_columns


def test_one_column_per_controller():
    columns = build_controller_columns({})
    assert [c for c, _model, _flags in columns] == ["DDJ-XP2", "XDJ-XZ"]


def test_pad_section_first_and_flagged_used_when_usage_present():
    usage = {("DDJ-XP2", "PAD", "Pad 1"): {"0": {"codfather_st"}}}
    columns = build_controller_columns(usage)
    _controller, model, flags = columns[0]
    assert model.item(0).text() == "PAD"
    pad_row, pad_used = flags[0]
    assert pad_row == 0
    assert pad_used is True


def test_sections_without_usage_are_flagged_unused():
    columns = build_controller_columns({})
    _controller, _model, flags = columns[0]
    assert all(not used for _row, used in flags)


def test_leaf_carries_cell_key_and_reflects_usage_in_text():
    usage = {("DDJ-XP2", "PAD", "Pad 1"): {"2": {"codfather_st"}}}
    columns = build_controller_columns(usage)
    _controller, model, _flags = columns[0]
    pad_section = model.item(0)
    pad1_leaf = pad_section.child(0)
    assert pad1_leaf.data(CELL_KEY_ROLE) == ("DDJ-XP2", "PAD", "Pad 1")
    assert "codfather_st" in pad1_leaf.text()
    assert "D2" in pad1_leaf.text()

    pad2_leaf = pad_section.child(1)
    assert "not used" in pad2_leaf.text()
