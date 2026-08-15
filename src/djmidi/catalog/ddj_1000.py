"""DDJ-1000 controller definition.

The DDJ-1000 uses one MIDI channel per deck and four additional channels for
the performance-pad banks.  This first catalog deliberately covers the
discrete transport/loop controls and the 16-pad grid; continuous controls are
kept out of catalogs, as they cannot be represented by one useful trigger.
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
_PAD_CHANNELS = {"6": 1, "7": 2, "8": 3, "9": 4}

# Discrete controls shared by each of the four deck channels.  The values are
# the NOTE values from Pioneer DJ's DDJ-1000 MIDI message list.
_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-1000", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "0"),
    ControlInfo("DDJ-1000", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "1"),
    ControlInfo("DDJ-1000", "DECK", "SYNC", "NOTE", _DECK_CHANNELS, "2"),
    ControlInfo("DDJ-1000", "DECK", "MASTER TEMPO", "NOTE", _DECK_CHANNELS, "3"),
    ControlInfo("DDJ-1000", "DECK", "TEMPO RANGE", "NOTE", _DECK_CHANNELS, "4"),
    ControlInfo("DDJ-1000", "DECK", "KEYLOCK", "NOTE", _DECK_CHANNELS, "5"),
    ControlInfo("DDJ-1000", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "6"),
    ControlInfo("DDJ-1000", "DECK", "REVERSE", "NOTE", _DECK_CHANNELS, "7"),
    ControlInfo("DDJ-1000", "DECK", "LOOP IN", "NOTE", _DECK_CHANNELS, "10"),
    ControlInfo("DDJ-1000", "DECK", "LOOP OUT", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-1000", "DECK", "RELOOP/EXIT", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-1000", "DECK", "QUANTIZE", "NOTE", _DECK_CHANNELS, "13"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    """Resolve the DDJ-1000's 16 pads, including its eight pad modes."""
    if channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if kind != "NOTE" or note is None:
        return None
    mode, pad = divmod(note, 16)
    if mode >= 8:
        return None
    return ControlInfo(
        "DDJ-1000",
        "PAD",
        f"Deck {_PAD_CHANNELS[channel]} Pad {pad + 1} (PAD MODE {mode + 1})",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-1000",
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=16,
        pad_columns=8,
        section_order=("DECK", "PAD"),
    )
)
