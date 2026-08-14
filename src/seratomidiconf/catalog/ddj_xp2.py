"""DDJ-XP2 controller definition, transcribed from Pioneer's official MIDI
Message List PDF (linked in README.md). See catalog/__init__.py for scope
notes (discrete press/toggle controls only) shared across all controllers.
"""

from __future__ import annotations

from seratomidiconf.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    _parse_midi_note,
    register,
)

# MIDI channel assignment (decimal): 1-4 = DECK 1-4, 5/6 = SLIDE FX 1/2,
# 7 = BROWSER, 8/10/12/14 = DECK 1-4 PAD (no shift), 9/11/13/15 = same +SHIFT,
# 16 = MIDI-OUT illumination.

_DECK_CH = ("1", "2", "3", "4")
_FX_CH = ("5", "6")
_BROWSE_CH = ("7",)
_OUT_CH = ("16",)
_PAD_CH_TO_DECK = {"8": 1, "10": 2, "12": 3, "14": 4, "9": 1, "11": 2, "13": 3, "15": 4}
_PAD_SHIFT_CHANNELS = {"9", "11", "13", "15"}

_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-XP2", "DECK", "4 BEAT LOOP", "NOTE", _DECK_CH, "20"),
    ControlInfo("DDJ-XP2", "DECK", "4 BEAT LOOP (+SHIFT)", "NOTE", _DECK_CH, "80"),
    ControlInfo("DDJ-XP2", "DECK", "1/2X", "NOTE", _DECK_CH, "16"),
    ControlInfo("DDJ-XP2", "DECK", "1/2X (+SHIFT)", "NOTE", _DECK_CH, "76"),
    ControlInfo("DDJ-XP2", "DECK", "2X", "NOTE", _DECK_CH, "17"),
    ControlInfo("DDJ-XP2", "DECK", "2X (+SHIFT)", "NOTE", _DECK_CH, "77"),
    ControlInfo("DDJ-XP2", "DECK", "QUANTIZE", "NOTE", _DECK_CH, "53"),
    ControlInfo("DDJ-XP2", "DECK", "QUANTIZE (+SHIFT)", "NOTE", _DECK_CH, "57"),
    ControlInfo("DDJ-XP2", "DECK", "BEAT SYNC", "NOTE", _DECK_CH, "88"),
    ControlInfo("DDJ-XP2", "DECK", "BEAT SYNC (+SHIFT)", "NOTE", _DECK_CH, "92"),
    ControlInfo("DDJ-XP2", "DECK", "SILENT CUE", "NOTE", _DECK_CH, "104"),
    ControlInfo("DDJ-XP2", "DECK", "SILENT CUE (+SHIFT)", "NOTE", _DECK_CH, "120"),
    ControlInfo("DDJ-XP2", "DECK", "KEY -", "NOTE", _DECK_CH, "10"),
    ControlInfo("DDJ-XP2", "DECK", "KEY - (+SHIFT)", "NOTE", _DECK_CH, "101"),
    ControlInfo("DDJ-XP2", "DECK", "KEY +", "NOTE", _DECK_CH, "121"),
    ControlInfo("DDJ-XP2", "DECK", "KEY + (+SHIFT)", "NOTE", _DECK_CH, "100"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 1", "NOTE", _DECK_CH, "27"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 1 (+SHIFT)", "NOTE", _DECK_CH, "105"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 2", "NOTE", _DECK_CH, "30"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 2 (+SHIFT)", "NOTE", _DECK_CH, "107"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 3", "NOTE", _DECK_CH, "32"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 3 (+SHIFT)", "NOTE", _DECK_CH, "109"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 4", "NOTE", _DECK_CH, "34"),
    ControlInfo("DDJ-XP2", "PAD MODE", "PAD MODE 4 (+SHIFT)", "NOTE", _DECK_CH, "111"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 1", "NOTE", _FX_CH, "112"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 1 (+SHIFT)", "NOTE", _FX_CH, "115"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 2", "NOTE", _FX_CH, "113"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 2 (+SHIFT)", "NOTE", _FX_CH, "116"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 3", "NOTE", _FX_CH, "114"),
    ControlInfo("DDJ-XP2", "EFFECT", "EFFECT 3 (+SHIFT)", "NOTE", _FX_CH, "117"),
    ControlInfo("DDJ-XP2", "EFFECT", "TOUCH STRIP HOLD", "NOTE", _FX_CH, "118"),
    ControlInfo("DDJ-XP2", "BROWSE", "Rotary Selector (press)", "NOTE", _BROWSE_CH, "65"),
    ControlInfo("DDJ-XP2", "BROWSE", "Rotary Selector (+SHIFT press)", "NOTE", _BROWSE_CH, "66"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 1", "NOTE", _BROWSE_CH, "70"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 2", "NOTE", _BROWSE_CH, "71"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 3", "NOTE", _BROWSE_CH, "72"),
    ControlInfo("DDJ-XP2", "BROWSE", "LOAD DECK 4", "NOTE", _BROWSE_CH, "73"),
    ControlInfo("DDJ-XP2", "OTHER", "SHIFT", "NOTE", _BROWSE_CH, "64"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 1)", "NOTE", _OUT_CH, "0"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 2)", "NOTE", _OUT_CH, "1"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 3)", "NOTE", _OUT_CH, "2"),
    ControlInfo("DDJ-XP2", "MIDI-OUT", "Loaded (Deck 4)", "NOTE", _OUT_CH, "3"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    """16 pads x 8 modes, MIDI note = base(pad) + (mode-1)*16, where
    base(pad) walks each group of 4 pads from high to low: pad1-4 -> 12-15,
    pad5-8 -> 8-11, pad9-12 -> 4-7, pad13-16 -> 0-3 (verified against the PDF).
    Not a case for make_sequential_pad_lookup() — the note order isn't linear."""
    if kind != "NOTE" or channel not in _PAD_CH_TO_DECK:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode = note // 16 + 1
    base = note % 16
    group, pos = divmod(base, 4)
    pad = (3 - group) * 4 + pos + 1
    deck = _PAD_CH_TO_DECK[channel]
    shift_suffix = " +SHIFT" if channel in _PAD_SHIFT_CHANNELS else ""
    name = f"Deck {deck} Pad {pad} (PAD MODE {mode}){shift_suffix}"
    return ControlInfo("DDJ-XP2", "PAD", name, "NOTE", (channel,), data1)


register(
    ControllerDefinition(
        name="DDJ-XP2",
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=16,
        pad_columns=4,
        section_order=("DECK", "PAD MODE", "EFFECT", "BROWSE", "OTHER", "MIDI-OUT"),
    )
)
