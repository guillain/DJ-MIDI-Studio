"""DDJ-800 controller definition, transcribed from Pioneer's official MIDI
Message List PDF (controllers/ddj-800/ddj-800-midi-message-list-e3.pdf).

Like DDJ-REV5, the DDJ-800 is modeled as a 4-deck-channel controller: one
MIDI channel per deck (1-4) for DECK-section controls, a shared channel 7
for BROWSE/global controls, channel 5 for its single FX unit, and eight
additional channels (four decks x on/+SHIFT) for the performance-pad bank.

Deliberately conservative, following the same exclusion discipline already
established by DDJ-1000/DDJ-FLX10/DDJ-REV5 -- never modeling a
"+SHIFT <control>" as a separate entry (every DECK/BROWSE/EFFECT/MIXER
+SHIFT row in the PDF duplicates its base control's Data1 on the same
channel; only the pad grid's shift is channel-based, see below). Also
excluded, each for its own concrete reason rather than fabricated:

- LOAD (B2-L/B2-R): each of the two physical LOAD buttons sends a
  different trigger depending on which deck is currently "selected" on
  that side (deck1 vs deck2 on the left button, deck3 vs deck4 on the
  right) -- not one deterministic value per physical button. Same
  reasoning DDJ-REV5 already applied to its own LOAD/DECK-select controls.
- MIC OFF/ON (M19) and INPUT SELECT (M18): each sends a *pair* of NOTE
  messages per switch position (one going high, a sibling going low) --
  not one clean trigger per catalog's single-trigger-per-name model, same
  pattern DDJ-REV5 excluded MIC OFF/ON/TALKOVER for.
- CROSSFADER (Fader Start) (M1) and CH FADER (Fader Start) (M2): edge-
  triggered NOTE messages fired when the *continuous* fader crosses zero
  (4-6 conditional messages per control, A-side/B-side x zero-crossing
  direction) -- an emergent trigger from analog fader movement, not a
  discrete press/toggle control.
- FX SELECT (F8) and CH SELECT (F9): both are encoder *rotations* that
  step through named values (many FX types / channel targets) rather than
  a press -- continuous, out of catalog scope like every other rotary.
- The pad grid's PAGE t/u buttons (Fig. P13/P14): the source PDF's table
  layout for this row could not be reliably machine-extracted -- the
  footnote (*1) describes two simple single-purpose buttons ("press PAGE
  t to switch to PAGE 1, PAGE u to switch to PAGE 2"), but the extracted
  text shows eight different Data1 values per row that don't resolve to
  that description without the source image or hardware to check against.
  Left out rather than guessed. The pad grid below still models both
  PAGE 1 and PAGE 2 states for every named mode (their own rows are
  unambiguous), so this only means the PAGE-switch buttons themselves
  aren't independently catalogued, not that PAGE 2 pad hits go unresolved.

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

# Discrete DECK-section controls shared by each of the four deck channels.
# Data1 values are the "MIDI Data (Data1) (Dec)" column, DECK group.
_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-800", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-800", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-800", "DECK", "MASTER TEMPO", "NOTE", _DECK_CHANNELS, "26"),
    ControlInfo("DDJ-800", "DECK", "BEAT SYNC", "NOTE", _DECK_CHANNELS, "88"),
    ControlInfo("DDJ-800", "DECK", "KEY SYNC", "NOTE", _DECK_CHANNELS, "101"),
    ControlInfo("DDJ-800", "DECK", "TEMPO RANGE", "NOTE", _DECK_CHANNELS, "96"),
    ControlInfo("DDJ-800", "DECK", "LOOP IN", "NOTE", _DECK_CHANNELS, "16"),
    ControlInfo("DDJ-800", "DECK", "LOOP OUT", "NOTE", _DECK_CHANNELS, "17"),
    ControlInfo("DDJ-800", "DECK", "RELOOP/EXIT", "NOTE", _DECK_CHANNELS, "77"),
    ControlInfo("DDJ-800", "DECK", "QUANTIZE", "NOTE", _DECK_CHANNELS, "53"),
    ControlInfo("DDJ-800", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "64"),
    ControlInfo("DDJ-800", "DECK", "SLIP REVERSE", "NOTE", _DECK_CHANNELS, "21"),
    ControlInfo("DDJ-800", "DECK", "SEARCH <", "NOTE", _DECK_CHANNELS, "94"),
    ControlInfo("DDJ-800", "DECK", "SEARCH >", "NOTE", _DECK_CHANNELS, "95"),
    ControlInfo("DDJ-800", "DECK", "MEMORY", "NOTE", _DECK_CHANNELS, "61"),
    ControlInfo("DDJ-800", "DECK", "DELETE", "NOTE", _DECK_CHANNELS, "62"),
    ControlInfo("DDJ-800", "DECK", "CUE/LOOP CALL <", "NOTE", _DECK_CHANNELS, "81"),
    ControlInfo("DDJ-800", "DECK", "CUE/LOOP CALL >", "NOTE", _DECK_CHANNELS, "83"),
    ControlInfo("DDJ-800", "DECK", "SHIFT", "NOTE", _DECK_CHANNELS, "63"),
    # Pad-mode select buttons (P9-P12 in the PDF): press only, switching
    # which of the pad grid's named modes below is active. Only 4 of the
    # grid's 8 named modes have their own direct select button in the PDF
    # -- see the module docstring's PAGE t/u note for the other 4.
    ControlInfo("DDJ-800", "DECK", "HOT CUE MODE", "NOTE", _DECK_CHANNELS, "27"),
    ControlInfo("DDJ-800", "DECK", "PAD FX MODE", "NOTE", _DECK_CHANNELS, "30"),
    ControlInfo("DDJ-800", "DECK", "BEAT JUMP MODE", "NOTE", _DECK_CHANNELS, "32"),
    ControlInfo("DDJ-800", "DECK", "SAMPLER MODE", "NOTE", _DECK_CHANNELS, "34"),
    # BROWSE group, channel 7 (the shared BROWSER/Global Section channel).
    ControlInfo("DDJ-800", "BROWSE", "BROWSE", "NOTE", ("7",), "65"),
    ControlInfo("DDJ-800", "BROWSE", "BACK", "NOTE", ("7",), "101"),
    ControlInfo("DDJ-800", "BROWSE", "VIEW", "NOTE", ("7",), "103"),
    # EFFECT group. COLOR FX buttons sit on the shared channel 7 in the
    # PDF (not the dedicated EFFECT channel 5); BEAT </>/ON-OFF do use
    # channel 5.
    ControlInfo("DDJ-800", "EFFECT", "COLOR FX D-ECHO", "NOTE", ("7",), "0"),
    ControlInfo("DDJ-800", "EFFECT", "COLOR FX PITCH", "NOTE", ("7",), "1"),
    ControlInfo("DDJ-800", "EFFECT", "COLOR FX NOISE", "NOTE", ("7",), "2"),
    ControlInfo("DDJ-800", "EFFECT", "COLOR FX FILTER", "NOTE", ("7",), "3"),
    ControlInfo("DDJ-800", "EFFECT", "BEAT <", "NOTE", ("5",), "74"),
    ControlInfo("DDJ-800", "EFFECT", "BEAT >", "NOTE", ("5",), "75"),
    ControlInfo("DDJ-800", "EFFECT", "BEAT FX ON/OFF", "NOTE", ("5",), "71"),
    # MIXER group. HEADPHONES CUE is one physical button per deck channel
    # strip, same _DECK_CHANNELS shape as DECK-section controls.
    ControlInfo("DDJ-800", "MIXER", "HEADPHONES CUE", "NOTE", _DECK_CHANNELS, "84"),
    ControlInfo("DDJ-800", "MIXER", "MASTER CUE", "NOTE", ("7",), "99"),
    # A single clean OFF=PHONO/ON=LINE toggle (unlike M18/M19's paired-
    # message switches above) -- channels 1/2 only, per the PDF's own
    # "1/2" condition column (this mixer input select is 2-channel, not
    # tied to all four deck channels).
    ControlInfo("DDJ-800", "MIXER", "LINE/PHONO SW", "NOTE", ("1", "2"), "70"),
]

# The 8-pad grid has 8 named modes, each split into PAGE 1/PAGE 2 (16
# notes per mode, 8 used per page), covering the full 0-127 Data1 range
# with no gaps -- verified directly against the PDF's PAD group rows for
# pads 1, 2, 7, and 8 across every named mode. Order matches the PDF's
# own row order.
_PAD_MODE_NAMES = (
    "HOT CUE",
    "PAD FX 1",
    "BEAT JUMP",
    "SAMPLER",
    "KEYBOARD",
    "PAD FX 2",
    "BEAT LOOP",
    "KEY SHIFT",
)

# channel -> (deck, is_shifted). Same convention as DDJ-1000/DDJ-FLX10/
# DDJ-REV5: the pad grid's +SHIFT state is carried entirely by which
# channel a pad hit arrives on (identical Data1 on both), not by a
# different NOTE range.
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
    """Resolve the DDJ-800's 8-pad grid across its 8 named modes x 2 pages."""
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode, rest = divmod(note, 16)
    page, pad = divmod(rest, 8)
    if mode >= len(_PAD_MODE_NAMES) or pad >= 8:
        return None
    deck, shifted = _PAD_CHANNELS[channel]
    suffix = " (+SHIFT)" if shifted else ""
    return ControlInfo(
        "DDJ-800",
        "PAD",
        f"Deck {deck} Pad {pad + 1} ({_PAD_MODE_NAMES[mode]} PAGE {page + 1}){suffix}",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-800",
        plugin_id="pioneer.ddj-800",
        manufacturer="Pioneer DJ",
        supported_software=("serato",),
        reference_image="ddj-800/reference.png",
        display_order=61,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "BROWSE", "EFFECT", "MIXER", "PAD"),
    )
)
