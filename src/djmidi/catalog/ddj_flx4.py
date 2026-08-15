"""Initial conservative Pioneer DJ DDJ-FLX4 controller profile.

The FLX4 is a two-deck controller whose common MIDI layout follows the
DDJ-400 family: deck buttons use channels 1/2 and the two eight-pad banks use
channels 6/7. The discrete values below are intended for catalog navigation
and assisted mapping only; verify them against the installed firmware with a
hardware capture before using the profile for a production remap.
"""

from __future__ import annotations

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    _parse_midi_note,
    register,
)

_DECK_CHANNELS = ("1", "2")
_PAD_CHANNELS = {"6": 1, "7": 2}

_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-FLX4", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "0"),
    ControlInfo("DDJ-FLX4", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "1"),
    ControlInfo("DDJ-FLX4", "DECK", "SYNC", "NOTE", _DECK_CHANNELS, "2"),
    ControlInfo("DDJ-FLX4", "DECK", "MASTER TEMPO", "NOTE", _DECK_CHANNELS, "3"),
    ControlInfo("DDJ-FLX4", "DECK", "TEMPO RANGE", "NOTE", _DECK_CHANNELS, "4"),
    ControlInfo("DDJ-FLX4", "DECK", "KEYLOCK", "NOTE", _DECK_CHANNELS, "5"),
    ControlInfo("DDJ-FLX4", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "6"),
    ControlInfo("DDJ-FLX4", "DECK", "REVERSE", "NOTE", _DECK_CHANNELS, "7"),
    ControlInfo("DDJ-FLX4", "DECK", "LOOP IN", "NOTE", _DECK_CHANNELS, "10"),
    ControlInfo("DDJ-FLX4", "DECK", "LOOP OUT", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-FLX4", "DECK", "RELOOP/EXIT", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-FLX4", "DECK", "QUANTIZE", "NOTE", _DECK_CHANNELS, "13"),
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
    return ControlInfo(
        "DDJ-FLX4",
        "PAD",
        f"Deck {_PAD_CHANNELS[channel]} Pad {pad + 1} (PAD MODE {mode + 1})",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-FLX4",
        plugin_id="pioneer.ddj-flx4",
        manufacturer="Pioneer DJ",
        supported_software=("rekordbox", "serato"),
        reference_image="ddj-flx4.png",
        display_order=25,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=8,
        section_order=("DECK", "PAD"),
    )
)
