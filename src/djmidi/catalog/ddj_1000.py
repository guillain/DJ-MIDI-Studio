"""DDJ-1000 controller definition, transcribed from Pioneer's official MIDI
Message List PDF (docs/controllers/ddj-1000-midi-message-list-e1.pdf).

The DDJ-1000 uses one MIDI channel per deck and eight additional channels
(four decks x on/+SHIFT) for the performance-pad bank. This catalog
deliberately covers the discrete transport/loop controls and the 8-pad grid;
continuous controls are kept out of catalogs, as they cannot be represented
by one useful trigger.

Corrected from a first pass that used placeholder sequential values (0-13)
instead of the PDF's real Data1 numbers, and mixed up several UI names with
adjacent-but-different real controls (see git history for the original).
Every value below was re-verified against the PDF at 300 DPI.
"""

from __future__ import annotations

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    _parse_midi_note,
    register,
)

_DECK_CHANNELS = ("1", "2", "3", "4")
# channel -> (deck, is_shifted). The pad grid's +SHIFT state is carried
# entirely by which channel a pad hit arrives on (channels 9/11/13/15),
# not by a different NOTE range -- the same Data1 value means the same pad
# and mode on both the plain and +SHIFT channel for a given deck.
_PAD_CHANNELS = {
    "8": (1, False),
    "9": (1, True),
    "10": (2, False),
    "11": (2, True),
    "12": (3, False),
    "13": (3, True),
    "14": (4, False),
    "15": (4, True),
}

# Discrete controls shared by each of the four deck channels. Data1 values
# are the "MIDI Data (Data1) (Dec)" column from Pioneer's official MIDI
# message list (page 2, DECK group).
_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-1000", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-1000", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-1000", "DECK", "MASTER TEMPO", "NOTE", _DECK_CHANNELS, "26"),
    ControlInfo("DDJ-1000", "DECK", "BEAT SYNC", "NOTE", _DECK_CHANNELS, "88"),
    ControlInfo("DDJ-1000", "DECK", "KEY SYNC", "NOTE", _DECK_CHANNELS, "101"),
    ControlInfo("DDJ-1000", "DECK", "KEY RESET", "NOTE", _DECK_CHANNELS, "100"),
    ControlInfo("DDJ-1000", "DECK", "LOOP IN", "NOTE", _DECK_CHANNELS, "16"),
    ControlInfo("DDJ-1000", "DECK", "LOOP OUT", "NOTE", _DECK_CHANNELS, "17"),
    ControlInfo("DDJ-1000", "DECK", "4 BEAT LOOP/EXIT", "NOTE", _DECK_CHANNELS, "20"),
    ControlInfo("DDJ-1000", "DECK", "QUANTIZE", "NOTE", _DECK_CHANNELS, "53"),
    ControlInfo("DDJ-1000", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "64"),
    ControlInfo("DDJ-1000", "DECK", "SLIP REVERSE", "NOTE", _DECK_CHANNELS, "21"),
]

# The 8-pad grid has 16 real pad-mode banks (8 named modes x 2 pages each),
# each occupying its own 8-note block -- not 8 modes x 16 notes as a first
# pass assumed. Order and names are the PAD group's "UI name" column.
_PAD_MODE_NAMES = (
    "HOT CUE, PAGE 1",
    "HOT CUE, PAGE 2",
    "PAD FX 1, PAGE 1",
    "PAD FX 1, PAGE 2",
    "BEAT JUMP, PAGE 1",
    "BEAT JUMP, PAGE 2",
    "SAMPLER, PAGE 1",
    "SAMPLER, PAGE 2",
    "KEYBOARD, PAGE 1",
    "KEYBOARD, PAGE 2",
    "PAD FX 2, PAGE 1",
    "PAD FX 2, PAGE 2",
    "BEAT LOOP, PAGE 1",
    "BEAT LOOP, PAGE 2",
    "KEY SHIFT, PAGE 1",
    "KEY SHIFT, PAGE 2",
)


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    """Resolve the DDJ-1000's 8-pad grid across its 16 real pad-mode banks."""
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode, pad = divmod(note, 8)
    if mode >= len(_PAD_MODE_NAMES):
        return None
    deck, shifted = _PAD_CHANNELS[channel]
    suffix = " (+SHIFT)" if shifted else ""
    return ControlInfo(
        "DDJ-1000",
        "PAD",
        f"Deck {deck} Pad {pad + 1} ({_PAD_MODE_NAMES[mode]}){suffix}",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-1000",
        plugin_id="pioneer.ddj-1000",
        manufacturer="Pioneer DJ",
        supported_software=("serato",),
        reference_image="ddj-1000.png",
        display_order=30,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "PAD"),
    )
)
