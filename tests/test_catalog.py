from pathlib import Path

from djmidi import catalog
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_every_control_in_sample_file_resolves_via_ddj_xp2_pad_grid():
    config = parse_file(FIXTURE)
    for control in config.controls:
        hits = catalog.lookup(control.channel, control.event_type, control.control)
        assert any(h.controller == "DDJ-XP2" for h in hits), control


def test_known_ddj_xp2_pad_note():
    hits = catalog.lookup("10", "Note On", "64")
    names = [h.name for h in hits if h.controller == "DDJ-XP2"]
    assert names == ["Deck 2 Pad 1 (PAD MODE 5)"]


def test_ddj_xp2_deck_button():
    hits = catalog.lookup("1", "Note On", "20")
    assert any(h.name == "4 BEAT LOOP" for h in hits)


def test_ddj_xp2_double_click_second_note_resolves_pad_mode_5():
    hits = catalog.lookup("1", "Note On", "28")
    names = [h.name for h in hits if h.controller == "DDJ-XP2"]
    assert names == ["PAD MODE 5"]


def test_ddj_xp2_double_click_notes_resolve_pad_modes_6_to_8():
    expected = {"31": "PAD MODE 6", "33": "PAD MODE 7", "35": "PAD MODE 8"}
    for note, name in expected.items():
        hits = catalog.lookup("1", "Note On", note)
        assert any(h.controller == "DDJ-XP2" and h.name == name for h in hits)


def test_xdj_xz_pad_note():
    hits = catalog.lookup("6", "Note On", "0")
    names = [h.name for h in hits if h.controller == "XDJ-XZ"]
    assert names == ["Deck 1 Performance Pad 1 (HOT CUE mode)"]


def test_xdj_xz_pad_note_with_shift():
    hits = catalog.lookup("9", "Note On", "127")
    names = [h.name for h in hits if h.controller == "XDJ-XZ"]
    assert names == ["Deck 4 Performance Pad 8 (EXTENSION4 mode) +SHIFT"]


def test_xdj_xz_effect_select():
    hits = catalog.lookup("5", "Control Change", "59")
    assert any(h.name == "EFFECT SELECT: FILTER" for h in hits)


def test_ddj_1000_transport_control():
    hits = catalog.lookup("2", "Note On", "11")
    assert any(h.controller == "DDJ-1000" and h.name == "PLAY/PAUSE" for h in hits)


def test_ddj_1000_pad_grid():
    hits = catalog.lookup("9", "Note On", "31")
    names = [h.name for h in hits if h.controller == "DDJ-1000"]
    assert names == ["Deck 1 Pad 8 (PAD FX 1, PAGE 2) (+SHIFT)"]


def test_no_match_returns_empty_list():
    assert catalog.lookup("1", "Note On", "999999") == []
    assert catalog.lookup(None, "Note On", "20") == []
    assert catalog.lookup("1", None, "20") == []


def test_ddj_rev5_deck_transport():
    hits = catalog.lookup("3", "Note On", "11")
    assert any(h.controller == "DDJ-REV5" and h.name == "PLAY/PAUSE" for h in hits)


def test_ddj_rev5_pad_grid():
    hits = catalog.lookup("10", "Note On", "48")
    names = [h.name for h in hits if h.controller == "DDJ-REV5"]
    assert names == ["Deck 2 Pad 1 (SAMPLER MODE)"]


def test_ddj_rev5_pad_grid_with_shift():
    hits = catalog.lookup("15", "Note On", "119")
    names = [h.name for h in hits if h.controller == "DDJ-REV5"]
    assert names == ["Deck 4 Pad 8 (SCRATCH BANK MODE) (+SHIFT)"]


def test_ddj_rev5_ambiguous_user_mode_notes_are_excluded():
    """The 8 pad-mode banks each occupy a 16-note block but only use the
    first 8 (pad positions); the remaining 8 notes per block are the PDF's
    USER MODE (8/24/40/56) and D20-D23 stem-part (72/88/104/120) rows this
    controller's catalog deliberately leaves untranscribed (see
    ddj_rev5.py's module docstring)."""
    for note in ("8", "24", "40", "56", "72", "88", "104", "120"):
        hits = catalog.lookup("8", "Note On", note)
        assert not any(h.controller == "DDJ-REV5" for h in hits), note


def test_ddj_rev5_fx_and_browse_controls():
    fx_hits = catalog.lookup("5", "Note On", "112")
    assert any(h.controller == "DDJ-REV5" and h.name == "FX1-1" for h in fx_hits)

    beat_hits = catalog.lookup("6", "Note On", "6")
    assert any(h.controller == "DDJ-REV5" and h.name == "BEAT <" for h in beat_hits)

    browse_hits = catalog.lookup("7", "Note On", "65")
    assert any(h.controller == "DDJ-REV5" and h.name == "BROWSE" for h in browse_hits)


def test_ddj_rev5_headphones_cue_spans_all_deck_channels():
    for channel in ("1", "2", "3", "4"):
        hits = catalog.lookup(channel, "Note On", "7")
        assert any(h.controller == "DDJ-REV5" and h.name == "HEADPHONES CUE" for h in hits), channel


def test_ddj_rev5_bpm_transition_select_is_on_the_global_channel():
    """Issue #346: the PDF prints BPM TRANSITION SELECT (D9) on channel 7
    note 62 (status 0x96). Deck channels 1-4 note 62 are DECK1/3 / DECK2/4's
    deck-on/off indicator (D26) and must not resolve to it."""
    hits = catalog.lookup("7", "Note On", "62")
    assert [h.name for h in hits if h.controller == "DDJ-REV5"] == ["BPM TRANSITION SELECT"]
    for channel in ("1", "2", "3", "4"):
        hits = catalog.lookup(channel, "Note On", "62")
        assert not any(h.controller == "DDJ-REV5" for h in hits), channel


def test_ddj_rev5_static_entries_match_the_official_midi_message_list():
    """Every static entry, as printed in the bundled PDF's table (re-read
    from a 300 DPI render, issue #346): name -> (channels, Data1)."""
    from djmidi.catalog import ddj_rev5

    deck = ("1", "2", "3", "4")
    expected = {
        "PLAY/PAUSE": (deck, "11"),
        "CUE": (deck, "12"),
        "TEMPO RANGE": (deck, "8"),
        "KEY LOCK": (deck, "9"),
        "SYNC": (deck, "10"),
        "BPM TRANSITION SELECT": (("7",), "62"),
        "BPM TRANSITION START": (deck, "49"),
        "LOOP 1/2X": (deck, "1"),
        "LOOP 2X": (deck, "3"),
        "SLIP": (deck, "40"),
        "CENSOR": (deck, "41"),
        "KEY -": (deck, "42"),
        "KEY +": (deck, "43"),
        "STEMS": (deck, "37"),
        "HOT CUE": (deck, "38"),
        "SCRATCH BANK": (deck, "39"),
        "HOT CUE MODE": (deck, "64"),
        "ROLL MODE": (deck, "65"),
        "SAVED LOOP MODE": (deck, "66"),
        "SAMPLER MODE": (deck, "67"),
        "BROWSE": (("7",), "65"),
        "BACK": (("7",), "101"),
        "LOAD DECK 1": (("7",), "70"),
        "LOAD DECK 2": (("7",), "71"),
        "LOAD DECK 3": (("7",), "72"),
        "LOAD DECK 4": (("7",), "73"),
        "FX1-1": (("5",), "112"),
        "FX1-2": (("5",), "113"),
        "FX1-3": (("5",), "114"),
        "FX2-1": (("6",), "112"),
        "FX2-2": (("6",), "113"),
        "FX2-3": (("6",), "114"),
        "BEAT <": (("5", "6"), "6"),
        "BEAT >": (("5", "6"), "7"),
        "HEADPHONES CUE": (deck, "7"),
        "CROSSFADER REVERSE": (("7",), "84"),
        "SHIFT": (("7",), "63"),
    }
    actual = {e.name: (tuple(e.channels), e.data1) for e in ddj_rev5._STATIC}
    assert actual == expected
    assert all(e.note_or_cc == "NOTE" for e in ddj_rev5._STATIC)


def test_ddj_rev5_hot_cue_scratch_bank_and_load():
    """Issue #350: D24 HOT CUE / D25 SCRATCH BANK are plain deck-channel
    presses (notes 38/39); B3 LOAD is one channel-7 note per target deck."""
    for channel in ("1", "2", "3", "4"):
        assert [h.name for h in catalog.lookup(channel, "Note On", "38") if h.controller == "DDJ-REV5"] == ["HOT CUE"]
        assert [h.name for h in catalog.lookup(channel, "Note On", "39") if h.controller == "DDJ-REV5"] == [
            "SCRATCH BANK"
        ]
    for deck, note in zip(range(1, 5), ("70", "71", "72", "73")):
        hits = [h.name for h in catalog.lookup("7", "Note On", note) if h.controller == "DDJ-REV5"]
        assert hits == [f"LOAD DECK {deck}"]


def test_ddj_rev5_static_entries_have_no_duplicate_triggers():
    from djmidi.catalog import ddj_rev5

    seen: dict[tuple[str, str], str] = {}
    for entry in ddj_rev5._STATIC:
        for channel in entry.channels:
            key = (channel, entry.data1)
            assert key not in seen, f"{key} claimed by both {seen.get(key)!r} and {entry.name!r}"
            seen[key] = entry.name


def test_ddj_800_deck_transport():
    hits = catalog.lookup("3", "Note On", "11")
    assert any(h.controller == "DDJ-800" and h.name == "PLAY/PAUSE" for h in hits)


def test_ddj_800_pad_grid():
    hits = catalog.lookup("10", "Note On", "48")
    names = [h.name for h in hits if h.controller == "DDJ-800"]
    assert names == ["Deck 2 Pad 1 (SAMPLER PAGE 1)"]


def test_ddj_800_pad_grid_page_2():
    hits = catalog.lookup("8", "Note On", "56")
    names = [h.name for h in hits if h.controller == "DDJ-800"]
    assert names == ["Deck 1 Pad 1 (SAMPLER PAGE 2)"]


def test_ddj_800_pad_grid_with_shift():
    hits = catalog.lookup("15", "Note On", "126")
    names = [h.name for h in hits if h.controller == "DDJ-800"]
    assert names == ["Deck 4 Pad 7 (KEY SHIFT PAGE 2) (+SHIFT)"]


def test_ddj_800_pad_grid_covers_the_full_note_range_with_no_gaps():
    """The pad grid's 8-mode x 16-note-per-mode layout exactly covers the
    full 0-127 Data1 range with no gaps, unlike DDJ-REV5's grid (which
    only uses the first half of each 16-note block)."""
    hits = catalog.lookup("8", "Note On", "127")
    names = [h.name for h in hits if h.controller == "DDJ-800"]
    assert names == ["Deck 1 Pad 8 (KEY SHIFT PAGE 2)"]
    # A channel this controller doesn't use for pads at all resolves to no
    # DDJ-800 hit (a hit from another controller sharing that channel/note
    # is fine and expected -- MIDI channels are shared across controllers).
    hits = catalog.lookup("16", "Note On", "0")
    assert not any(h.controller == "DDJ-800" for h in hits)


def test_ddj_800_effect_and_browse_controls():
    fx_hits = catalog.lookup("5", "Note On", "74")
    assert any(h.controller == "DDJ-800" and h.name == "BEAT <" for h in fx_hits)

    color_fx_hits = catalog.lookup("7", "Note On", "0")
    assert any(h.controller == "DDJ-800" and h.name == "COLOR FX D-ECHO" for h in color_fx_hits)

    browse_hits = catalog.lookup("7", "Note On", "65")
    assert any(h.controller == "DDJ-800" and h.name == "BROWSE" for h in browse_hits)


def test_ddj_800_view_is_the_plain_press_not_the_long_press():
    # The PDF's B4 rows: press = note 122, LONG press = 103, +SHIFT = 104.
    assert any(h.controller == "DDJ-800" and h.name == "VIEW" for h in catalog.lookup("7", "Note On", "122"))
    assert not any(h.controller == "DDJ-800" for h in catalog.lookup("7", "Note On", "103"))


def test_ddj_800_headphones_cue_spans_all_deck_channels():
    for channel in ("1", "2", "3", "4"):
        hits = catalog.lookup(channel, "Note On", "84")
        assert any(h.controller == "DDJ-800" and h.name == "HEADPHONES CUE" for h in hits), channel


def test_ddj_800_line_phono_switch_limited_to_two_channels():
    for channel in ("1", "2"):
        hits = catalog.lookup(channel, "Note On", "70")
        assert any(h.controller == "DDJ-800" and h.name == "LINE/PHONO SW" for h in hits), channel
    for channel in ("3", "4"):
        hits = catalog.lookup(channel, "Note On", "70")
        assert not any(h.controller == "DDJ-800" for h in hits), channel


def test_ddj_800_static_entries_have_no_duplicate_triggers():
    from djmidi.catalog import ddj_800

    seen: dict[tuple[str, str], str] = {}
    for entry in ddj_800._STATIC:
        for channel in entry.channels:
            key = (channel, entry.data1)
            assert key not in seen, f"{key} claimed by both {seen.get(key)!r} and {entry.name!r}"
            seen[key] = entry.name
