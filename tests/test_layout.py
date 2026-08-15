from djmidi.gui import layout


def test_ddj_xp2_pad_grid_is_4x4():
    cells = layout.build_layout("DDJ-XP2")
    pad_cells = [c for c in cells if c.section == "PAD"]
    assert len(pad_cells) == 16
    assert max(c.row for c in pad_cells) - min(c.row for c in pad_cells) == 3
    assert {c.col for c in pad_cells} == {0, 1, 2, 3}


def test_xdj_xz_pad_grid_has_8_pads():
    cells = layout.build_layout("XDJ-XZ")
    pad_cells = [c for c in cells if c.section == "PAD"]
    assert len(pad_cells) == 8


def test_shift_variants_collapse_into_one_cell():
    cells = layout.build_layout("DDJ-XP2")
    labels = [c.label for c in cells]
    assert labels.count("BEAT SYNC") == 1
    assert "BEAT SYNC (+SHIFT)" not in labels


def test_no_two_cells_share_a_row_col_within_same_controller():
    for controller in ("DDJ-XP2", "XDJ-XZ"):
        cells = layout.build_layout(controller)
        positions = [(c.row, c.col) for c in cells]
        assert len(positions) == len(set(positions)), controller


def test_dj_visual_kinds_are_inferred_without_changing_mapping_keys():
    assert layout.visual_kind_for("PAD", "Pad 1") == "pad"
    assert layout.visual_kind_for("DECK", "PLAY") == "button"
    assert layout.visual_kind_for("MIXER", "Channel 1 Volume") == "fader"
    assert layout.visual_kind_for("MIXER", "Channel 1 EQ High") == "knob"
    assert layout.visual_kind_for("DECK", "Jog Wheel") == "jog"


def test_layout_cells_expose_visual_kind_for_dj_rendering():
    cells = layout.build_layout("DDJ-XP2")
    assert all(cell.visual_kind in {"button", "pad", "knob", "fader", "jog"} for cell in cells)
    assert all(cell.visual_kind == "pad" for cell in cells if cell.section == "PAD")
