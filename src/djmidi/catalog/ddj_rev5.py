"""DDJ-REV5 controller definition, transcribed from Pioneer's official MIDI
Message List PDF (controllers/hardware/pioneer/DDJ-REV5/ddj-rev5-midi-message-list-e1.pdf).

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
  rows, channel 7 notes 32-47, one note per deck) and the "VOCAL/PAD 1"..
  "DRUMS/PAD 4" part buttons (D20-D23): the latter land on the pad
  channels at Data1 values (72-75, 88-91, 104-107, 120-123) whose printed
  "mode" conditions (HOT CUE/SAVED LOOP/SCRATCH BANK/SAMPLER) don't match
  the pad-grid bank those notes fall in, plus deck channels 1-4 notes
  44-47 in STEMS MODE -- left out rather than guessed.
- Every "+SHIFT" row, as above -- and the PDF contradicts itself there
  anyway: BPM TRANSITION SELECT +SHIFT and FX1-1 +SHIFT both print
  channel 7 note 48. The pad grid's USER MODE rows (pad-mode button
  pressed twice) use notes 8-15/24-31/40-47/56-63, the second half of the
  first four banks, which this catalog's 8-pad lookup leaves unnamed.
- The table prints SHIFT under Fig. "M12", a typo for E12 (the figure's
  callout and the button's own label both say SHIFT); its values (channel
  7 note 63) are unambiguous, so it is kept.
- DECK1/3 and DECK2/4 (D26, deck-pair select): each press sends a
  multi-message sequence (switch one deck off, another on) rather than one
  simple press trigger -- DDJ-1000/DDJ-FLX10 already exclude the
  equivalent "DECK SELECT" function for the same reason. LOAD (B3) is
  *not* such a sequence: the table gives one plain channel-7 press per
  target deck (Deck1-4: notes 70-73), so it is modelled as LOAD DECK 1-4
  like DDJ-XP2's, each physical LOAD button covering its side's two decks
  (issue #350).
- MIC OFF/ON/TALKOVER (M15), AUX LINE/PORTABLE (M24), INPUT SELECT (M1):
  each a 2/3-position slide switch sending a *pair* of NOTE messages per
  position (one going high, a sibling going low) -- not one clean trigger
  per catalog's single-trigger-per-name model.

Re-checked row by row against a 300 DPI ``pdftoppm`` render of every page
of that PDF (issue #346): the only mismatch was BPM TRANSITION SELECT's
channel, fixed below. Issue #350 added the rows that check found missing
-- D24 HOT CUE and D25 SCRATCH BANK (plain deck-channel presses, notes
38/39) -- and LOAD, read from the same render. Field-verification against real hardware is still
open, same status as every other PDF-transcribed profile in this catalog
(issue #11).
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
    # BPM TRANSITION SELECT (D9) is printed on channel 7 (status 0x96), not
    # the deck channels: it is one global message, whichever deck's button
    # is pressed. Deck channels 1-4 note 62 are DECK1/3 / DECK2/4's
    # deck-on/off indicator (D26), not a press trigger (issue #346).
    ControlInfo("DDJ-REV5", "DECK", "BPM TRANSITION SELECT", "NOTE", ("7",), "62"),
    ControlInfo("DDJ-REV5", "DECK", "BPM TRANSITION START", "NOTE", _DECK_CHANNELS, "49"),
    ControlInfo("DDJ-REV5", "DECK", "LOOP 1/2X", "NOTE", _DECK_CHANNELS, "1"),
    ControlInfo("DDJ-REV5", "DECK", "LOOP 2X", "NOTE", _DECK_CHANNELS, "3"),
    ControlInfo("DDJ-REV5", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "40"),
    ControlInfo("DDJ-REV5", "DECK", "CENSOR", "NOTE", _DECK_CHANNELS, "41"),
    ControlInfo("DDJ-REV5", "DECK", "KEY -", "NOTE", _DECK_CHANNELS, "42"),
    ControlInfo("DDJ-REV5", "DECK", "KEY +", "NOTE", _DECK_CHANNELS, "43"),
    ControlInfo("DDJ-REV5", "DECK", "STEMS", "NOTE", _DECK_CHANNELS, "37"),
    # D24 HOT CUE / D25 SCRATCH BANK: the two buttons under KEY -/+ (their
    # +SHIFT rows, notes 54/55, print SAVED LOOP / SAMPLER below them).
    ControlInfo("DDJ-REV5", "DECK", "HOT CUE", "NOTE", _DECK_CHANNELS, "38"),
    ControlInfo("DDJ-REV5", "DECK", "SCRATCH BANK", "NOTE", _DECK_CHANNELS, "39"),
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
    # B3 LOAD: one channel-7 note per target deck, whichever side's LOAD
    # button sends it (the table's Deck1-Deck4 condition rows).
    ControlInfo("DDJ-REV5", "BROWSE", "LOAD DECK 1", "NOTE", ("7",), "70"),
    ControlInfo("DDJ-REV5", "BROWSE", "LOAD DECK 2", "NOTE", ("7",), "71"),
    ControlInfo("DDJ-REV5", "BROWSE", "LOAD DECK 3", "NOTE", ("7",), "72"),
    ControlInfo("DDJ-REV5", "BROWSE", "LOAD DECK 4", "NOTE", ("7",), "73"),
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

# The 8-pad grid has 8 named modes x 16 notes each (pad P = mode*16 + P-1),
# verified directly against the PDF's PERFORMANCE PADS group (P5 rows for
# pads 1-8), not assumed from another controller's layout. Notes 8-15 of
# each block are USER MODE or D20-D23 rows, left unnamed (see above).
# Order matches the PDF's own row order.
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
        reference_image="hardware/pioneer/DDJ-REV5/reference.png",
        display_order=60,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "BROWSE", "EFFECT", "MIXER", "PAD"),
    )
)
