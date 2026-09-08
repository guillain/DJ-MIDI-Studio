"""Pioneer DJ DDJ-REV1 MIDI profile.

The discrete controls and pad note layout are transcribed from Pioneer DJ's
official DDJ-REV1 MIDI Message List E1. The profile intentionally omits jog,
fader, EQ and FX continuous controls; those need value-aware mappings rather
than a single catalog trigger.
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

_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-REV1", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-REV1", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-REV1", "DECK", "AUTO LOOP", "NOTE", _DECK_CHANNELS, "20"),
    ControlInfo("DDJ-REV1", "DECK", "1/2X", "NOTE", _DECK_CHANNELS, "16"),
    ControlInfo("DDJ-REV1", "DECK", "2X", "NOTE", _DECK_CHANNELS, "17"),
    ControlInfo("DDJ-REV1", "DECK", "SYNC", "NOTE", _DECK_CHANNELS, "88"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode, pad = divmod(note, 16)
    if mode >= 8 or pad >= 8:
        return None
    deck, shifted = _PAD_CHANNELS[channel]
    suffix = " (+SHIFT)" if shifted else ""
    return ControlInfo(
        "DDJ-REV1",
        "PAD",
        f"Deck {deck} Pad {pad + 1} (PAD MODE {mode + 1}){suffix}",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-REV1",
        plugin_id="pioneer.ddj-rev1",
        manufacturer="Pioneer DJ",
        supported_software=("serato",),
        reference_image="ddj-rev1.png",
        display_order=20,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "PAD"),
    )
)
