"""Hercules DJControl Inpulse 500 MIDI profile.

This profile covers a small, stable set of discrete controls and the two
eight-pad banks. Jog wheels, faders, EQ knobs, and touch strips are omitted;
verify the profile against the installed DJ software before using it for a
production mapping.
"""

from __future__ import annotations

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    register,
)

_DECK_CHANNELS = ("1", "2")
_STATIC = [
    ControlInfo("Hercules DJControl Inpulse 500", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "10"),
    ControlInfo("Hercules DJControl Inpulse 500", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("Hercules DJControl Inpulse 500", "DECK", "SYNC", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("Hercules DJControl Inpulse 500", "DECK", "BEATJUMP", "NOTE", _DECK_CHANNELS, "13"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _DECK_CHANNELS:
        return None
    try:
        note = int(data1)
    except ValueError:
        return None
    if not 40 <= note <= 47:
        return None
    deck = _DECK_CHANNELS.index(channel) + 1
    return ControlInfo(
        "Hercules DJControl Inpulse 500",
        "PAD",
        f"Deck {deck} Pad {note - 39}",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="Hercules DJControl Inpulse 500",
        plugin_id="hercules.djcontrol-inpulse-500",
        manufacturer="Hercules",
        supported_software=("serato", "virtualdj"),
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=8,
        section_order=("DECK", "PAD"),
        display_order=50,
    )
)
