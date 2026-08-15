"""Initial DDJ-FLX10 controller profile.

This conservative profile covers the discrete deck controls and performance
pad banks used by common Rekordbox/Serato mappings. Continuous controls are
intentionally omitted. Verify the profile against the installed firmware or a
hardware capture before using it for a production remap; no unverified
reference image is declared yet.
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

_STATIC: list[ControlInfo] = [
    ControlInfo("DDJ-FLX10", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "0"),
    ControlInfo("DDJ-FLX10", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "1"),
    ControlInfo("DDJ-FLX10", "DECK", "SYNC", "NOTE", _DECK_CHANNELS, "2"),
    ControlInfo("DDJ-FLX10", "DECK", "MASTER TEMPO", "NOTE", _DECK_CHANNELS, "3"),
    ControlInfo("DDJ-FLX10", "DECK", "TEMPO RANGE", "NOTE", _DECK_CHANNELS, "4"),
    ControlInfo("DDJ-FLX10", "DECK", "KEYLOCK", "NOTE", _DECK_CHANNELS, "5"),
    ControlInfo("DDJ-FLX10", "DECK", "SLIP", "NOTE", _DECK_CHANNELS, "6"),
    ControlInfo("DDJ-FLX10", "DECK", "REVERSE", "NOTE", _DECK_CHANNELS, "7"),
    ControlInfo("DDJ-FLX10", "DECK", "LOOP IN", "NOTE", _DECK_CHANNELS, "10"),
    ControlInfo("DDJ-FLX10", "DECK", "LOOP OUT", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-FLX10", "DECK", "RELOOP/EXIT", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-FLX10", "DECK", "QUANTIZE", "NOTE", _DECK_CHANNELS, "13"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode, pad = divmod(note, 16)
    if mode >= 8:
        return None
    return ControlInfo(
        "DDJ-FLX10",
        "PAD",
        f"Deck {_PAD_CHANNELS[channel]} Pad {pad + 1} (PAD MODE {mode + 1})",
        "NOTE",
        (channel,),
        data1,
    )


register(
    ControllerDefinition(
        name="DDJ-FLX10",
        plugin_id="pioneer.ddj-flx10",
        manufacturer="Pioneer DJ",
        supported_software=("rekordbox", "serato"),
        display_order=35,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=16,
        pad_columns=8,
        section_order=("DECK", "PAD"),
    )
)
