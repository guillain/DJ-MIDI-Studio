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
    assert set(CONTROL_GEOMETRY["XDJ-XZ"]) == {
        "PLAY/PAUSE",
        "CUE",
        "SYNC",
        "Jog wheel",
        "Tempo",
        "HOT CUE",
        "BEAT LOOP",
        "SLIP LOOP",
        "BEAT JUMP",
        *(f"Pad {n}" for n in range(1, 9)),
    }


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
        for hit in catalog.lookup("8", "NOTE", "12")  # DDJ-XP2 deck-1 pad channel
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
    plus an 8-pad grid -- this is the whole controller, not a subset."""
    assert set(CONTROL_GEOMETRY["DDJ-REV1"]) == {
        "PLAY/PAUSE",
        "CUE",
        "AUTO LOOP",
        "1/2X",
        "2X",
        "SYNC",
        *(f"Pad {n}" for n in range(1, 9)),
    }


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
    subset."""
    assert set(CONTROL_GEOMETRY["DDJ-1000"]) == {
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
        *(f"Pad {n}" for n in range(1, 9)),
    }


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
    subset."""
    assert set(CONTROL_GEOMETRY["DDJ-FLX10"]) == {
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
        *(f"Pad {n}" for n in range(1, 9)),
    }


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


def test_resolve_geometry_label_extracts_pad_number_from_ddj_flx10_pad_names():
    """DDJ-FLX10's pad_lookup() produces names like "Deck 1 Pad 3 (HOT CUE,
    PAGE 1)" -- verified against the real lookup path."""
    hit = next(
        hit
        for hit in catalog.lookup("8", "NOTE", "2")  # DDJ-FLX10 deck-1 pad channel
        if hit.controller == "DDJ-FLX10"
    )
    assert resolve_geometry_label("DDJ-FLX10", hit.name) == "Pad 3"
