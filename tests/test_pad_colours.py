from pathlib import Path

import pytest

from djmidi import pad_colours
from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.pad_colours import PadSlot

INPULSE = "Hercules DJControl Inpulse 500"
CONTROLLERS_DIR = Path(__file__).parent.parent / "controllers"


def _palette():
    palette = pad_colours.palette_for(INPULSE)
    assert palette is not None
    return palette


def test_only_documented_controllers_have_a_palette():
    assert pad_colours.palette_controllers() == [INPULSE]
    assert pad_colours.palette_for("DDJ-XP2") is None
    assert (CONTROLLERS_DIR / _palette().source).is_file()


def test_inpulse_palette_matches_the_documented_table():
    # Page 5 of the bundled Hercules sheet, "COLOR PER DATA2 VALUE ON PAD MIDI OUT".
    assert {colour.name: colour.velocity for colour in _palette().colours} == {
        "No light": 0x00, "Blue low": 0x02, "Blue": 0x03, "Green low": 0x10, "Cyan low": 0x12,
        "Green": 0x1C, "Cyan": 0x1F, "Lime low": 0x30, "Red low": 0x40, "Fuchsia low": 0x42,
        "Orange low": 0x4C, "Yellow low": 0x50, "White low": 0x52, "Lime": 0x5C, "Red": 0x60,
        "Fuchsia": 0x63, "Orange": 0x74, "Yellow": 0x7C, "White": 0x7F,
    }


@pytest.mark.parametrize(
    ("slot", "channel", "note"),
    [
        (PadSlot(1, 1), 7, 0x00),  # 96 00
        (PadSlot(1, 8, shift=True), 7, 0x0F),  # 96 0F
        (PadSlot(1, 3, mode=5, shift=True), 7, 0x4A),  # 96 4A
        (PadSlot(1, 1, mode=6), 7, 0x50),  # 96 50
        (PadSlot(1, 8, mode=8, shift=True), 7, 0x7F),  # 96 7F
        (PadSlot(2, 5, mode=1), 8, 0x04),  # 97 04
    ],
)
def test_inpulse_led_note_matches_the_documented_pad_table(slot, channel, note):
    message = _palette().message_for(slot, _palette().colour_named("Red"))
    assert message == SyncMessage("Note On", channel, note, 0x60)
    assert _palette().slot_for_message(message) == slot


def test_every_inpulse_pad_has_its_own_led_note():
    palette = _palette()
    addresses = [palette.led_address(slot) for slot in palette.slots()]
    assert len(addresses) == len(set(addresses)) == 2 * 8 * 8 * 2


def test_message_for_rejects_an_unknown_pad_or_colour():
    palette = _palette()
    with pytest.raises(ValueError):
        palette.message_for(PadSlot(3, 1), palette.colours[0])
    with pytest.raises(ValueError):
        palette.message_for(PadSlot(1, 1), pad_colours.PadColour("Teal", 0x20, "#008080"))


def test_pad_number_reads_layout_and_catalog_labels():
    assert pad_colours.pad_number("Pad 3") == 3
    assert pad_colours.pad_number("Deck 2 Pad 8 (R)") == 8
    assert pad_colours.pad_number("PLAY/PAUSE") is None


def test_merge_into_a_new_sync_set():
    palette = _palette()
    red, blue = palette.colour_named("Red"), palette.colour_named("Blue")
    sync_set = pad_colours.merge_into_sync_set(
        palette, None, {PadSlot(1, 2): blue, PadSlot(1, 1): red}, scene="Tek"
    )
    assert sync_set.controller == INPULSE
    assert sync_set.scene == "Tek"
    # Appended in pad (channel, note) order.
    assert sync_set.messages == (SyncMessage("Note On", 7, 0, 0x60), SyncMessage("Note On", 7, 1, 0x03))


def test_merge_replaces_a_pads_colour_and_keeps_other_messages():
    palette = _palette()
    unrelated = SyncMessage("Control Change", 1, 14, 64)
    other_note = SyncMessage("Note On", 2, 7, 127)
    existing = ControllerSyncSet(
        INPULSE, "Inpulse 500", (unrelated, SyncMessage("Note On", 7, 0, 0x60), other_note), "Tek"
    )
    merged = pad_colours.merge_into_sync_set(
        palette, existing, {PadSlot(1, 1): palette.colour_named("Green"), PadSlot(2, 1): palette.colour_named("White")}
    )
    assert merged.output_port == "Inpulse 500"
    assert merged.scene == "Tek"
    assert merged.messages == (
        unrelated,
        SyncMessage("Note On", 7, 0, 0x1C),  # replaced in place
        other_note,
        SyncMessage("Note On", 8, 0, 0x7F),
    )


def test_colours_round_trip_through_sync_messages():
    palette = _palette()
    colours = {PadSlot(1, 4, mode=2): palette.colour_named("Orange"), PadSlot(2, 7, shift=True): palette.colour_named("Cyan")}
    sync_set = pad_colours.merge_into_sync_set(palette, None, colours)
    noise = [SyncMessage("Note On", 7, 3, 0x21), SyncMessage("Control Change", 7, 0, 0x60)]
    assert pad_colours.colours_from_messages(palette, [*sync_set.messages, *noise]) == colours
