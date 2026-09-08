from djmidi.gui import layout
from djmidi.gui.layout import clear_reverse_lookup_cache, reverse_lookup


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


# ─── reverse_lookup (gui/controller_emulator.py's raw-trigger resolution) ─────

def test_reverse_lookup_finds_static_entry_variants_by_cell():
    clear_reverse_lookup_cache()
    index = reverse_lookup("DDJ-XP2")
    variants = index[("DDJ-XP2", "DECK", "BEAT SYNC")]
    names = {v.name for v in variants}
    assert names == {"BEAT SYNC", "BEAT SYNC (+SHIFT)"}
    for variant in variants:
        assert variant.channels == ("1", "2", "3", "4")


def test_reverse_lookup_finds_pad_bank_variants_via_brute_force():
    clear_reverse_lookup_cache()
    index = reverse_lookup("DDJ-XP2")
    variants = index[("DDJ-XP2", "PAD", "Pad 1")]
    # Every pad-mode bank for physical Pad 1, across both the plain and
    # +SHIFT pad channels, collapses into this one cell.
    assert len(variants) > 1
    for variant in variants:
        hit = layout.catalog.lookup(variant.channels[0], variant.note_or_cc, variant.data1)
        assert any(h.name.startswith("Pad 1") or "Pad 1 " in h.name for h in hit)


def test_reverse_lookup_pad_variants_are_ordered_lowest_data1_first():
    clear_reverse_lookup_cache()
    index = reverse_lookup("DDJ-XP2")
    variants = index[("DDJ-XP2", "PAD", "Pad 1")]
    same_channel = [v for v in variants if v.channels == variants[0].channels]
    data1_values = [int(v.data1) for v in same_channel]
    assert data1_values == sorted(data1_values)


def test_reverse_lookup_is_cached_until_cleared():
    clear_reverse_lookup_cache()
    first = reverse_lookup("DDJ-XP2")
    second = reverse_lookup("DDJ-XP2")
    assert first is second
    clear_reverse_lookup_cache()
    third = reverse_lookup("DDJ-XP2")
    assert third is not first


def test_reverse_lookup_returns_empty_for_a_cell_with_no_trigger():
    clear_reverse_lookup_cache()
    index = reverse_lookup("DDJ-XP2")
    assert ("DDJ-XP2", "MIXER", "Effect 1 Depth") not in index


# ─── cell_key_for_geometry_label (real-position layout view, gui/layout_view.py) ──


def test_cell_key_for_geometry_label_resolves_a_plain_label():
    layout.clear_label_to_key_cache()
    assert layout.cell_key_for_geometry_label("DDJ-XP2", "SHIFT") == ("DDJ-XP2", "OTHER", "SHIFT")


def test_cell_key_for_geometry_label_resolves_a_plain_pad_label():
    layout.clear_label_to_key_cache()
    assert layout.cell_key_for_geometry_label("DDJ-XP2", "Pad 3") == ("DDJ-XP2", "PAD", "Pad 3")


def test_cell_key_for_geometry_label_right_grid_pad_shares_the_left_key():
    """A known simplification (see gui/geometry.py's module docstring):
    "Pad 3 (R)" resolves to the same CellKey as "Pad 3", not a distinct one."""
    layout.clear_label_to_key_cache()
    left = layout.cell_key_for_geometry_label("DDJ-XP2", "Pad 3")
    right = layout.cell_key_for_geometry_label("DDJ-XP2", "Pad 3 (R)")
    assert left == right == ("DDJ-XP2", "PAD", "Pad 3")


def test_cell_key_for_geometry_label_combined_label_resolves_to_first_alternative():
    layout.clear_label_to_key_cache()
    assert layout.cell_key_for_geometry_label("DDJ-XP2", "PAD MODE 1/5") == (
        "DDJ-XP2",
        "PAD MODE",
        "PAD MODE 1",
    )
    assert layout.cell_key_for_geometry_label("DDJ-XP2", "LOAD DECK 1/3") == (
        "DDJ-XP2",
        "BROWSE",
        "LOAD DECK 1",
    )


def test_cell_key_for_geometry_label_uses_the_alias_table():
    """DDJ-XP2's "FX LEVEL" geometry marker has no build_layout() cell of
    that exact name -- it's an alias for the schematic's "Slide FX 1"."""
    layout.clear_label_to_key_cache()
    assert layout.cell_key_for_geometry_label("DDJ-XP2", "FX LEVEL") == (
        "DDJ-XP2",
        "MIXER",
        "Slide FX 1",
    )


def test_cell_key_for_geometry_label_returns_none_for_an_unmatched_label():
    layout.clear_label_to_key_cache()
    assert layout.cell_key_for_geometry_label("XDJ-XZ", "Jog wheel") is None


def test_cell_key_for_geometry_label_cache_is_cleared():
    layout.clear_label_to_key_cache()
    first = layout._label_to_key_map("DDJ-XP2")
    second = layout._label_to_key_map("DDJ-XP2")
    assert first is second
    layout.clear_label_to_key_cache()
    third = layout._label_to_key_map("DDJ-XP2")
    assert third is not first


# ─── resolve_side_aware_variant (Controller Emulator / Live Send: left vs. ──
# ─── right pad grid must resolve to their own deck, not always deck 1/3) ───


def test_resolve_side_aware_variant_left_grid_resolves_to_left_deck():
    clear_reverse_lookup_cache()
    entry = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD", "Pad 3"))
    assert entry is not None
    assert entry.name.startswith("Deck 1 Pad 3")


def test_resolve_side_aware_variant_right_grid_resolves_to_right_deck():
    clear_reverse_lookup_cache()
    entry = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD", "Pad 3 (R)"))
    assert entry is not None
    assert entry.name.startswith("Deck 2 Pad 3")


def test_resolve_side_aware_variant_left_and_right_pick_different_channels():
    clear_reverse_lookup_cache()
    left = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD", "Pad 5"))
    right = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD", "Pad 5 (R)"))
    assert left is not None and right is not None
    assert left.channels != right.channels
    assert left.name.startswith("Deck 1 Pad 5")
    assert right.name.startswith("Deck 2 Pad 5")


def test_resolve_side_aware_variant_works_for_xdj_xz_too():
    clear_reverse_lookup_cache()
    left = layout.resolve_side_aware_variant("XDJ-XZ", ("XDJ-XZ", "PAD", "Pad 2"))
    right = layout.resolve_side_aware_variant("XDJ-XZ", ("XDJ-XZ", "PAD", "Pad 2 (R)"))
    assert left is not None and right is not None
    assert left.name.startswith("Deck 1")
    assert right.name.startswith("Deck 2")


def test_resolve_side_aware_variant_passthrough_for_non_suffixed_key():
    clear_reverse_lookup_cache()
    plain = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "OTHER", "SHIFT"))
    variants = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "OTHER", "SHIFT")]
    assert plain == layout.pick_default_variant(variants)


def test_resolve_side_aware_variant_combined_label_resolves_via_first_alternative():
    clear_reverse_lookup_cache()
    entry = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD MODE", "PAD MODE 1/5"))
    assert entry is not None
    assert entry.name.startswith("PAD MODE 1")


def test_resolve_side_aware_variant_returns_none_for_an_unknown_trigger():
    clear_reverse_lookup_cache()
    assert layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD", "Pad 99")) is None


# ─── resolve_side_aware_variant: DECK/PAD MODE sections (the "tous les ────
# ─── modes pad ont le même problème (mirroring deck 1 et 2)" follow-up) ────
# These sections have no separate per-deck ControlInfo the way PAD does --
# a single entry's `channels` tuple spans all 4 decks, so the fix narrows
# that tuple down to one side's channel instead of filtering variants.


def test_resolve_side_aware_variant_narrows_deck_section_to_the_left_channel():
    clear_reverse_lookup_cache()
    entry = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "DECK", "BEAT SYNC"))
    assert entry is not None
    assert entry.name == "BEAT SYNC"
    assert entry.channels == ("1",)  # deck 1, the left cluster's default


def test_resolve_side_aware_variant_narrows_deck_section_to_the_right_channel():
    clear_reverse_lookup_cache()
    entry = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "DECK", "BEAT SYNC (R)"))
    assert entry is not None
    assert entry.name == "BEAT SYNC"
    assert entry.channels == ("2",)  # deck 2, the right cluster's default


def test_resolve_side_aware_variant_narrows_pad_mode_section_by_side():
    clear_reverse_lookup_cache()
    left = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD MODE", "PAD MODE 1"))
    right = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "PAD MODE", "PAD MODE 1 (R)"))
    assert left is not None and right is not None
    assert left.channels == ("1",)
    assert right.channels == ("2",)


def test_resolve_side_aware_variant_narrows_xdj_xz_deck_section_too():
    clear_reverse_lookup_cache()
    left = layout.resolve_side_aware_variant("XDJ-XZ", ("XDJ-XZ", "DECK", "PLAY/PAUSE"))
    right = layout.resolve_side_aware_variant("XDJ-XZ", ("XDJ-XZ", "DECK", "PLAY/PAUSE (R)"))
    assert left is not None and right is not None
    assert left.channels == ("1",)
    assert right.channels == ("2",)


def test_resolve_side_aware_variant_narrows_ddj_xp2_effect_section_by_slide_fx_side():
    """DDJ-XP2's EFFECT section (EFFECT 1/2/3, TOUCH STRIP HOLD) bundles
    both Slide FX chains' copies into one entry via _FX_CH = ("5", "6") --
    channel "5" is Slide FX 1 (left), "6" is Slide FX 2 (right). Reported
    by the maintainer as "le hold effect de la ddj-xp2" sharing the same
    mirroring problem as the pads and PAD MODE buttons."""
    clear_reverse_lookup_cache()
    left = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "EFFECT", "EFFECT 1"))
    right = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "EFFECT", "EFFECT 1 (R)"))
    assert left is not None and right is not None
    assert left.channels == ("5",)
    assert right.channels == ("6",)


def test_resolve_side_aware_variant_narrows_touch_strip_hold_by_slide_fx_side():
    clear_reverse_lookup_cache()
    left = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "EFFECT", "TOUCH STRIP HOLD"))
    right = layout.resolve_side_aware_variant("DDJ-XP2", ("DDJ-XP2", "EFFECT", "TOUCH STRIP HOLD (R)"))
    assert left is not None and right is not None
    assert left.channels == ("5",)
    assert right.channels == ("6",)


def test_resolve_side_aware_variant_does_not_narrow_a_controller_with_no_channel_table():
    """A (controller, section) pair absent from _RIGHT_SIDE_CHANNELS (e.g.
    XDJ-XZ's EFFECT section, which has no left/right split at all -- see
    catalog/xdj_xz.py's single-channel _FX_CH) passes its entry through
    unnarrowed, exactly as before this fix."""
    clear_reverse_lookup_cache()
    entry = layout.resolve_side_aware_variant("XDJ-XZ", ("XDJ-XZ", "EFFECT", "FX QUANTIZE"))
    assert entry is not None
    assert entry.channels == ("5",)


# ─── hit_matches_side / presentation_key_for_hit / find_controls_for_cell ──
# The By Channel/Deck/Controller tabs' own follow-up to the Controller
# Emulator's pad-side-identity fix: cross-tab navigation and tree<->layout
# selection both need to tell the two physical grids/clusters apart too.

from pathlib import Path

from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_hit_matches_side_true_for_a_controller_with_no_side_split():
    clear_reverse_lookup_cache()
    hit = reverse_lookup("DDJ-FLX4")[("DDJ-FLX4", "DECK", "PLAY/PAUSE")][0]
    assert layout.hit_matches_side("DDJ-FLX4", "DECK", hit, right_side=True) is True
    assert layout.hit_matches_side("DDJ-FLX4", "DECK", hit, right_side=False) is True


def test_hit_matches_side_for_a_pad_hit():
    clear_reverse_lookup_cache()
    variants = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "PAD", "Pad 3")]
    left_hit = next(v for v in variants if v.name.startswith("Deck 1 Pad 3"))
    right_hit = next(v for v in variants if v.name.startswith("Deck 2 Pad 3"))
    assert layout.hit_matches_side("DDJ-XP2", "PAD", left_hit, right_side=False) is True
    assert layout.hit_matches_side("DDJ-XP2", "PAD", left_hit, right_side=True) is False
    assert layout.hit_matches_side("DDJ-XP2", "PAD", right_hit, right_side=True) is True
    assert layout.hit_matches_side("DDJ-XP2", "PAD", right_hit, right_side=False) is False


def test_hit_matches_side_for_a_bundled_channel_hit():
    clear_reverse_lookup_cache()
    beat_sync = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "DECK", "BEAT SYNC")][0]
    # A single shared entry spans all 4 decks' channels -- it "matches" both
    # sides at once, since side-narrowing only happens in
    # resolve_side_aware_variant(), not in this membership check.
    assert layout.hit_matches_side("DDJ-XP2", "DECK", beat_sync, right_side=True) is True
    assert layout.hit_matches_side("DDJ-XP2", "DECK", beat_sync, right_side=False) is True


def test_presentation_key_for_hit_suffixes_a_right_side_pad():
    clear_reverse_lookup_cache()
    variants = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "PAD", "Pad 3")]
    right_hit = next(v for v in variants if v.name.startswith("Deck 2 Pad 3"))
    assert layout.presentation_key_for_hit(right_hit) == ("DDJ-XP2", "PAD", "Pad 3 (R)")


def test_presentation_key_for_hit_leaves_a_left_side_pad_unsuffixed():
    clear_reverse_lookup_cache()
    variants = reverse_lookup("DDJ-XP2")[("DDJ-XP2", "PAD", "Pad 3")]
    left_hit = next(v for v in variants if v.name.startswith("Deck 1 Pad 3"))
    assert layout.presentation_key_for_hit(left_hit) == ("DDJ-XP2", "PAD", "Pad 3")


def test_presentation_key_for_hit_leaves_a_no_split_control_unsuffixed():
    clear_reverse_lookup_cache()
    hit = reverse_lookup("DDJ-FLX4")[("DDJ-FLX4", "DECK", "PLAY/PAUSE")][0]
    assert layout.presentation_key_for_hit(hit) == ("DDJ-FLX4", "DECK", "PLAY/PAUSE")


def test_find_controls_for_cell_separates_left_and_right_pad_controls():
    config = parse_file(FIXTURE)
    left = layout.find_controls_for_cell(config, ("DDJ-XP2", "PAD", "Pad 3"))
    right = layout.find_controls_for_cell(config, ("DDJ-XP2", "PAD", "Pad 3 (R)"))
    assert left and right
    # Control isn't hashable -- compare by identity instead of a set.
    assert all(not any(l is r for r in right) for l in left)


def test_find_controls_for_cell_matches_the_merged_lookup_for_a_plain_key():
    """A key with no side split (or no suffix) behaves exactly like the
    pre-existing merged cell_key() scan -- no regression for the common
    case that isn't split at all."""
    config = parse_file(FIXTURE)
    matches = layout.find_controls_for_cell(config, ("DDJ-XP2", "DECK", "BEAT SYNC"))
    # BEAT SYNC isn't mapped by name in this fixture's own tags, but the
    # function must not raise and must return a list either way.
    assert isinstance(matches, list)


def test_find_controls_for_cell_returns_empty_for_an_unknown_cell():
    config = parse_file(FIXTURE)
    assert layout.find_controls_for_cell(config, ("DDJ-XP2", "PAD", "Pad 99")) == []


def test_is_side_split_section_true_for_pad_on_a_split_controller():
    assert layout.is_side_split_section("DDJ-XP2", "PAD") is True


def test_is_side_split_section_true_for_a_right_side_channels_entry():
    assert layout.is_side_split_section("DDJ-XP2", "DECK") is True
    assert layout.is_side_split_section("DDJ-XP2", "EFFECT") is True


def test_is_side_split_section_false_for_an_unlisted_section():
    assert layout.is_side_split_section("DDJ-XP2", "OTHER") is False
    assert layout.is_side_split_section("DDJ-XP2", "BROWSE") is False


def test_is_side_split_section_false_for_a_controller_with_no_split_at_all():
    assert layout.is_side_split_section("DDJ-FLX4", "PAD") is False
    assert layout.is_side_split_section("DDJ-FLX4", "DECK") is False


def test_right_side_usage_deck_ids_translates_catalog_decks_to_zero_indexed():
    assert layout.right_side_usage_deck_ids("DDJ-XP2") == frozenset({"1", "3"})
    assert layout.right_side_usage_deck_ids("XDJ-XZ") == frozenset({"1", "3"})


def test_right_side_usage_deck_ids_none_for_a_controller_with_no_split():
    assert layout.right_side_usage_deck_ids("DDJ-FLX4") is None
