from djmidi.gui import layout


def test_ddj_xp2_pad_grid_is_4x4():
    cells = layout.build_layout("DDJ-XP2")
    pad_cells = [c for c in cells if c.section == "PAD"]
    assert len(pad_cells) == 16
    assert max(c.row for c in pad_cells) - min(c.row for c in pad_cells) == 3
    assert {c.col for c in pad_cells} == {4, 5, 6, 7}


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


def test_dj_layouts_include_display_only_mixer_controls():
    xdj_cells = layout.build_layout("XDJ-XZ")
    mixer = {cell.label: cell.visual_kind for cell in xdj_cells if cell.section == "MIXER"}
    assert mixer["Channel 1 Trim"] == "knob"
    assert mixer["Channel 1 Volume"] == "fader"
    assert mixer["Crossfader"] == "fader"

    xp2_cells = layout.build_layout("DDJ-XP2")
    assert any(cell.label == "Slide FX 1" and cell.visual_kind == "fader" for cell in xp2_cells)


def test_xdj_and_xp2_use_separate_physical_zones():
    xdj = layout.build_layout("XDJ-XZ")
    xdj_by_section = {section: min((cell.col, cell.row) for cell in xdj if cell.section == section) for section in {cell.section for cell in xdj}}
    assert xdj_by_section["PAD"] == (4, 1)
    assert xdj_by_section["DECK"] == (4, 5)
    assert xdj_by_section["EFFECT"] == (14, 1)
    assert xdj_by_section["MIXER"] == (9, 5)

    xp2 = layout.build_layout("DDJ-XP2")
    xp2_by_section = {section: min((cell.col, cell.row) for cell in xp2 if cell.section == section) for section in {cell.section for cell in xp2}}
    assert xp2_by_section["PAD"] == (4, 1)
    assert xp2_by_section["PAD MODE"] == (10, 1)


def test_zone_anchors_do_not_vertically_abut():
    """Vertically-adjacent zones must leave a row gap so the framed zone
    panels in the layout view don't overlap their neighbour's header."""
    for controller in ("DDJ-XP2", "XDJ-XZ"):
        cells = layout.build_layout(controller)
        by_col: dict[int, list] = {}
        for cell in cells:
            by_col.setdefault(cell.col, []).append(cell)
        spans: dict[str, tuple[int, int]] = {}
        for cell in cells:
            lo, hi = spans.get(cell.section, (cell.row, cell.row))
            spans[cell.section] = (min(lo, cell.row), max(hi, cell.row))
        cols_by_section = {
            s: {c.col for c in cells if c.section == s} for s in spans
        }
        sections = list(spans)
        for i, a in enumerate(sections):
            for b in sections[i + 1 :]:
                if cols_by_section[a] & cols_by_section[b]:
                    a_lo, a_hi = spans[a]
                    b_lo, b_hi = spans[b]
                    # overlapping columns => must be clearly separated in rows
                    assert a_hi + 1 < b_lo or b_hi + 1 < a_lo, (controller, a, b)
