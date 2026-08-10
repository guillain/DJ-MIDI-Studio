"""Reference tables mapping raw MIDI (channel, NOTE/CC, data1) triples to the
physical control name on the DDJ-XP2 and XDJ-XZ, transcribed from Pioneer's
official MIDI Message List PDFs (linked in README.md).

Scope: discrete press/toggle controls (buttons, pad grids) on both
controllers, which are what Serato MIDI configs actually remap. Continuous
controls (faders, TRIM/EQ knobs, jog wheels, the TIME/TOUCH STRIP encoders)
are intentionally left out: they're rarely remapped and their value ranges
don't reduce to a single readable name. Extend `_STATIC_ENTRIES` below the
same way to add more.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NoteOrCC = Literal["NOTE", "CC"]


@dataclass(frozen=True)
class ControlInfo:
    controller: str
    section: str
    name: str
    note_or_cc: NoteOrCC
    channels: tuple[str, ...]
    data1: str


def _event_kind(event_type: str | None) -> NoteOrCC | None:
    if not event_type:
        return None
    lowered = event_type.lower()
    if "note" in lowered:
        return "NOTE"
    if "control" in lowered:
        return "CC"
    return None


# ---------------------------------------------------------------------------
# DDJ-XP2
# ---------------------------------------------------------------------------
# MIDI channel assignment (decimal): 1-4 = DECK 1-4, 5/6 = SLIDE FX 1/2,
# 7 = BROWSER, 8/10/12/14 = DECK 1-4 PAD (no shift), 9/11/13/15 = same +SHIFT,
# 16 = MIDI-OUT illumination.

_XP2_DECK_CH = ("1", "2", "3", "4")
_XP2_FX_CH = ("5", "6")
_XP2_BROWSE_CH = ("7",)
_XP2_OUT_CH = ("16",)
_XP2_PAD_CH_TO_DECK = {"8": 1, "10": 2, "12": 3, "14": 4, "9": 1, "11": 2, "13": 3, "15": 4}
_XP2_PAD_SHIFT_CHANNELS = {"9", "11", "13", "15"}

_XP2_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-XP2", "DECK", "4 BEAT LOOP", "NOTE", _XP2_DECK_CH, "20"),
    ControlInfo("DDJ-XP2", "DECK", "4 BEAT LOOP (+SHIFT)", "NOTE", _XP2_DECK_CH, "80"),
    ControlInfo("DDJ-XP2", "DECK", "1/2X", "NOTE", _XP2_DECK_CH, "16"),
    ControlInfo("DDJ-XP2", "DECK", "1/2X (+SHIFT)", "NOTE", _XP2_DECK_CH, "76"),
    ControlInfo("DDJ-XP2", "DECK", "2X", "NOTE", _XP2_DECK_CH, "17"),
    ControlInfo("DDJ-XP2", "DECK", "2X (+SHIFT)", "NOTE", _XP2_DECK_CH, "77"),
    ControlInfo("DDJ-XP2", "DECK", "QUANTIZE", "NOTE", _XP2_DECK_CH, "53"),
    ControlInfo("DDJ-XP2", "DECK", "QUANTIZE (+SHIFT)", "NOTE", _XP2_DECK_CH, "57"),
    ControlInfo("DDJ-XP2", "DECK", "BEAT SYNC", "NOTE", _XP2_DECK_CH, "88"),
    ControlInfo("DDJ-XP2", "DECK", "BEAT SYNC (+SHIFT)", "NOTE", _XP2_DECK_CH, "92"),
    ControlInfo("DDJ-XP2", "DECK", "SILENT CUE", "NOTE", _XP2_DECK_CH, "104"),
    ControlInfo("DDJ-XP2", "DECK", "SILENT CUE (+SHIFT)", "NOTE", _XP2_DECK_CH, "120"),
    ControlInfo("DDJ-XP2", "DECK", "KEY -", "NOTE", _XP2_DECK_CH, "10"),
    ControlInfo("DDJ-XP2", "DECK", "KEY - (+SHIFT)", "NOTE", _XP2_DECK_CH, "101"),
    ControlInfo("DDJ-XP2", "DECK", "KEY +", "NOTE", _XP2_DECK_CH, "121"),
    ControlInfo("DDJ-XP2", "DECK", "KEY + (+SHIFT)", "NOTE", _XP2_DECK_CH, "100"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 1", "NOTE", _XP2_DECK_CH, "27"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 1 (+SHIFT)", "NOTE", _XP2_DECK_CH, "105"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 2", "NOTE", _XP2_DECK_CH, "30"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 2 (+SHIFT)", "NOTE", _XP2_DECK_CH, "107"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 3", "NOTE", _XP2_DECK_CH, "32"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 3 (+SHIFT)", "NOTE", _XP2_DECK_CH, "109"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 4", "NOTE", _XP2_DECK_CH, "34"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 4 (+SHIFT)", "NOTE", _XP2_DECK_CH, "111"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 1", "NOTE", _XP2_FX_CH, "112"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 1 (+SHIFT)", "NOTE", _XP2_FX_CH, "115"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 2", "NOTE", _XP2_FX_CH, "113"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 2 (+SHIFT)", "NOTE", _XP2_FX_CH, "116"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 3", "NOTE", _XP2_FX_CH, "114"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 3 (+SHIFT)", "NOTE", _XP2_FX_CH, "117"),
    ControlInfo("DDJ-XP2", "EFFECT", "TOUCH STRIP HOLD", "NOTE", _XP2_FX_CH, "118"),
    ControlInfo("DDJ-XP2", "BROWSE", "Rotary Selector (press)", "NOTE", _XP2_BROWSE_CH, "65"),
    ControlInfo("DDJ-XP2", "BROWSE", "Rotary Selector (+SHIFT press)", "NOTE", _XP2_BROWSE_CH, "66"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 1", "NOTE", _XP2_BROWSE_CH, "70"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 2", "NOTE", _XP2_BROWSE_CH, "71"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 3", "NOTE", _XP2_BROWSE_CH, "72"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 4", "NOTE", _XP2_BROWSE_CH, "73"),
    ControlInfo("DDJ-XP2", "OTHER", "SHIFT", "NOTE", _XP2_BROWSE_CH, "64"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 1)", "NOTE", _XP2_OUT_CH, "0"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 2)", "NOTE", _XP2_OUT_CH, "1"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 3)", "NOTE", _XP2_OUT_CH, "2"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 4)", "NOTE", _XP2_OUT_CH, "3"),
]


def _xp2_pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    """16 pads x 8 modes, MIDI note = base(pad) + (mode-1)*16, where
    base(pad) walks each group of 4 pads from high to low: pad1-4 -> 12-15,
    pad5-8 -> 8-11, pad9-12 -> 4-7, pad13-16 -> 0-3 (verified against the PDF)."""
    if kind != "NOTE" or channel not in _XP2_PAD_CH_TO_DECK:
        return None
    try:
        note = int(data1)
    except ValueError:
        return None
    if not 0 <= note <= 127:
        return None
    mode = note // 16 + 1
    base = note % 16
    group, pos = divmod(base, 4)
    pad = (3 - group) * 4 + pos + 1
    deck = _XP2_PAD_CH_TO_DECK[channel]
    shift_suffix = " +SHIFT" if channel in _XP2_PAD_SHIFT_CHANNELS else ""
    name = f"Deck {deck} Pad {pad} (PAD MODE {mode}){shift_suffix}"
    return ControlInfo("DDJ-XP2", "PAD", name, "NOTE", (channel,), data1)


# ---------------------------------------------------------------------------
# XDJ-XZ
# ---------------------------------------------------------------------------
# MIDI channel assignment (decimal): 1-4 = DECK 1-4, 5 = Mixer/Effect,
# 6-9 = Performance Pads DECK 1-4, 12 = Others & Jog Display.

_XZ_DECK_CH = ("1", "2", "3", "4")
_XZ_FX_CH = ("5",)
_XZ_PAD_CH_TO_DECK = {"6": 1, "7": 2, "8": 3, "9": 4}
_XZ_PAD_MODE_NAMES = [
    "HOT CUE",
    "BEAT LOOP",
    "SLIP LOOP",
    "BEAT JUMP",
    "EXTENSION1",
    "EXTENSION2",
    "EXTENSION3",
    "EXTENSION4",
]

_XZ_STATIC: list[ControlInfo] = [
    ControlInfo("XDJ-XZ", "DECK", "Jog dial touch", "NOTE", _XZ_DECK_CH, "32"),
    ControlInfo("XDJ-XZ", "DECK", "Jog dial touch (+SHIFT)", "NOTE", _XZ_DECK_CH, "72"),
    ControlInfo("XDJ-XZ", "DECK", "TEMPO RESET", "NOTE", _XZ_DECK_CH, "19"),
    ControlInfo("XDJ-XZ", "DECK", "MASTER TEMPO", "NOTE", _XZ_DECK_CH, "17"),
    ControlInfo("XDJ-XZ", "DECK", "TEMPO RANGE", "NOTE", _XZ_DECK_CH, "16"),
    ControlInfo("XDJ-XZ", "DECK", "SYNC", "NOTE", _XZ_DECK_CH, "31"),
    ControlInfo("XDJ-XZ", "DECK", "SYNC (long press)", "NOTE", _XZ_DECK_CH, "71"),
    ControlInfo("XDJ-XZ", "DECK", "MASTER", "NOTE", _XZ_DECK_CH, "30"),
    ControlInfo("XDJ-XZ", "DECK", "JOG MODE", "NOTE", _XZ_DECK_CH, "18"),
    ControlInfo("XDJ-XZ", "DECK", "TRACK SEARCH FWD", "NOTE", _XZ_DECK_CH, "4"),
    ControlInfo("XDJ-XZ", "DECK", "TRACK SEARCH REV", "NOTE", _XZ_DECK_CH, "5"),
    ControlInfo("XDJ-XZ", "DECK", "SEARCH FWD", "NOTE", _XZ_DECK_CH, "2"),
    ControlInfo("XDJ-XZ", "DECK", "SEARCH REV", "NOTE", _XZ_DECK_CH, "3"),
    ControlInfo("XDJ-XZ", "DECK", "SHIFT", "NOTE", _XZ_DECK_CH, "63"),
    ControlInfo("XDJ-XZ", "DECK", "REVERSE", "NOTE", _XZ_DECK_CH, "33"),
    ControlInfo("XDJ-XZ", "DECK", "SLIP", "NOTE", _XZ_DECK_CH, "44"),
    ControlInfo("XDJ-XZ", "DECK", "4 BEAT", "NOTE", _XZ_DECK_CH, "67"),
    ControlInfo("XDJ-XZ", "DECK", "4 BEAT (long press)", "NOTE", _XZ_DECK_CH, "68"),
    ControlInfo("XDJ-XZ", "DECK", "LOOP IN", "NOTE", _XZ_DECK_CH, "6"),
    ControlInfo("XDJ-XZ", "DECK", "LOOP IN (long press)", "NOTE", _XZ_DECK_CH, "69"),
    ControlInfo("XDJ-XZ", "DECK", "LOOP OUT", "NOTE", _XZ_DECK_CH, "7"),
    ControlInfo("XDJ-XZ", "DECK", "RELOOP/EXIT", "NOTE", _XZ_DECK_CH, "8"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP CALL NEXT", "NOTE", _XZ_DECK_CH, "11"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP CALL PREV", "NOTE", _XZ_DECK_CH, "12"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP DELETE", "NOTE", _XZ_DECK_CH, "13"),
    ControlInfo("XDJ-XZ", "DECK", "CUE/LOOP MEMORY", "NOTE", _XZ_DECK_CH, "10"),
    ControlInfo("XDJ-XZ", "DECK", "PLAY/PAUSE", "NOTE", _XZ_DECK_CH, "0"),
    ControlInfo("XDJ-XZ", "DECK", "CUE", "NOTE", _XZ_DECK_CH, "1"),
    ControlInfo("XDJ-XZ", "DECK", "LOAD", "NOTE", _XZ_DECK_CH, "81"),
    ControlInfo("XDJ-XZ", "DECK", "HOT CUE (direct button)", "NOTE", _XZ_DECK_CH, "34"),
    ControlInfo("XDJ-XZ", "DECK", "HOT CUE (direct button, +SHIFT)", "NOTE", _XZ_DECK_CH, "38"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT LOOP (direct button)", "NOTE", _XZ_DECK_CH, "35"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT LOOP (direct button, +SHIFT)", "NOTE", _XZ_DECK_CH, "39"),
    ControlInfo("XDJ-XZ", "DECK", "SLIP LOOP (direct button)", "NOTE", _XZ_DECK_CH, "36"),
    ControlInfo("XDJ-XZ", "DECK", "SLIP LOOP (direct button, +SHIFT)", "NOTE", _XZ_DECK_CH, "40"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT JUMP (direct button)", "NOTE", _XZ_DECK_CH, "37"),
    ControlInfo("XDJ-XZ", "DECK", "BEAT JUMP (direct button, +SHIFT)", "NOTE", _XZ_DECK_CH, "41"),
    ControlInfo("XDJ-XZ", "EFFECT", "BEAT LEFT", "CC", _XZ_FX_CH, "76"),
    ControlInfo("XDJ-XZ", "EFFECT", "BEAT RIGHT", "CC", _XZ_FX_CH, "77"),
    ControlInfo("XDJ-XZ", "EFFECT", "AUTO/TAP", "CC", _XZ_FX_CH, "69"),
    ControlInfo("XDJ-XZ", "EFFECT", "TAP", "CC", _XZ_FX_CH, "78"),
    ControlInfo("XDJ-XZ", "EFFECT", "FX QUANTIZE", "NOTE", _XZ_FX_CH, "94"),
    ControlInfo("XDJ-XZ", "EFFECT", "FREQUENCY HI", "CC", _XZ_FX_CH, "102"),
    ControlInfo("XDJ-XZ", "EFFECT", "FREQUENCY MID", "CC", _XZ_FX_CH, "103"),
    ControlInfo("XDJ-XZ", "EFFECT", "FREQUENCY LOW", "CC", _XZ_FX_CH, "104"),
    ControlInfo("XDJ-XZ", "EFFECT", "BEAT EFFECT ON/OFF (= X-PAD press)", "CC", _XZ_FX_CH, "114"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: DELAY", "CC", _XZ_FX_CH, "42"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: ECHO", "CC", _XZ_FX_CH, "55"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: PING PONG", "CC", _XZ_FX_CH, "51"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: SPIRAL", "CC", _XZ_FX_CH, "43"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: REVERB", "CC", _XZ_FX_CH, "54"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: TRANS", "CC", _XZ_FX_CH, "53"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: FILTER", "CC", _XZ_FX_CH, "59"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: FLANGER", "CC", _XZ_FX_CH, "50"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: PHASER", "CC", _XZ_FX_CH, "57"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: PITCH", "CC", _XZ_FX_CH, "63"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: SPIRAL ROLL", "CC", _XZ_FX_CH, "58"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: ROLL", "CC", _XZ_FX_CH, "46"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: VINYL BRAKE", "CC", _XZ_FX_CH, "61"),
    ControlInfo("XDJ-XZ", "EFFECT", "EFFECT SELECT: HELIX", "CC", _XZ_FX_CH, "62"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CF.A", "CC", _XZ_FX_CH, "39"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CF.B", "CC", _XZ_FX_CH, "40"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MIC1", "CC", _XZ_FX_CH, "28"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MIC2", "CC", _XZ_FX_CH, "29"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MIC1/2", "CC", _XZ_FX_CH, "38"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: AUX", "CC", _XZ_FX_CH, "32"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH3", "CC", _XZ_FX_CH, "36"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH1", "CC", _XZ_FX_CH, "34"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH2", "CC", _XZ_FX_CH, "35"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: CH4", "CC", _XZ_FX_CH, "37"),
    ControlInfo("XDJ-XZ", "EFFECT", "CH SELECT: MASTER", "CC", _XZ_FX_CH, "41"),
    ControlInfo("XDJ-XZ", "EFFECT", "LEVEL DEPTH", "CC", _XZ_FX_CH, "91"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: SPACE", "CC", _XZ_FX_CH, "105"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: DUB ECHO", "CC", _XZ_FX_CH, "107"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: SWEEP", "CC", _XZ_FX_CH, "106"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: NOISE", "CC", _XZ_FX_CH, "85"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: CRUSH", "CC", _XZ_FX_CH, "86"),
    ControlInfo("XDJ-XZ", "EFFECT", "Sound Color FX: FILTER", "CC", _XZ_FX_CH, "87"),
]


def _xz_pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    """8 pads x 8 modes, MIDI note = (pad-1) + mode_index*16 + (8 if +SHIFT else 0)."""
    if kind != "NOTE" or channel not in _XZ_PAD_CH_TO_DECK:
        return None
    try:
        note = int(data1)
    except ValueError:
        return None
    if not 0 <= note <= 127:
        return None
    mode_index, remainder = divmod(note, 16)
    if mode_index >= len(_XZ_PAD_MODE_NAMES):
        return None
    shifted = remainder >= 8
    pad = (remainder % 8) + 1
    deck = _XZ_PAD_CH_TO_DECK[channel]
    mode_name = _XZ_PAD_MODE_NAMES[mode_index]
    shift_suffix = " +SHIFT" if shifted else ""
    name = f"Deck {deck} Performance Pad {pad} ({mode_name} mode){shift_suffix}"
    return ControlInfo("XDJ-XZ", "PAD", name, "NOTE", (channel,), data1)


_STATIC_ENTRIES: list[ControlInfo] = _XP2_STATIC + _XZ_STATIC
_PAD_LOOKUPS = (_xp2_pad_lookup, _xz_pad_lookup)

PAD_COUNTS = {"DDJ-XP2": 16, "XDJ-XZ": 8}


def static_entries(controller: str) -> list[ControlInfo]:
    if controller == "DDJ-XP2":
        return list(_XP2_STATIC)
    if controller == "XDJ-XZ":
        return list(_XZ_STATIC)
    raise ValueError(f"Unknown controller: {controller}")


def lookup(channel: str | None, event_type: str | None, data1: str | None) -> list[ControlInfo]:
    """Returns every known physical control matching this (channel, event_type, data1)
    triple, across both controllers (a config file mixing controllers doesn't self-identify
    which one sent a given message, so both catalogs are always checked)."""
    if not channel or not data1:
        return []
    kind = _event_kind(event_type)
    if kind is None:
        return []
    results = [entry for entry in _STATIC_ENTRIES if entry.note_or_cc == kind and channel in entry.channels and entry.data1 == data1]
    for pad_lookup in _PAD_LOOKUPS:
        found = pad_lookup(channel, kind, data1)
        if found is not None:
            results.append(found)
    return results
