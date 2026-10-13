"""Hercules DJControl Inpulse 500 catalog module, checked against the
official "MIDI COMMANDS" sheet bundled under ``controllers/`` (issue #247).

The (channel, note) values below are copied from that sheet's rows (status
byte -> 1-based channel), not derived from the module's own formula."""

import pytest

from djmidi import catalog, pad_colours
from djmidi.catalog import hercules_inpulse_500 as inpulse
from djmidi.gui import layout, pad_mode

CONTROLLER = "Hercules DJControl Inpulse 500"


def _hits(channel: str, data1: int) -> list[catalog.ControlInfo]:
    return [h for h in catalog.lookup(channel, "Note On", str(data1)) if h.controller == CONTROLLER]


def _names(channel: str, data1: int) -> list[str]:
    return [h.name for h in _hits(channel, data1)]


@pytest.mark.parametrize(
    ("channel", "note", "name"),
    [
        ("2", 0x07, "PLAY/PAUSE"),  # D1-1, 91 07
        ("5", 0x07, "PLAY/PAUSE (+SHIFT)"),  # 94 07
        ("3", 0x07, "PLAY/PAUSE"),  # D2-1, 92 07
        ("6", 0x07, "PLAY/PAUSE (+SHIFT)"),  # 95 07
        ("2", 0x06, "CUE"),  # D1-2, 91 06
        ("2", 0x04, "SHIFT"),  # D1-3, 91 04
        ("2", 0x09, "LOOP IN"),  # D1-4, 91 09
        ("2", 0x0B, "LOOP IN (long press)"),  # 91 0B
        ("3", 0x0A, "LOOP OUT"),  # D2-5, 92 0A
        ("6", 0x0A, "LOOP OUT (+SHIFT)"),  # 95 0A
        ("2", 0x2C, "AUTOLOOP (press)"),  # D1-6 push, 91 2C
        ("2", 0x05, "SYNC"),  # D1-10, 91 05
        ("3", 0x03, "VINYL"),  # D2-17, 92 03
        ("2", 0x01, "SLIP"),  # D1-18, 91 01
        ("2", 0x02, "QUANTIZE"),  # D1-19, 91 02
        ("2", 0x0F, "PAD MODE 1"),  # P1-1, 91 0F
        ("2", 0x13, "PAD MODE 5"),  # P1-1 +Shift, 91 13
        ("3", 0x16, "PAD MODE 8"),  # P2-4, 92 16
        ("2", 0x40, "PAD MODE 1 (long press)"),  # P1-1 Mode 1A, 91 40
        ("2", 0x0C, "DECK 1 PFL"),  # M-5, 91 0C
        ("6", 0x0C, "DECK 2 PFL (+SHIFT)"),  # M-7, 95 0C
        ("1", 0x02, "MASTER PFL"),  # M-30, 90 02
        ("1", 0x18, "XFADER CURVE ON/OFF"),  # M-2, 90 18
        ("1", 0x14, "FX 1"),  # M-10, 90 14
        ("4", 0x17, "FX 4 (+SHIFT)"),  # M-13, 93 17
        ("1", 0x00, "BROWSE (press)"),  # B3 push, 90 00
        ("2", 0x0D, "LOAD DECK 1"),  # B1, 91 0D
        ("3", 0x0E, "LOAD DECK 2 (long press)"),  # B2, 92 0E
    ],
)
def test_static_entries_match_the_sheet(channel, note, name):
    assert _names(channel, note) == [name]


@pytest.mark.parametrize(
    ("channel", "note", "name"),
    [
        ("7", 0x00, "Deck 1 Pad 1 (PAD MODE 1)"),  # P1-5, 96 00
        ("7", 0x0F, "Deck 1 Pad 8 (PAD MODE 1) +SHIFT"),  # 96 0F
        ("7", 0x18, "Deck 1 Pad 1 (PAD MODE 2) +SHIFT"),  # 96 18
        ("7", 0x52, "Deck 1 Pad 3 (PAD MODE 6)"),  # 96 52
        ("7", 0x7F, "Deck 1 Pad 8 (PAD MODE 8) +SHIFT"),  # 96 7F
        ("8", 0x03, "Deck 2 Pad 4 (PAD MODE 1)"),  # P2-8, 97 03
        ("8", 0x6F, "Deck 2 Pad 8 (PAD MODE 7) +SHIFT"),  # 97 6F
        ("8", 0x77, "Deck 2 Pad 8 (PAD MODE 8)"),  # 97 77
    ],
)
def test_pads_match_the_sheet(channel, note, name):
    assert _names(channel, note) == [name]


def test_every_pad_note_of_both_decks_resolves_once():
    for channel in ("7", "8"):
        assert all(len(_hits(channel, note)) == 1 for note in range(128))


def test_old_community_values_are_gone():
    # The former profile's pads (channels 1/2, notes 40-47) and BEATJUMP
    # (note 13) aren't on the sheet.
    assert not any(h.name.startswith("Deck") for note in range(40, 48) for h in _hits("1", note) + _hits("2", note))
    assert not any("BEATJUMP" in h.name for h in catalog.static_entries(CONTROLLER))


def test_self_contradictory_sheet_rows_are_left_out():
    # Guides (M-6) and Assistant (B4) are both printed as 90 01.
    assert _hits("1", 1) == []
    # Deck 2 "Mode 4A" says channel 2 but status 91; "Load 2" +Shift says channel 4 but 95.
    assert _hits("3", 67) == []
    assert _hits("6", 13) == []


def test_no_two_static_entries_share_a_trigger():
    triggers = [
        (channel, entry.data1) for entry in catalog.static_entries(CONTROLLER) for channel in entry.channels
    ]
    assert len(triggers) == len(set(triggers))


def test_pad_trigger_rejects_unknown_pads():
    with pytest.raises(ValueError):
        inpulse.pad_trigger(3, 1)
    with pytest.raises(ValueError):
        inpulse.pad_trigger(1, 9)
    with pytest.raises(ValueError):
        inpulse.pad_trigger(1, 1, mode=9)


def test_pad_colour_addresses_resolve_to_the_same_catalog_pad():
    palette = pad_colours.palette_for(CONTROLLER)
    assert palette is not None
    for slot in palette.slots():
        channel, note = palette.led_address(slot)
        suffix = " +SHIFT" if slot.shift else ""
        assert _names(str(channel), note) == [f"Deck {slot.deck} Pad {slot.pad} (PAD MODE {slot.mode}){suffix}"]


def test_emulator_pad_click_resolves_to_the_selected_mode_bank():
    variants = layout.reverse_lookup(CONTROLLER)[(CONTROLLER, "PAD", "Pad 3")]
    default = layout.pick_default_variant(variants)
    assert (default.channels, default.data1) == (("7",), "2")
    token = pad_mode.mode_token_for_button(CONTROLLER, "PAD MODE 6")
    chosen = layout.pick_default_variant(variants, prefer_token=token)
    assert (chosen.channels, chosen.data1) == (("7",), str(0x52))
    shifted = layout.pick_default_variant(variants, prefer_token=token, prefer_shift=True)
    assert shifted.data1 == str(0x5A)
