"""DDJ-FLX10 controller definition, transcribed from Pioneer's official MIDI
Message List PDF (docs/controllers/ddj-flx10-midi-message-list-e1.pdf).

The DDJ-FLX10 uses one MIDI channel per deck and eight additional channels
(four decks x on/+SHIFT) for the performance-pad bank. This catalog
deliberately covers the discrete transport/loop controls and the 8-pad grid;
continuous controls are kept out of catalogs, as they cannot be represented
by one useful trigger.

Corrected from a first pass that simply duplicated DDJ-1000's (also wrong)
placeholder sequential values (0-13) instead of the PDF's real Data1
numbers, and omitted most of DDJ-FLX10's real DECK controls entirely.
DDJ-FLX10 shares DDJ-1000's PLAY/PAUSE, CUE, LOOP IN/OUT, QUANTIZE, SLIP
(SLIP REVERSE), and 4-BEAT-LOOP/EXIT-style buttons, but is a materially
different, richer controller -- it has no separate MASTER TEMPO or KEYLOCK
button at all (its closest equivalent, TEMPO RESET, is a different function
with its own Data1 value), and adds controls DDJ-1000 doesn't have at all:
ACTIVE PART DRUMS/VOCAL/INST (rekordbox stem control), CUE/LOOP CALL <</>>,
MIX POINT SELECT <</>> and MIX POINT LINK, and 4 BEAT JUMP <</>>. Every
value below was re-verified against the PDF at 300 DPI, not carried over
from DDJ-1000's catalog.

The 8-pad grid's channel-to-deck map and 16-real-pad-mode-bank note formula
(HOT CUE, PAD FX 1, BEAT JUMP, SAMPLER, KEYBOARD, PAD FX 2, BEAT LOOP, KEY
SHIFT x 2 pages each, one 8-note block per bank) are identical to
DDJ-1000's -- verified independently against DDJ-FLX10's own PDF (PAD group,
page 4), not assumed from the shared design.
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
# message list (page 2-3, DECK group). Excludes continuous controls (JOG,
# TEMPO fader) and DECK SELECT (switches which deck a channel controls,
# not a per-deck function).
_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-FLX10", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-FLX10", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-FLX10", "DECK", "BEAT SYNC", "NOTE", _DECK_CHANNELS, "88"),
    ControlInfo("DDJ-FLX10", "DECK", "TEMPO RESET", "NOTE", _DECK_CHANNELS, "65"),
    ControlInfo("DDJ-FLX10", "DECK", "KEY SYNC", "NOTE", _DECK_CHANNELS, "101"),
    ControlInfo("DDJ-FLX10", "DECK", "ACTIVE PART DRUMS", "NOTE", _DECK_CHANNELS, "13"),
    ControlInfo("DDJ-FLX10", "DECK", "ACTIVE PART VOCAL", "NOTE", _DECK_CHANNELS, "14"),
    ControlInfo("DDJ-FLX10", "DECK", "ACTIVE PART INST", "NOTE", _DECK_CHANNELS, "15"),
    ControlInfo("DDJ-FLX10", "DECK", "CUE/LOOP CALL <", "NOTE", _DECK_CHANNELS, "81"),
    ControlInfo("DDJ-FLX10", "DECK", "CUE/LOOP CALL >", "NOTE", _DECK_CHANNELS, "83"),
    ControlInfo("DDJ-FLX10", "DECK", "LOOP IN / 1/2X", "NOTE", _DECK_CHANNELS, "16"),
    ControlInfo("DDJ-FLX10", "DECK", "LOOP OUT / 2X", "NOTE", _DECK_CHANNELS, "17"),
    ControlInfo("DDJ-FLX10", "DECK", "4 BEAT/EXIT", "NOTE", _DECK_CHANNELS, "20"),
    ControlInfo("DDJ-FLX10", "DECK", "MIX POINT SELECT <", "NOTE", _DECK_CHANNELS, "89"),
    ControlInfo("DDJ-FLX10", "DECK", "MIX POINT SELECT >", "NOTE", _DECK_CHANNELS, "90"),
    ControlInfo("DDJ-FLX10", "DECK", "MIX POINT LINK", "NOTE", _DECK_CHANNELS, "74"),
    ControlInfo("DDJ-FLX10", "DECK", "SLIP REVERSE", "NOTE", _DECK_CHANNELS, "21"),
    ControlInfo("DDJ-FLX10", "DECK", "QUANTIZE", "NOTE", _DECK_CHANNELS, "53"),
    ControlInfo("DDJ-FLX10", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "64"),
    ControlInfo("DDJ-FLX10", "DECK", "4 BEAT JUMP <", "NOTE", _DECK_CHANNELS, "94"),
    ControlInfo("DDJ-FLX10", "DECK", "4 BEAT JUMP >", "NOTE", _DECK_CHANNELS, "95"),
    ControlInfo("DDJ-FLX10", "DECK", "SHIFT", "NOTE", _DECK_CHANNELS, "63"),
]

# The 8-pad grid has 16 real pad-mode banks (8 named modes x 2 pages each),
# each occupying its own 8-note block -- verified against DDJ-FLX10's own
# PDF (PAD group), independently of DDJ-1000's identical layout.
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
    """Resolve the DDJ-FLX10's 8-pad grid across its 16 real pad-mode banks."""
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
        "DDJ-FLX10",
        "PAD",
        f"Deck {deck} Pad {pad + 1} ({_PAD_MODE_NAMES[mode]}){suffix}",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-FLX10",
        plugin_id="pioneer.ddj-flx10",
        manufacturer="Pioneer DJ",
        supported_software=("rekordbox", "serato"),
        reference_image="ddj-flx10.png",
        display_order=35,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "PAD"),
    )
)
