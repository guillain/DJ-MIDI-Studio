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
    # XDJ-XZ is the only controller with two physical jogs: left decks (1, 3)
    # -> "Jog wheel", right-tray decks (2, 4) -> "Jog wheel (R)". Every
    # XDJ-XZ jog data1 also collides with DDJ-FLX10's (both 2-deck Pioneer
    # gear on the deck channel), so check membership + the correct side,
    # never an exact one-element list.
    for data1 in ("34", "41"):  # platter 0x22 / 0x29
        for left in ("1", "3"):
            keys = jog.jog_cell_keys_for_event(left, "Control Change", data1)
            assert ("XDJ-XZ", "DISPLAY", "Jog wheel") in keys
            assert ("XDJ-XZ", "DISPLAY", "Jog wheel (R)") not in keys
        for right in ("2", "4"):
            keys = jog.jog_cell_keys_for_event(right, "Control Change", data1)
            assert ("XDJ-XZ", "DISPLAY", "Jog wheel (R)") in keys
            assert ("XDJ-XZ", "DISPLAY", "Jog wheel") not in keys


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


def test_ddj_flx10_platter_and_wheel_side_resolve_on_every_deck_channel():
    # Vinyl-on 0x22, vinyl-off 0x23, +4-beat-jump 0x29, +SHIFT 0x1F platter;
    # 0x21 / 0x26 wheel-side. Single left-deck marker on any deck channel.
    for data1 in ("34", "35", "41", "31", "33", "38"):
        for ch in ("1", "2", "3", "4"):
            assert ("DDJ-FLX10", "DISPLAY", "Jog wheel") in jog.jog_cell_keys_for_event(
                ch, "Control Change", data1
            )
    # 0x29 ("41", +4 BEAT JUMP) is FLX10's alone among the vinyl-style jogs
    # -- DDJ-REV1 has no such variant.
    assert jog.jog_cell_keys_for_event("1", "Control Change", "41") == [
        ("XDJ-XZ", "DISPLAY", "Jog wheel"),
        ("DDJ-1000", "DISPLAY", "Jog wheel"),
        ("DDJ-FLX10", "DISPLAY", "Jog wheel"),
    ]


def test_ddj_rev1_platter_and_wheel_side_resolve_on_every_deck_channel():
    # Same jog CCs as DDJ-FLX10 minus 0x29 (no +4 BEAT JUMP variant).
    for data1 in ("34", "35", "31", "33", "38"):
        for ch in ("1", "2", "3", "4"):
            assert ("DDJ-REV1", "DISPLAY", "Jog wheel") in jog.jog_cell_keys_for_event(
                ch, "Control Change", data1
            )
    assert ("DDJ-REV1", "DISPLAY", "Jog wheel") not in jog.jog_cell_keys_for_event(
        "1", "Control Change", "41"
    )


def test_shared_jog_cc_returns_every_controllers_marker():
    # data1 0x21 ("33") is a jog CC for XDJ-XZ (wheel-side), DDJ-1000
    # (platter), DDJ-FLX10 and DDJ-REV1 (wheel-side), all on the deck
    # channel -- each view spins only its own.
    keys = set(jog.jog_cell_keys_for_event("1", "Control Change", "33"))
    assert keys == {
        ("XDJ-XZ", "DISPLAY", "Jog wheel"),
        ("DDJ-1000", "DISPLAY", "Jog wheel"),
        ("DDJ-FLX10", "DISPLAY", "Jog wheel"),
        ("DDJ-REV1", "DISPLAY", "Jog wheel"),
    }
