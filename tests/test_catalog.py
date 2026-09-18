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
    ambiguous "USER MODE" rows this controller's catalog deliberately
    leaves untranscribed (see ddj_rev5.py's module docstring)."""
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


def test_ddj_rev5_static_entries_have_no_duplicate_triggers():
    from djmidi.catalog import ddj_rev5

    seen: dict[tuple[str, str], str] = {}
    for entry in ddj_rev5._STATIC:
        for channel in entry.channels:
            key = (channel, entry.data1)
            assert key not in seen, f"{key} claimed by both {seen.get(key)!r} and {entry.name!r}"
            seen[key] = entry.name
