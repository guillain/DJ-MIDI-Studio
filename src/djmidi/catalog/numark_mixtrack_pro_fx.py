"""Numark Mixtrack Pro FX MIDI profile.

Numark publishes no MIDI message list for this controller. The values below
come from the Mixxx project's maintained mapping for it (Mixxx 2.5
``res/controllers/Numark Mixtrack Pro FX.midi.xml`` and its
``Numark-Mixtrack-Pro-FX-scripts.js``, read in place; issue #372): a working,
community-maintained mapping for this exact device -- still not vendor
documentation, and not yet checked on a unit here. They replace the earlier
"conservative community values", which Mixxx's mapping contradicts (pads on
notes 36-43 of the deck channels, a LOOP button on note 3).

- Deck buttons on channel 1 (deck 1) / 2 (deck 2). SHIFT sends other notes:
  PLAY 0 -> 4, CUE 1 -> 5, SYNC 2 -> 3, SCRATCH 7 -> 8, pitch bend up/down
  11/12 -> 43/44 (the script's ``shiftOffset`` values).
- The loop buttons, the pad-mode buttons and the 8 pads on channel 5
  (deck 1) / 6 (deck 2). Pads send notes 20-27, +8 with SHIFT; the pad
  *mode* is kept by the software (the mode buttons only tell it which), so a
  pad's note doesn't change with the mode.
- LOAD on channel 16, note 2 (deck 1) / 3 (deck 2).

Continuous controls (faders, knobs, jogs, the browse encoder) stay out, as
for every profile; the browse encoder's push is left out too, since which
of its two notes is the SHIFT layer isn't clear from the mapping.
"""

from __future__ import annotations

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    register,
)

_NAME = "Numark Mixtrack Pro FX"
_DECK_CHANNELS = ("1", "2")
_PAD_CHANNELS = ("5", "6")
_PAD_NOTES = range(20, 28)
_SHIFT_OFFSET = 8


def _entries(section: str, channels: tuple[str, ...], rows: tuple[tuple[str, int], ...]) -> list[ControlInfo]:
    return [ControlInfo(_NAME, section, name, "NOTE", channels, str(note)) for name, note in rows]


_STATIC = [
    *_entries(
        "DECK",
        _DECK_CHANNELS,
        (
            ("PLAY/PAUSE", 0),
            ("PLAY/PAUSE +SHIFT", 4),
            ("CUE", 1),
            ("CUE +SHIFT", 5),
            ("SYNC", 2),
            ("SYNC +SHIFT", 3),
            ("SHIFT", 32),
            ("PFL", 27),
            ("SCRATCH", 7),
            ("SCRATCH +SHIFT", 8),
            ("PITCH BEND UP", 11),
            ("PITCH BEND UP +SHIFT", 43),
            ("PITCH BEND DOWN", 12),
            ("PITCH BEND DOWN +SHIFT", 44),
        ),
    ),
    *_entries(
        "LOOP",
        _PAD_CHANNELS,
        (
            ("LOOP", 64),
            ("LOOP +SHIFT", 65),
            ("LOOP HALF", 52),
            ("LOOP HALF +SHIFT", 54),
            ("LOOP DOUBLE", 53),
            ("LOOP DOUBLE +SHIFT", 55),
        ),
    ),
    # Mixxx's PadModeControls; BEAT JUMP and SAMPLE 2 are the mode buttons'
    # SHIFT layer there ("shifted leds" in its script).
    *_entries(
        "PAD MODE",
        _PAD_CHANNELS,
        (
            ("HOT CUE", 0),
            ("AUTO LOOP", 13),
            ("FADER CUTS", 7),
            ("SAMPLE", 11),
            ("BEAT JUMP", 2),
            ("SAMPLE 2", 15),
        ),
    ),
    ControlInfo(_NAME, "BROWSE", "LOAD DECK 1", "NOTE", ("16",), "2"),
    ControlInfo(_NAME, "BROWSE", "LOAD DECK 2", "NOTE", ("16",), "3"),
]


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    try:
        note = int(data1)
    except ValueError:
        return None
    shifted = note - _SHIFT_OFFSET in _PAD_NOTES
    if note not in _PAD_NOTES and not shifted:
        return None
    pad = (note - _SHIFT_OFFSET if shifted else note) - _PAD_NOTES.start + 1
    deck = _PAD_CHANNELS.index(channel) + 1
    name = f"Deck {deck} Pad {pad}" + (" +SHIFT" if shifted else "")
    return ControlInfo(_NAME, "PAD", name, "NOTE", (channel,), data1)


register(
    ControllerDefinition(
        name=_NAME,
        plugin_id="numark.mixtrack-pro-fx",
        manufacturer="Numark",
        supported_software=("serato", "virtualdj"),
        reference_image="hardware/numark/Mixtrack-Pro-FX/reference.png",
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=8,
        section_order=("DECK", "LOOP", "PAD MODE", "BROWSE", "PAD"),
        display_order=40,
    )
)
