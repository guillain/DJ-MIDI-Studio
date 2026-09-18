"""DDJ-REV5 controller definition, transcribed from Pioneer's official MIDI
Message List PDF (controllers/ddj-rev5/ddj-rev5-midi-message-list-e1.pdf).

The DDJ-REV5 is a 4-deck flagship controller: one MIDI channel per deck
(1-4) for DECK-section controls, a shared channel 7 for BROWSE/EFFECT/
MIXER-global controls, channels 5/6 for the two FX units, and eight
additional channels (four decks x on/+SHIFT) for the performance-pad bank
-- the same deck/pad-channel shape as DDJ-1000/DDJ-FLX10.

Deliberately conservative, matching those two catalogs' precedent of never
modeling a "+SHIFT <control>" as a separate entry (SHIFT-modified DECK
triggers are real per the PDF, but every DDJ-1000/DDJ-FLX10 entry already
established that convention; this module follows it rather than introduce
one controller's catalog with a different shape). Also excluded, each for
its own reason rather than fabricated:

- AUTO LOOP (D11): the PDF's own Data1/Data2 columns disagree between its
  input and MIDI-OUT rows (Data1 0x05 in, 0x04 out) in a way that doesn't
  resolve cleanly to one trigger value from the extracted text alone.
- STEMS SOLO (D19) and BPM TRANSITION BAR (D8): "Indicate"-only rows (LED
  output, no press input), same category DDJ-XP2's MIDI-OUT section
  excludes.
- The STEMS +VOCAL/+MELODY/+BASS/+DRUMS sub-triggers (D18's condition
  rows) and the "VOCAL/PAD1".."DRUMS/PAD4" block (D20-D23): these land on
  the pad channels at Data1 values (72-75, 88-91, 104-107, 120-123) that
  don't fit the 8-mode x 16-note pad-grid formula below (verified: 72
  falls mid-way through the PITCH PLAY MODE block, not a valid pad
  position), and the PDF's own figure numbering keeps them ambiguous
  without the physical device or diagram to resolve against.
- DECK1/3 and DECK2/4 (D26, deck-pair select) and LOAD (B3): both send a
  multi-message sequence (switch one deck off, another on) rather than one
  simple press trigger -- DDJ-1000/DDJ-FLX10 already exclude the
  equivalent "DECK SELECT" function for the same reason, and neither
  models LOAD at all (its per-deck Data1 values are also not unambiguously
  orderable from the extracted PDF table).
- MIC OFF/ON/TALKOVER (M15), AUX LINE/PORTABLE (M24), INPUT SELECT (M1):
  each a 2/3-position slide switch sending a *pair* of NOTE messages per
  position (one going high, a sibling going low) -- not one clean trigger
  per catalog's single-trigger-per-name model.

Field-verification against real hardware is still open, same status as
every other PDF-transcribed profile in this catalog (issue #11).
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
_FX_CHANNELS = ("5", "6")

# Discrete DECK-section controls shared by each of the four deck channels.
# Data1 values are the "MIDI Data (Data1) (Dec)" column, DECK group.
_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-REV5", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-REV5", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-REV5", "DECK", "TEMPO RANGE", "NOTE", _DECK_CHANNELS, "8"),
    ControlInfo("DDJ-REV5", "DECK", "KEY LOCK", "NOTE", _DECK_CHANNELS, "9"),
    ControlInfo("DDJ-REV5", "DECK", "SYNC", "NOTE", _DECK_CHANNELS, "10"),
    ControlInfo("DDJ-REV5", "DECK", "BPM TRANSITION SELECT", "NOTE", _DECK_CHANNELS, "62"),
    ControlInfo("DDJ-REV5", "DECK", "BPM TRANSITION START", "NOTE", _DECK_CHANNELS, "49"),
    ControlInfo("DDJ-REV5", "DECK", "LOOP 1/2X", "NOTE", _DECK_CHANNELS, "1"),
    ControlInfo("DDJ-REV5", "DECK", "LOOP 2X", "NOTE", _DECK_CHANNELS, "3"),
    ControlInfo("DDJ-REV5", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "40"),
    ControlInfo("DDJ-REV5", "DECK", "CENSOR", "NOTE", _DECK_CHANNELS, "41"),
    ControlInfo("DDJ-REV5", "DECK", "KEY -", "NOTE", _DECK_CHANNELS, "42"),
    ControlInfo("DDJ-REV5", "DECK", "KEY +", "NOTE", _DECK_CHANNELS, "43"),
    ControlInfo("DDJ-REV5", "DECK", "STEMS", "NOTE", _DECK_CHANNELS, "37"),
    # Pad-mode select buttons (P1-P4 in the PDF): press only, switching
    # which of the pad grid's 8 banks below is active. +SHIFT gives PITCH
    # PLAY/PIANO PLAY/STEMS/SCRATCH BANK MODE respectively, excluded per
    # this module's no-"+SHIFT"-entries convention above.
    ControlInfo("DDJ-REV5", "DECK", "HOT CUE MODE", "NOTE", _DECK_CHANNELS, "64"),
    ControlInfo("DDJ-REV5", "DECK", "ROLL MODE", "NOTE", _DECK_CHANNELS, "65"),
    ControlInfo("DDJ-REV5", "DECK", "SAVED LOOP MODE", "NOTE", _DECK_CHANNELS, "66"),
    ControlInfo("DDJ-REV5", "DECK", "SAMPLER MODE", "NOTE", _DECK_CHANNELS, "67"),
    # BROWSE group, channel 7 (the shared BROWSER/Global Section channel).
    ControlInfo("DDJ-REV5", "BROWSE", "BROWSE", "NOTE", ("7",), "65"),
    ControlInfo("DDJ-REV5", "BROWSE", "BACK", "NOTE", ("7",), "101"),
    # EFFECT group: FX1 on channel 5, FX2 on channel 6 (same Data1 values).
    ControlInfo("DDJ-REV5", "EFFECT", "FX1-1", "NOTE", ("5",), "112"),
    ControlInfo("DDJ-REV5", "EFFECT", "FX1-2", "NOTE", ("5",), "113"),
    ControlInfo("DDJ-REV5", "EFFECT", "FX1-3", "NOTE", ("5",), "114"),
    ControlInfo("DDJ-REV5", "EFFECT", "FX2-1", "NOTE", ("6",), "112"),
    ControlInfo("DDJ-REV5", "EFFECT", "FX2-2", "NOTE", ("6",), "113"),
    ControlInfo("DDJ-REV5", "EFFECT", "FX2-3", "NOTE", ("6",), "114"),
    # BEAT </> (E7/E8): same Data1 on both FX1 (ch5) and FX2 (ch6) channels.
    ControlInfo("DDJ-REV5", "EFFECT", "BEAT <", "NOTE", _FX_CHANNELS, "6"),
    ControlInfo("DDJ-REV5", "EFFECT", "BEAT >", "NOTE", _FX_CHANNELS, "7"),
    # MIXER group. HEADPHONES CUE (M11+M12) is one physical button per deck
    # channel strip, same _DECK_CHANNELS shape as DECK-section controls.
    ControlInfo("DDJ-REV5", "MIXER", "HEADPHONES CUE", "NOTE", _DECK_CHANNELS, "7"),
    ControlInfo("DDJ-REV5", "MIXER", "CROSSFADER REVERSE", "NOTE", ("7",), "84"),
    ControlInfo("DDJ-REV5", "MIXER", "SHIFT", "NOTE", ("7",), "63"),
]

# The 8-pad grid has 8 named modes x 16 notes each, covering the full
# 0-127 Data1 range with no gaps -- verified directly against the PDF's
# PERFORMANCE PADS group (P5-P8 rows), not assumed from another
# controller's layout. Order matches the PDF's own row order.
_PAD_MODE_NAMES = (
    "HOT CUE MODE",
    "ROLL MODE",
    "SAVED LOOP MODE",
    "SAMPLER MODE",
    "PITCH PLAY MODE",
    "PIANO PLAY MODE",
    "STEMS MODE",
    "SCRATCH BANK MODE",
)

# channel -> (deck, is_shifted). Same convention as DDJ-1000/DDJ-FLX10: the
# pad grid's +SHIFT state is carried entirely by which channel a pad hit
# arrives on, not by a different NOTE range.
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


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    """Resolve the DDJ-REV5's 8-pad grid across its 8 real pad-mode banks."""
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode, pad = divmod(note, 16)
    if mode >= len(_PAD_MODE_NAMES) or pad >= 8:
        return None
    deck, shifted = _PAD_CHANNELS[channel]
    suffix = " (+SHIFT)" if shifted else ""
    return ControlInfo(
        "DDJ-REV5",
        "PAD",
        f"Deck {deck} Pad {pad + 1} ({_PAD_MODE_NAMES[mode]}){suffix}",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-REV5",
        plugin_id="pioneer.ddj-rev5",
        manufacturer="Pioneer DJ",
        supported_software=("serato",),
        reference_image="ddj-rev5/reference.png",
        display_order=60,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "BROWSE", "EFFECT", "MIXER", "PAD"),
    )
)
