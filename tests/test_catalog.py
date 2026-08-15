from pathlib import Path

from seratomidiconf import catalog
from seratomidiconf.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def test_every_control_in_sample_file_resolves_via_ddj_xp2_pad_grid():
    config = parse_file(FIXTURE)
    for control in config.controls:
        hits = catalog.lookup(control.channel, control.event_type, control.control)
        assert any(h.controller == "DDJ-XP2" for h in hits), control


def test_known_ddj_xp2_pad_note():
    hits = catalog.lookup("10", "Note On", "64")
    names = [h.name for h in hits if h.controller == "DDJ-XP2"]
    assert names == ["Deck 2 Pad 13 (PAD MODE 5)"]


def test_ddj_xp2_deck_button():
    hits = catalog.lookup("1", "Note On", "20")
    assert any(h.name == "4 BEAT LOOP" for h in hits)


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
    hits = catalog.lookup("2", "Note On", "0")
    assert any(h.controller == "DDJ-1000" and h.name == "PLAY/PAUSE" for h in hits)


def test_ddj_1000_pad_grid():
    hits = catalog.lookup("9", "Note On", "31")
    names = [h.name for h in hits if h.controller == "DDJ-1000"]
    assert names == ["Deck 4 Pad 16 (PAD MODE 2)"]


def test_no_match_returns_empty_list():
    assert catalog.lookup("1", "Note On", "999999") == []
    assert catalog.lookup(None, "Note On", "20") == []
    assert catalog.lookup("1", None, "20") == []
