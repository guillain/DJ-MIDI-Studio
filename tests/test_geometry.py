from djmidi import catalog
from djmidi.gui.geometry import (
    CONTROL_GEOMETRY,
    ControlGeometry,
    resolve_geometry_label,
)


def test_control_geometry_fractions_are_within_the_unit_square():
    for controller, entries in CONTROL_GEOMETRY.items():
        for label, geom in entries.items():
            assert 0.0 <= geom.x <= 1.0, f"{controller} {label} x out of range"
            assert 0.0 <= geom.y <= 1.0, f"{controller} {label} y out of range"
            assert geom.w > 0.0, f"{controller} {label} w must be positive"
            assert geom.h > 0.0, f"{controller} {label} h must be positive"
            assert geom.x + geom.w <= 1.0, f"{controller} {label} extends past the right edge"
            assert geom.y + geom.h <= 1.0, f"{controller} {label} extends past the bottom edge"
            assert geom.shape in ("rect", "circle")


def test_ddj_xp2_has_no_transport_controls():
    """DDJ-XP2 is a pad/FX companion controller with no deck transport
    section (no PLAY/CUE/SYNC) -- see gui/geometry.py's module docstring."""
    for label in ("PLAY/PAUSE", "CUE", "SYNC"):
        assert label not in CONTROL_GEOMETRY["DDJ-XP2"]


def test_xdj_xz_transport_geometry_covers_the_expected_controls():
    """v0.47.88 (issue #103) added a right-tray (deck 2/4) " (R)" copy of
    every non-pad entry -- the pad grid already had both sides since
    v0.47.55, but the transport/pad-mode cluster stayed left-tray-only
    until now (the module docstring used to (wrongly) claim there was
    nothing left on the right tray to model)."""
    non_pad = {
        "PLAY/PAUSE",
        "CUE",
        "SYNC",
        "SHIFT",  # added v0.47.68 so the emulator's SHIFT-held state is clickable
        "Jog wheel",
        "Tempo",
        "HOT CUE",
        "BEAT LOOP",
        "SLIP LOOP",
        "BEAT JUMP",
    }
    assert set(CONTROL_GEOMETRY["XDJ-XZ"]) == (
        non_pad
        | {f"{name} (R)" for name in non_pad}
        | {f"Pad {n}" for n in range(1, 9)}
        | {f"Pad {n} (R)" for n in range(1, 9)}
    )


def test_xdj_xz_right_deck_entries_do_not_overlap_their_left_counterparts():
    """Same sanity check as DDJ-1000/DDJ-FLX10: every " (R)" entry actually
    landed on the right tray, not a copy-paste of the left fraction."""
    geometry = CONTROL_GEOMETRY["XDJ-XZ"]
    for label, geom in geometry.items():
        if label.endswith(" (R)"):
            left_label = label[: -len(" (R)")]
            left_geom = geometry[left_label]
            assert geom.x > left_geom.x + left_geom.w, (
                f"{label} does not sit to the right of {left_label}"
            )


def test_xdj_xz_hot_cue_pad_grid_is_a_non_overlapping_2x4_layout():
    pads = {n: CONTROL_GEOMETRY["XDJ-XZ"][f"Pad {n}"] for n in range(1, 9)}
    for row in range(2):
        xs = [pads[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [pads[row * 4 + col + 1].y for row in range(2)]
        assert ys == sorted(ys)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = pads[a], pads[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} and Pad {b} overlap"


def test_resolve_geometry_label_extracts_pad_number_from_xdj_xz_pad_names():
    """XDJ-XZ's pad_lookup() produces names like "Deck 1 Performance Pad 3
    (HOT CUE mode)" -- verified against the real lookup path."""
    hit = next(
        hit
        for hit in catalog.lookup("6", "NOTE", "2")  # XDJ-XZ deck-1 pad channel, HOT CUE mode
        if hit.controller == "XDJ-XZ"
    )
    assert resolve_geometry_label("XDJ-XZ", hit.name) == "Pad 3"


def test_resolve_geometry_label_strips_direct_button_suffix_for_hot_cue_modes():
    assert resolve_geometry_label("XDJ-XZ", "HOT CUE (direct button)") == "HOT CUE"
    assert resolve_geometry_label("XDJ-XZ", "BEAT JUMP (direct button, +SHIFT)") == "BEAT JUMP"


def test_ddj_xp2_geometry_covers_the_expected_controls():
    assert set(CONTROL_GEOMETRY["DDJ-XP2"]) == {
        *(f"Pad {n}" for n in range(1, 17)),
        *(f"Pad {n} (R)" for n in range(1, 17)),
        "PAD MODE 1/5",
        "PAD MODE 2/6",
        "PAD MODE 3/7",
        "PAD MODE 4/8",
        "EFFECT 1",
        "EFFECT 2",
        "EFFECT 3",
        "TOUCH STRIP HOLD",
        "FX LEVEL",
        "4 BEAT LOOP",
        "1/2X",
        "2X",
        "QUANTIZE",
        "BEAT SYNC",
        "SILENT CUE",
        "KEY -",
        "KEY +",
        "Rotary Selector",
        "LOAD DECK 1/3",
        "LOAD DECK 2/4",
        "SHIFT",
    }


def test_ddj_xp2_pad_grid_is_a_non_overlapping_4x4_layout():
    """Sanity check the pad grid reads left-to-right, top-to-bottom like the
    real hardware, and that no two pads' bounding boxes overlap."""
    pads = {n: CONTROL_GEOMETRY["DDJ-XP2"][f"Pad {n}"] for n in range(1, 17)}
    for row in range(4):
        xs = [pads[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [pads[row * 4 + col + 1].y for row in range(4)]
        assert ys == sorted(ys)
    for a in range(1, 17):
        for b in range(a + 1, 17):
            ga, gb = pads[a], pads[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} and Pad {b} overlap"


def _assert_non_overlapping_4x4(pads: dict[int, ControlGeometry]) -> None:
    for row in range(4):
        xs = [pads[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [pads[row * 4 + col + 1].y for row in range(4)]
        assert ys == sorted(ys)
    for a in range(1, 17):
        for b in range(a + 1, 17):
            ga, gb = pads[a], pads[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} and Pad {b} overlap"


def test_ddj_xp2_right_pad_grid_is_a_non_overlapping_4x4_layout_to_the_right_of_the_left_grid():
    left = {n: CONTROL_GEOMETRY["DDJ-XP2"][f"Pad {n}"] for n in range(1, 17)}
    right = {n: CONTROL_GEOMETRY["DDJ-XP2"][f"Pad {n} (R)"] for n in range(1, 17)}
    _assert_non_overlapping_4x4(right)
    # The right grid sits entirely to the right of the left grid's last column.
    left_right_edge = max(g.x + g.w for g in left.values())
    assert min(g.x for g in right.values()) >= left_right_edge
    # Same row Y's as the left grid -- it's a horizontal mirror, not a
    # vertically shifted copy.
    for n in range(1, 17):
        assert right[n].y == left[n].y


def test_xdj_xz_right_pad_grid_is_a_non_overlapping_2x4_layout_to_the_right_of_the_left_grid():
    left = {n: CONTROL_GEOMETRY["XDJ-XZ"][f"Pad {n}"] for n in range(1, 9)}
    right = {n: CONTROL_GEOMETRY["XDJ-XZ"][f"Pad {n} (R)"] for n in range(1, 9)}
    for row in range(2):
        xs = [right[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = right[a], right[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} (R) and Pad {b} (R) overlap"
    left_right_edge = max(g.x + g.w for g in left.values())
    assert min(g.x for g in right.values()) >= left_right_edge
    for n in range(1, 9):
        assert right[n].y == left[n].y


def test_resolve_geometry_label_picks_the_right_grid_for_ddj_xp2_deck_2_and_4():
    hit_deck2 = next(
        hit for hit in catalog.lookup("10", "NOTE", "0") if hit.controller == "DDJ-XP2"
    )
    assert resolve_geometry_label("DDJ-XP2", hit_deck2.name) == "Pad 1 (R)"
    hit_deck4 = next(
        hit for hit in catalog.lookup("14", "NOTE", "0") if hit.controller == "DDJ-XP2"
    )
    assert resolve_geometry_label("DDJ-XP2", hit_deck4.name) == "Pad 1 (R)"


def test_resolve_geometry_label_keeps_the_left_grid_for_ddj_xp2_deck_1_and_3():
    hit_deck1 = next(
        hit for hit in catalog.lookup("8", "NOTE", "0") if hit.controller == "DDJ-XP2"
    )
    assert resolve_geometry_label("DDJ-XP2", hit_deck1.name) == "Pad 1"
    hit_deck3 = next(
        hit for hit in catalog.lookup("12", "NOTE", "0") if hit.controller == "DDJ-XP2"
    )
    assert resolve_geometry_label("DDJ-XP2", hit_deck3.name) == "Pad 1"


def test_resolve_geometry_label_picks_the_right_grid_for_xdj_xz_deck_2():
    hit = next(hit for hit in catalog.lookup("7", "NOTE", "2") if hit.controller == "XDJ-XZ")
    assert resolve_geometry_label("XDJ-XZ", hit.name) == "Pad 3 (R)"


def test_control_geometry_is_frozen():
    geom = ControlGeometry(0.1, 0.2, 0.3, 0.4, "rect", "#ffffff")
    try:
        geom.x = 0.5
        raise AssertionError("expected a FrozenInstanceError")
    except AttributeError:
        pass


def test_resolve_geometry_label_matches_exact_catalog_names():
    assert resolve_geometry_label("XDJ-XZ", "PLAY/PAUSE") == "PLAY/PAUSE"
    assert resolve_geometry_label("XDJ-XZ", "SYNC") == "SYNC"


def test_resolve_geometry_label_strips_shift_suffixes():
    assert resolve_geometry_label("XDJ-XZ", "SYNC (long press)") == "SYNC"


def test_resolve_geometry_label_extracts_pad_number_from_ddj_xp2_pad_names():
    """DDJ-XP2's pad_lookup() produces names like "Deck 1 Pad 3 (PAD MODE
    2)", never a bare "Pad 3" -- verified against the real lookup path, not
    a hand-written string, so a future format change here is caught."""
    hit = next(
        hit
        for hit in catalog.lookup("8", "NOTE", "0")  # DDJ-XP2 deck-1 pad channel
        if hit.controller == "DDJ-XP2"
    )
    assert resolve_geometry_label("DDJ-XP2", hit.name) == "Pad 1"


def test_resolve_geometry_label_finds_the_shared_marker_for_a_combined_label():
    """PAD MODE 5 shares DDJ-XP2's PAD MODE 1 button (see catalog/ddj_xp2.py);
    the catalog's raw name is "PAD MODE 5", never "PAD MODE 1/5"."""
    assert resolve_geometry_label("DDJ-XP2", "PAD MODE 5") == "PAD MODE 1/5"
    assert resolve_geometry_label("DDJ-XP2", "LOAD DECK 3") == "LOAD DECK 1/3"


def test_resolve_geometry_label_returns_none_for_an_unmodeled_control():
    assert resolve_geometry_label("DDJ-XP2", "SHIFT") == "SHIFT"  # sanity: this one IS modeled
    assert resolve_geometry_label("DDJ-XP2", "Rotary Selector (+SHIFT press)") == "Rotary Selector"
    assert resolve_geometry_label("XDJ-XZ", "LOOP IN") is None  # not modeled yet
    assert resolve_geometry_label("__unknown_controller__", "PLAY/PAUSE") is None


def test_ddj_rev1_geometry_covers_every_catalog_entry():
    """DDJ-REV1's catalog (catalog/ddj_rev1.py) has exactly six DECK entries
    plus an 8-pad grid -- this is the whole controller, not a subset. Plus
    one display-only "Jog wheel" (no catalog entry -- a continuous control,
    spun by gui/jog.py, v0.47.66). Issue #103 added a right-deck (deck 2/4)
    " (R)" copy of every non-pad entry, same as DDJ-1000 -- the pad grid's
    own right-deck copy is a known-remaining gap (see the module's
    DDJ-REV1 comment: repeated attempts to precisely locate the right
    grid's column/row bounds kept landing on a pad boundary rather than a
    pad center, so it's left for a dedicated follow-up rather than shipped
    imprecise)."""
    non_pad = {
        "Jog wheel",
        "PLAY/PAUSE",
        "CUE",
        "AUTO LOOP",
        "1/2X",
        "2X",
        "SYNC",
    }
    assert set(CONTROL_GEOMETRY["DDJ-REV1"]) == (
        non_pad
        | {f"{name} (R)" for name in non_pad}
        | {f"Pad {n}" for n in range(1, 9)}
    )


def test_ddj_rev1_right_deck_entries_do_not_overlap_their_left_counterparts():
    """A cheap sanity check that every " (R)" entry actually landed on the
    right half of the reference image, not a copy-paste of the left
    fraction."""
    geometry = CONTROL_GEOMETRY["DDJ-REV1"]
    for label, geom in geometry.items():
        if label.endswith(" (R)"):
            left_label = label[: -len(" (R)")]
            left_geom = geometry[left_label]
            assert geom.x > left_geom.x + left_geom.w, (
                f"{label} does not sit to the right of {left_label}"
            )


def test_ddj_rev1_pad_grid_is_a_non_overlapping_2x4_layout():
    pads = {n: CONTROL_GEOMETRY["DDJ-REV1"][f"Pad {n}"] for n in range(1, 9)}
    for row in range(2):
        xs = [pads[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [pads[row * 4 + col + 1].y for row in range(2)]
        assert ys == sorted(ys)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = pads[a], pads[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} and Pad {b} overlap"


def test_resolve_geometry_label_extracts_pad_number_from_ddj_rev1_pad_names():
    """DDJ-REV1's pad_lookup() produces names like "Deck 1 Pad 3 (PAD MODE
    2)" -- verified against the real lookup path."""
    hit = next(
        hit
        for hit in catalog.lookup("8", "NOTE", "18")  # DDJ-REV1 deck-1 pad channel
        if hit.controller == "DDJ-REV1"
    )
    assert resolve_geometry_label("DDJ-REV1", hit.name) == "Pad 3"


def test_numark_mixtrack_pro_fx_geometry_covers_every_catalog_entry():
    """Numark Mixtrack Pro FX's catalog (catalog/numark_mixtrack_pro_fx.py)
    has exactly four DECK entries plus an 8-pad grid -- this is the whole
    controller, not a subset."""
    assert set(CONTROL_GEOMETRY["Numark Mixtrack Pro FX"]) == {
        "PLAY/PAUSE",
        "CUE",
        "SYNC",
        "LOOP",
        *(f"Pad {n}" for n in range(1, 9)),
    }


def test_numark_mixtrack_pro_fx_pad_grid_is_a_non_overlapping_2x4_layout():
    pads = {n: CONTROL_GEOMETRY["Numark Mixtrack Pro FX"][f"Pad {n}"] for n in range(1, 9)}
    for row in range(2):
        xs = [pads[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [pads[row * 4 + col + 1].y for row in range(2)]
        assert ys == sorted(ys)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = pads[a], pads[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} and Pad {b} overlap"


def test_resolve_geometry_label_extracts_pad_number_from_numark_pad_names():
    """Numark Mixtrack Pro FX's pad_lookup() produces names like
    "Deck 1 Pad 4" -- verified against the real lookup path."""
    hit = next(
        hit
        for hit in catalog.lookup("1", "NOTE", "39")  # deck-1 pad channel, note 36+3
        if hit.controller == "Numark Mixtrack Pro FX"
    )
    assert resolve_geometry_label("Numark Mixtrack Pro FX", hit.name) == "Pad 4"


def test_ddj_1000_geometry_covers_every_catalog_entry():
    """DDJ-1000's catalog (catalog/ddj_1000.py) has exactly twelve DECK
    entries plus an 8-pad grid -- this is the whole controller, not a
    subset. Plus one display-only "Jog wheel" (no catalog entry -- a
    continuous control, spun by gui/jog.py, v0.47.64). Issue #103 added a
    right-deck (deck 2/4) " (R)" copy of every non-pad entry (v0.47.83),
    then the pad grid too (v0.47.86) once the shipped left "Pad 1" entry
    -- found imprecise while first measuring the right deck -- was
    re-measured for both decks with a cleaner crop technique (see the
    module's DDJ-1000 comment)."""
    non_pad = {
        "Jog wheel",
        "PLAY/PAUSE",
        "CUE",
        "MASTER TEMPO",
        "BEAT SYNC",
        "KEY SYNC",
        "KEY RESET",
        "LOOP IN",
        "LOOP OUT",
        "4 BEAT LOOP/EXIT",
        "QUANTIZE",
        "SLIP",
        "SLIP REVERSE",
    }
    assert set(CONTROL_GEOMETRY["DDJ-1000"]) == (
        non_pad
        | {f"{name} (R)" for name in non_pad}
        | {f"Pad {n}" for n in range(1, 9)}
        | {f"Pad {n} (R)" for n in range(1, 9)}
    )


def test_ddj_1000_right_deck_entries_do_not_overlap_their_left_counterparts():
    """A cheap sanity check that every " (R)" entry actually landed on the
    right half of the reference image, not a copy-paste of the left
    fraction (which would draw two identical markers stacked on the left
    deck instead of one on each deck)."""
    geometry = CONTROL_GEOMETRY["DDJ-1000"]
    for label, geom in geometry.items():
        if label.endswith(" (R)"):
            left_label = label[: -len(" (R)")]
            left_geom = geometry[left_label]
            assert geom.x > left_geom.x + left_geom.w, (
                f"{label} does not sit to the right of {left_label}"
            )


def test_ddj_1000_pad_grid_is_a_non_overlapping_2x4_layout():
    pads = {n: CONTROL_GEOMETRY["DDJ-1000"][f"Pad {n}"] for n in range(1, 9)}
    for row in range(2):
        xs = [pads[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [pads[row * 4 + col + 1].y for row in range(2)]
        assert ys == sorted(ys)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = pads[a], pads[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} and Pad {b} overlap"


def test_ddj_1000_right_pad_grid_is_a_non_overlapping_2x4_layout_to_the_right_of_the_left_grid():
    """v0.47.86 (issue #103): the right pad grid, re-measured alongside the
    left one after the shipped left "Pad 1" turned out imprecise. Same
    shape check as DDJ-XP2/XDJ-XZ's right grids, but same-row-Y is not
    asserted here -- unlike those two, DDJ-1000's right grid was measured
    independently rather than mirrored, and while it landed on the same
    rows in practice, that's a fact to verify, not assume."""
    left = {n: CONTROL_GEOMETRY["DDJ-1000"][f"Pad {n}"] for n in range(1, 9)}
    right = {n: CONTROL_GEOMETRY["DDJ-1000"][f"Pad {n} (R)"] for n in range(1, 9)}
    for row in range(2):
        xs = [right[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [right[row * 4 + col + 1].y for row in range(2)]
        assert ys == sorted(ys)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = right[a], right[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} (R) and Pad {b} (R) overlap"
    left_right_edge = max(g.x + g.w for g in left.values())
    assert min(g.x for g in right.values()) >= left_right_edge


def test_resolve_geometry_label_picks_the_right_grid_for_ddj_1000_deck_2_and_4():
    """v0.47.86: unlike DDJ-1000's other DECK entries, pad_lookup() names
    already carry a "Deck N" prefix, so wiring DDJ-1000 into
    _RIGHT_GRID_DECKS (once the right grid's geometry existed to resolve
    to) was enough to make this work for free, the same mechanism DDJ-XP2/
    XDJ-XZ already use."""
    hit_deck2 = next(
        hit for hit in catalog.lookup("10", "NOTE", "2") if hit.controller == "DDJ-1000"
    )
    assert resolve_geometry_label("DDJ-1000", hit_deck2.name) == "Pad 3 (R)"
    hit_deck4 = next(
        hit for hit in catalog.lookup("14", "NOTE", "2") if hit.controller == "DDJ-1000"
    )
    assert resolve_geometry_label("DDJ-1000", hit_deck4.name) == "Pad 3 (R)"


def test_resolve_geometry_label_keeps_the_left_grid_for_ddj_1000_deck_1_and_3():
    hit_deck1 = next(
        hit for hit in catalog.lookup("8", "NOTE", "2") if hit.controller == "DDJ-1000"
    )
    assert resolve_geometry_label("DDJ-1000", hit_deck1.name) == "Pad 3"
    hit_deck3 = next(
        hit for hit in catalog.lookup("12", "NOTE", "2") if hit.controller == "DDJ-1000"
    )
    assert resolve_geometry_label("DDJ-1000", hit_deck3.name) == "Pad 3"


def test_resolve_geometry_label_extracts_pad_number_from_ddj_1000_pad_names():
    """DDJ-1000's pad_lookup() produces names like "Deck 1 Pad 3 (HOT CUE,
    PAGE 1)" -- verified against the real lookup path."""
    hit = next(
        hit
        for hit in catalog.lookup("8", "NOTE", "2")  # DDJ-1000 deck-1 pad channel
        if hit.controller == "DDJ-1000"
    )
    assert resolve_geometry_label("DDJ-1000", hit.name) == "Pad 3"


def test_ddj_flx10_geometry_covers_every_catalog_entry():
    """DDJ-FLX10's catalog (catalog/ddj_flx10.py) has exactly twenty-two DECK
    entries plus an 8-pad grid -- this is the whole controller, not a
    subset. Plus one display-only "Jog wheel" (no catalog entry -- a
    continuous control, spun by gui/jog.py, v0.47.65). Issue #103 added a
    right-deck (deck 2/4) " (R)" copy of every non-pad entry (v0.47.85),
    then the pad grid too (v0.47.87, both decks re-measured together with
    the clean-crop technique established for DDJ-1000's re-measurement)."""
    non_pad = {
        "Jog wheel",
        "PLAY/PAUSE",
        "CUE",
        "BEAT SYNC",
        "TEMPO RESET",
        "KEY SYNC",
        "ACTIVE PART DRUMS",
        "ACTIVE PART VOCAL",
        "ACTIVE PART INST",
        "CUE/LOOP CALL <",
        "CUE/LOOP CALL >",
        "LOOP IN / 1/2X",
        "LOOP OUT / 2X",
        "4 BEAT/EXIT",
        "MIX POINT SELECT <",
        "MIX POINT SELECT >",
        "MIX POINT LINK",
        "SLIP REVERSE",
        "QUANTIZE",
        "SLIP",
        "4 BEAT JUMP <",
        "4 BEAT JUMP >",
        "SHIFT",
    }
    assert set(CONTROL_GEOMETRY["DDJ-FLX10"]) == (
        non_pad
        | {f"{name} (R)" for name in non_pad}
        | {f"Pad {n}" for n in range(1, 9)}
        | {f"Pad {n} (R)" for n in range(1, 9)}
    )


def test_ddj_flx10_right_deck_entries_do_not_overlap_their_left_counterparts():
    """A cheap sanity check that every " (R)" entry actually landed on the
    right half of the reference image, not a copy-paste of the left
    fraction."""
    geometry = CONTROL_GEOMETRY["DDJ-FLX10"]
    for label, geom in geometry.items():
        if label.endswith(" (R)"):
            left_label = label[: -len(" (R)")]
            left_geom = geometry[left_label]
            assert geom.x > left_geom.x + left_geom.w, (
                f"{label} does not sit to the right of {left_label}"
            )


def test_ddj_flx10_pad_grid_is_a_non_overlapping_2x4_layout():
    pads = {n: CONTROL_GEOMETRY["DDJ-FLX10"][f"Pad {n}"] for n in range(1, 9)}
    for row in range(2):
        xs = [pads[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [pads[row * 4 + col + 1].y for row in range(2)]
        assert ys == sorted(ys)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = pads[a], pads[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} and Pad {b} overlap"


def test_ddj_flx10_right_pad_grid_is_a_non_overlapping_2x4_layout_to_the_right_of_the_left_grid():
    """v0.47.87 (issue #103): the right pad grid, measured alongside a
    re-measurement of the left one. Same shape check as DDJ-1000's right
    grid test."""
    left = {n: CONTROL_GEOMETRY["DDJ-FLX10"][f"Pad {n}"] for n in range(1, 9)}
    right = {n: CONTROL_GEOMETRY["DDJ-FLX10"][f"Pad {n} (R)"] for n in range(1, 9)}
    for row in range(2):
        xs = [right[row * 4 + col + 1].x for col in range(4)]
        assert xs == sorted(xs)
    for col in range(4):
        ys = [right[row * 4 + col + 1].y for row in range(2)]
        assert ys == sorted(ys)
    for a in range(1, 9):
        for b in range(a + 1, 9):
            ga, gb = right[a], right[b]
            x_overlap = ga.x < gb.x + gb.w and gb.x < ga.x + ga.w
            y_overlap = ga.y < gb.y + gb.h and gb.y < ga.y + ga.h
            assert not (x_overlap and y_overlap), f"Pad {a} (R) and Pad {b} (R) overlap"
    left_right_edge = max(g.x + g.w for g in left.values())
    assert min(g.x for g in right.values()) >= left_right_edge
    # Measured together, not mirrored -- both grids landed on the same
    # rows in practice, so assert that fact (unlike DDJ-1000's, whose left
    # and right grids were measured in two separate PRs and only turned
    # out to share rows by coincidence -- here it's expected by
    # construction, worth pinning down either way).
    for n in range(1, 9):
        assert right[n].y == left[n].y


def test_resolve_geometry_label_picks_the_right_grid_for_ddj_flx10_deck_2_and_4():
    hit_deck2 = next(
        hit for hit in catalog.lookup("10", "NOTE", "2") if hit.controller == "DDJ-FLX10"
    )
    assert resolve_geometry_label("DDJ-FLX10", hit_deck2.name) == "Pad 3 (R)"
    hit_deck4 = next(
        hit for hit in catalog.lookup("14", "NOTE", "2") if hit.controller == "DDJ-FLX10"
    )
    assert resolve_geometry_label("DDJ-FLX10", hit_deck4.name) == "Pad 3 (R)"


def test_resolve_geometry_label_keeps_the_left_grid_for_ddj_flx10_deck_1_and_3():
    hit_deck1 = next(
        hit for hit in catalog.lookup("8", "NOTE", "2") if hit.controller == "DDJ-FLX10"
    )
    assert resolve_geometry_label("DDJ-FLX10", hit_deck1.name) == "Pad 3"
    hit_deck3 = next(
        hit for hit in catalog.lookup("12", "NOTE", "2") if hit.controller == "DDJ-FLX10"
    )
    assert resolve_geometry_label("DDJ-FLX10", hit_deck3.name) == "Pad 3"


def test_resolve_geometry_label_extracts_pad_number_from_ddj_flx10_pad_names():
    """DDJ-FLX10's pad_lookup() produces names like "Deck 1 Pad 3 (HOT CUE,
    PAGE 1)" -- verified against the real lookup path."""
    hit = next(
        hit
        for hit in catalog.lookup("8", "NOTE", "2")  # DDJ-FLX10 deck-1 pad channel
        if hit.controller == "DDJ-FLX10"
    )
    assert resolve_geometry_label("DDJ-FLX10", hit.name) == "Pad 3"
