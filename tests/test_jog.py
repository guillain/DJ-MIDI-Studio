"""gui/jog.py -- live jog-wheel turn resolution (Qt-free)."""

from djmidi.gui import jog


def test_decode_jog_delta_is_signed_around_0x40():
    assert jog.decode_jog_delta(0x41) == 1
    assert jog.decode_jog_delta(0x45) == 5
    assert jog.decode_jog_delta(0x3F) == -1
    assert jog.decode_jog_delta(0x3B) == -5
    assert jog.decode_jog_delta(0x40) == 0


def test_decode_jog_delta_clamps_and_tolerates_garbage():
    assert jog.decode_jog_delta(0x7F) == 63
    assert jog.decode_jog_delta(0x00) == -63
    assert jog.decode_jog_delta(None) == 0
    assert jog.decode_jog_delta("not a number") == 0


def test_jog_keys_resolve_xdj_xz_platter_and_wheel_side_by_deck_channel():
    # Left decks (1, 3) -> left jog; right decks (2, 4) -> right-tray jog.
    # 0x22/0x26 ("34"/"38") are XDJ-XZ-only data1s (no DDJ-1000 collision).
    assert jog.jog_cell_keys_for_event("1", "Control Change", "34") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel")
    ]
    assert jog.jog_cell_keys_for_event("3", "Control Change", "34") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel")
    ]
    assert jog.jog_cell_keys_for_event("2", "Control Change", "38") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel (R)")
    ]
    assert jog.jog_cell_keys_for_event("4", "Control Change", "38") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel (R)")
    ]
    # 0x21 ("33") collides with DDJ-1000's platter; the XDJ-XZ marker is
    # still the side-correct one.
    assert ("XDJ-XZ", "DISPLAY", "Jog wheel") in jog.jog_cell_keys_for_event(
        "3", "Control Change", "33"
    )
    assert ("XDJ-XZ", "DISPLAY", "Jog wheel (R)") in jog.jog_cell_keys_for_event(
        "2", "Control Change", "33"
    )


def test_jog_keys_empty_for_non_jog_events():
    # A Note (the jog *touch*, not the turn) is never a jog turn.
    assert jog.jog_cell_keys_for_event("1", "Note On", "34") == []
    # A CC number that isn't a jog-turn data1.
    assert jog.jog_cell_keys_for_event("1", "Control Change", "7") == []
    # A channel with no jog mapping (XDJ-XZ mixer/FX is channel 5).
    assert jog.jog_cell_keys_for_event("5", "Control Change", "34") == []
    assert jog.jog_cell_keys_for_event(None, None, None) == []


def test_ddj_1000_platter_resolves_on_every_deck_channel():
    # DDJ-1000's schematic draws only the left deck, so any of channels
    # 1-4 spins its single "Jog wheel". Plain 0x21, +SEARCH 0x29, +SHIFT 0x1F.
    for ch in ("1", "2", "3", "4"):
        assert ("DDJ-1000", "DISPLAY", "Jog wheel") in jog.jog_cell_keys_for_event(
            ch, "Control Change", "33"
        )
    assert jog.jog_cell_keys_for_event("2", "Control Change", "31") == [
        ("DDJ-1000", "DISPLAY", "Jog wheel")
    ]


def test_shared_jog_cc_returns_both_controllers_markers():
    # data1 0x21 ("33") is XDJ-XZ's wheel-side jog *and* DDJ-1000's platter,
    # both on the deck channel -- each view spins only its own.
    keys = jog.jog_cell_keys_for_event("1", "Control Change", "33")
    assert ("XDJ-XZ", "DISPLAY", "Jog wheel") in keys
    assert ("DDJ-1000", "DISPLAY", "Jog wheel") in keys
