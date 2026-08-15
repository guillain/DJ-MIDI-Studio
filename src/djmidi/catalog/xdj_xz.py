"""XDJ-XZ controller definition, transcribed from Pioneer's official MIDI
Message List PDF (linked in README.md). See catalog/__init__.py for scope
notes (discrete press/toggle controls only) shared across all controllers.
"""

from __future__ import annotations

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    _parse_midi_note,
    register,
)

# MIDI channel assignment (decimal): 1-4 = DECK 1-4, 5 = Mixer/Effect,
# 6-9 = Performance Pads DECK 1-4, 12 = Others & Jog Display.

_DECK_CH = ("1", "2", "3", "4")
_FX_CH = ("5",)
_PAD_CH_TO_DECK = {"6": 1, "7": 2, "8": 3, "9": 4}
_PAD_MODE_NAMES = [
    "HOT CUE",
    "BEAT LOOP",
    "SLIP LOOP",
    "BEAT JUMP",
    "EXTENSION1",
    "EXTENSION2",
    "EXTENSION3",
    "EXTENSION4",
]

_STATIC: list[ControlInfo] = [
    ControlInfo("XDJ-XZ", "DECK", "Jog dial touch", "NOTE", _DECK_CH, "32"),
    ControlInfo("XDJ-XZ", "DECK", "Jog dial touch (+SHIFT)", "NOTE", _DECK_CH, "72"),
    ControlInfo("XDJ-XZ", "DECK", "TEMPO RESET", "NOTE", _DECK_CH, "19"),
    ControlInfo("XDJ-XZ", "DECK", "MASTER TEMPO", "NOTE", _DECK_CH, "17"),
    ControlInfo("XDJ-XZ", "DECK", "TEMPO RANGE", "NOTE", _DECK_CH, "16"),
    ControlInfo("XDJ-XZ", "DECK", "SYNC", "NOTE", _DECK_CH, "31"),
    ControlInfo("XDJ-XZ", "DECK", "SYNC (long press)", "NOTE", _DECK_CH, "71"),
    ControlInfo("XDJ-XZ", "DECK", "MASTER", "NOTE", _DECK_CH, "30"),
    ControlInfo("XDJ-XZ", "DECK", "JOG MODE", "NOTE", _DECK_CH, "18"),
    ControlInfo("XDJ-XZ", "DECK", "TRACK SEARCH FWD", "NOTE", _DECK_CH, "4"),
    ControlInfo("XDJ-XZ", "DECK", "TRACK SEARCH REV", "NOTE", _DECK_CH, "5"),
    ControlInfo("XDJ-XZ", "DECK", "SEARCH FWD", "NOTE", _DECK_CH, "2"),
    ControlInfo("XDJ-XZ", "DECK", "SEARCH REV", "NOTE", _DECK_CH, "3"),
    ControlInfo("XDJ-XZ", "DECK", "SHIFT", "NOTE", _DECK_CH, "63"),
    ControlInfo("XDJ-XZ", "DECK", "REVERSE", "NOTE", _DECK_CH, "33"),
    ControlInfo("XDJ-XZ", "DECK", "SLIP", "NOTE", _DECK_CH, "44"),
    ControlInfo("XDJ-XZ", "DECK", "4 BEAT", "NOTE", _DECK_CH, "67"),
    ControlInfo("XDJ-XZ", "DECK", "4 BEAT (long press)", "NOTE", _DECK_CH, "68"),
    ControlInfo("XDJ-XZ", "DECK", "LOOP IN", "NOTE", _DECK_CH, "6"),
    ControlInfo("XDJ-XZ", "DECK", "LOOP IN (long press)", "NOTE", _DECK_CH, "69"),
    ControlInfo("XDJ-XZ", "DECK", "LOOP OUT", "NOTE", _DECK_CH, "7"),
    ControlInfo("XDJ-XZ", "DECK", "RELOOP/EXIT", "NOTE", _DECK_CH, "8"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP CALL NEXT", "NOTE", _DECK_CH, "11"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP CALL PREV", "NOTE", _DECK_CH, "12"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP DELETE", "NOTE", _DECK_CH, "13"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP MEMORY", "NOTE", _DECK_CH, "10"),
    ControlInfo("XDJ-XZ", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CH, "0"),
    ControlInfo("XDJ-XZ", "DECK", "CUE", "NOTE", _DECK_CH, "1"),
    ControlInfo("XDJ-XZ", "DECK", "LOAD", "NOTE", _DECK_CH, "81"),
    ControlInfo("XDJ-XZ", "DECK", "HOT CUE (direct button)", "NOTE", _DECK_CH, "34"),
    ControlInfo("XDJ-XZ", "DECK", "HOT CUE (direct button, +SHIFT)", "NOTE", _DECK_CH, "38"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT LOOP (direct button)", "NOTE", _DECK_CH, "35"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT LOOP (direct button, +SHIFT)", "NOTE", _DECK_CH, "39"),
    ControlInfo("XDJ-XZ", "DECK", "SLIP LOOP (direct button)", "NOTE", _DECK_CH, "36"),
    ControlInfo("XDJ-XZ", "DECK", "SLIP LOOP (direct button, +SHIFT)", "NOTE", _DECK_CH, "40"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT JUMP (direct button)", "NOTE", _DECK_CH, "37"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT JUMP (direct button, +SHIFT)", "NOTE", _DECK_CH, "41"),
    ControlInfo("XDJ-XZ", "EFFECT", "BEAT LEFT", "CC", _FX_CH, "76"),
    ControlInfo("XDJ-XZ", "EFFECT", "BEAT RIGHT", "CC", _FX_CH, "77"),
    ControlInfo("XDJ-XZ", "EFFECT", "AUTO/TAP", "CC", _FX_CH, "69"),
    ControlInfo("XDJ-XZ", "EFFECT", "TAP", "CC", _FX_CH, "78"),
    ControlInfo("XDJ-XZ", "EFFECT", "FX QUANTIZE", "NOTE", _FX_CH, "94"),
    ControlInfo("XDJ-XZ", "EFFECT", "FREQUENCY HI", "CC", _FX_CH, "102"),
    ControlInfo("XDJ-XZ", "EFFECT", "FREQUENCY MID", "CC", _FX_CH, "103"),
    ControlInfo("XDJ-XZ", "EFFECT", "FREQUENCY LOW", "CC", _FX_CH, "104"),
    ControlInfo("XDJ-XZ", "EFFECT", "BEAT EFFECT ON/OFF (= X-PAD press)", "CC", _FX_CH, "114"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: DELAY", "CC", _FX_CH, "42"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: ECHO", "CC", _FX_CH, "55"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: PING PONG", "CC", _FX_CH, "51"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: SPIRAL", "CC", _FX_CH, "43"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: REVERB", "CC", _FX_CH, "54"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: TRANS", "CC", _FX_CH, "53"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: FILTER", "CC", _FX_CH, "59"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: FLANGER", "CC", _FX_CH, "50"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: PHASER", "CC", _FX_CH, "57"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: PITCH", "CC", _FX_CH, "63"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: SPIRAL ROLL", "CC", _FX_CH, "58"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: ROLL", "CC", _FX_CH, "46"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: VINYL BRAKE", "CC", _FX_CH, "61"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: HELIX", "CC", _FX_CH, "62"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CF.A", "CC", _FX_CH, "39"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CF.B", "CC", _FX_CH, "40"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MIC1", "CC", _FX_CH, "28"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MIC2", "CC", _FX_CH, "29"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MIC1/2", "CC", _FX_CH, "38"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: AUX", "CC", _FX_CH, "32"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH3", "CC", _FX_CH, "36"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH1", "CC", _FX_CH, "34"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH2", "CC", _FX_CH, "35"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH4", "CC", _FX_CH, "37"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MASTER", "CC", _FX_CH, "41"),
    ControlInfo("XDJ-XZ", "EFFECT", "LEVEL DEPTH", "CC", _FX_CH, "91"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: SPACE", "CC", _FX_CH, "105"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: DUB ECHO", "CC", _FX_CH, "107"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: SWEEP", "CC", _FX_CH, "106"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: NOISE", "CC", _FX_CH, "85"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: CRUSH", "CC", _FX_CH, "86"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: FILTER", "CC", _FX_CH, "87"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    """8 pads x 8 modes, MIDI note = (pad-1) + mode_index*16 + (8 if +SHIFT else 0).
    Not a case for make_sequential_pad_lookup() — the +SHIFT variant of each pad
    lives in the upper half of the same 16-note mode block, not a separate mode."""
    if kind != "NOTE" or channel not in _PAD_CH_TO_DECK:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode_index, remainder = divmod(note, 16)
    if mode_index >= len(_PAD_MODE_NAMES):
        return None
    shifted = remainder >= 8
    pad = (remainder % 8) + 1
    deck = _PAD_CH_TO_DECK[channel]
    mode_name = _PAD_MODE_NAMES[mode_index]
    shift_suffix = " +SHIFT" if shifted else ""
    name = f"Deck {deck} Performance Pad {pad} ({mode_name} mode){shift_suffix}"
    return ControlInfo("XDJ-XZ", "PAD", name, "NOTE", (channel,), data1)


register(
    ControllerDefinition(
        name="XDJ-XZ",
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "EFFECT"),
    )
)
