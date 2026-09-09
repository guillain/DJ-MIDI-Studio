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
    assert jog.jog_cell_keys_for_event("1", "Control Change", "34") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel")
    ]
    assert jog.jog_cell_keys_for_event("3", "Control Change", "33") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel")
    ]
    assert jog.jog_cell_keys_for_event("2", "Control Change", "41") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel (R)")
    ]
    assert jog.jog_cell_keys_for_event("4", "Control Change", "38") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel (R)")
    ]


def test_jog_keys_empty_for_non_jog_events():
    # A Note (the jog *touch*, not the turn) is never a jog turn.
    assert jog.jog_cell_keys_for_event("1", "Note On", "34") == []
    # A CC number that isn't a jog-turn data1.
    assert jog.jog_cell_keys_for_event("1", "Control Change", "7") == []
    # A channel with no jog mapping (XDJ-XZ mixer/FX is channel 5).
    assert jog.jog_cell_keys_for_event("5", "Control Change", "34") == []
    assert jog.jog_cell_keys_for_event(None, None, None) == []
