"""Numark Mixtrack Pro FX MIDI profile.

This is a conservative community profile for the discrete transport and pad
controls. Numark mappings can vary with the selected DJ software and firmware;
continuous controls are intentionally not catalogued until verified against a
specific MIDI message list or a hardware capture.
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
    ControlInfo("Numark Mixtrack Pro FX", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "0"),
    ControlInfo("Numark Mixtrack Pro FX", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "1"),
    ControlInfo("Numark Mixtrack Pro FX", "DECK", "SYNC", "NOTE", _DECK_CHANNELS, "2"),
    ControlInfo("Numark Mixtrack Pro FX", "DECK", "LOOP", "NOTE", _DECK_CHANNELS, "3"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _DECK_CHANNELS:
        return None
    try:
        note = int(data1)
    except ValueError:
        return None
    if not 36 <= note <= 43:
        return None
    deck = _DECK_CHANNELS.index(channel) + 1
    return ControlInfo(
        "Numark Mixtrack Pro FX",
        "PAD",
        f"Deck {deck} Pad {note - 35}",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="Numark Mixtrack Pro FX",
        plugin_id="numark.mixtrack-pro-fx",
        manufacturer="Numark",
        supported_software=("serato", "virtualdj"),
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=8,
        section_order=("DECK", "PAD"),
        display_order=40,
    )
)
