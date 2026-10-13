"""Hercules DJControl Inpulse 500 MIDI profile.

Transcribed from the official "MIDI COMMANDS" sheet bundled at
``controllers/hardware/hercules/DJControl-Inpulse-500/
hercules-djcontrol-inpulse-500-product-sheet-fr.pdf`` (Guillemot, 2022),
every page read from a 300 DPI ``pdftoppm`` render (issue #247). The
previous, community-sourced profile (deck buttons on notes 10-13 and pads
on notes 40-47 of channels 1/2) contradicted that sheet and was replaced.

The sheet's "Channel" column is 0-based -- its own status bytes say so
(Play on deck 1 is "1 / 7" next to "91 07") -- so every channel below is
that column + 1, matching ``model.Control``'s 1-indexed convention:

- channel 1 (0x90): mixer/browser buttons, channel 4 (0x93) their SHIFT layer;
- channel 2/3 (0x91/0x92): deck 1/2 buttons, channel 5/6 (0x94/0x95) SHIFT;
- channel 7/8 (0x96/0x97): deck 1/2 pads, note = 16 * (mode - 1) + (pad - 1),
  +8 on the SHIFT layer -- one bank of 16 notes per pad mode, 8 modes.

Only discrete press/toggle controls are listed (catalog scope): jog wheels,
faders, knobs, the Autoloop/Browse encoder turns and output-only backlights
are left out. Rows the sheet contradicts itself on are dropped rather than
guessed (see ``docs/enduser/controller-profiles.md``):

- "Guides" (M-6) and "Assistant" (B4) are both printed as 0x90 note 1;
- deck 2 "Mode 4A" (long press) says channel 2 but status 0x91 (deck 1's);
- "Load 2" +SHIFT says channel 4 but status 0x95.

The pad addressing is exposed as :func:`pad_trigger` so the pad-colour
palette (``djmidi/pad_colours.py``, whose LED notes the sheet prints equal
to the pads' input notes) derives from this module instead of keeping a
second copy of the formula.
"""

from __future__ import annotations

from djmidi.catalog._registry import (
    ControlInfo,
    ControllerDefinition,
    NoteOrCC,
    _parse_midi_note,
    register,
)

CONTROLLER = "Hercules DJControl Inpulse 500"
DECKS = 2
PADS = 8
PAD_MODES = 8

_GLOBAL = ("1",)
_GLOBAL_SHIFT = ("4",)
_DECK = ("2", "3")
_DECK_SHIFT = ("5", "6")
_PAD_CHANNELS = {"7": 1, "8": 2}
_SHIFT_OFFSET = 8
_NOTES_PER_MODE = 16


def _entry(section: str, name: str, channels: tuple[str, ...], note: int) -> ControlInfo:
    return ControlInfo(CONTROLLER, section, name, "NOTE", channels, str(note))


def _with_shift(section: str, name: str, note: int, plain: tuple[str, ...], shift: tuple[str, ...]) -> list[ControlInfo]:
    return [_entry(section, name, plain, note), _entry(section, f"{name} (+SHIFT)", shift, note)]


_STATIC = [
    # DECK 1 / DECK 2 (sheet pages 1-2 and 10-11, D1-x / D2-x).
    *_with_shift("DECK", "PLAY/PAUSE", 7, _DECK, _DECK_SHIFT),
    *_with_shift("DECK", "CUE", 6, _DECK, _DECK_SHIFT),
    _entry("DECK", "SHIFT", _DECK, 4),
    *_with_shift("DECK", "LOOP IN", 9, _DECK, _DECK_SHIFT),
    _entry("DECK", "LOOP IN (long press)", _DECK, 11),
    *_with_shift("DECK", "LOOP OUT", 10, _DECK, _DECK_SHIFT),
    _entry("DECK", "AUTOLOOP (press)", _DECK, 44),
    _entry("DECK", "AUTOLOOP (+SHIFT press)", _DECK_SHIFT, 44),
    *_with_shift("DECK", "SYNC", 5, _DECK, _DECK_SHIFT),
    *_with_shift("DECK", "VINYL", 3, _DECK, _DECK_SHIFT),
    *_with_shift("DECK", "SLIP", 1, _DECK, _DECK_SHIFT),
    *_with_shift("DECK", "QUANTIZE", 2, _DECK, _DECK_SHIFT),
    # PADS DECK 1 / 2 mode buttons (P1-1..P1-4 / P2-1..P2-4): each button
    # selects mode N alone and mode N+4 with SHIFT (still on the deck
    # channel), plus a long-press note.
    *(_entry("PAD MODE", f"PAD MODE {mode}", _DECK, 14 + mode) for mode in range(1, PAD_MODES + 1)),
    _entry("PAD MODE", "PAD MODE 1 (long press)", _DECK, 64),
    _entry("PAD MODE", "PAD MODE 2 (long press)", _DECK, 65),
    _entry("PAD MODE", "PAD MODE 3 (long press)", _DECK, 66),
    _entry("PAD MODE", "PAD MODE 4 (long press)", ("2",), 67),  # deck 2's row is self-contradictory
    # MIXER (pages 5-7).
    *_with_shift("MIXER", "DECK 1 PFL", 12, ("2",), ("5",)),
    *_with_shift("MIXER", "DECK 2 PFL", 12, ("3",), ("6",)),
    *_with_shift("MIXER", "MASTER PFL", 2, _GLOBAL, _GLOBAL_SHIFT),
    _entry("MIXER", "XFADER CURVE ON/OFF", _GLOBAL, 24),
    *(
        entry
        for number in range(1, 5)
        for entry in _with_shift("FX", f"FX {number}", 19 + number, _GLOBAL, _GLOBAL_SHIFT)
    ),
    # BROWSER (page 8).
    _entry("BROWSER", "BROWSE (press)", _GLOBAL, 0),
    _entry("BROWSER", "BROWSE (+SHIFT press)", _GLOBAL_SHIFT, 0),
    *_with_shift("BROWSER", "LOAD DECK 1", 13, ("2",), ("5",)),
    _entry("BROWSER", "LOAD DECK 1 (long press)", ("2",), 14),
    _entry("BROWSER", "LOAD DECK 2", ("3",), 13),
    _entry("BROWSER", "LOAD DECK 2 (long press)", ("3",), 14),
]


def pad_trigger(deck: int, pad: int, mode: int = 1, shift: bool = False) -> tuple[int, int]:
    """``(1-based MIDI channel, note)`` of a pad, per the sheet's pad tables
    (pages 2-4 for deck 1, 11-14 for deck 2). The pad's LED listens on the
    same address ("MIDI OUT" repeats "MIDI IN" there)."""
    if not (1 <= deck <= DECKS and 1 <= pad <= PADS and 1 <= mode <= PAD_MODES):
        raise ValueError(f"{CONTROLLER} has no deck {deck} pad {pad} mode {mode}")
    note = _NOTES_PER_MODE * (mode - 1) + (pad - 1) + (_SHIFT_OFFSET if shift else 0)
    return 6 + deck, note


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode_index, offset = divmod(note, _NOTES_PER_MODE)
    shift, pad_index = divmod(offset, _SHIFT_OFFSET)
    suffix = " +SHIFT" if shift else ""
    name = f"Deck {_PAD_CHANNELS[channel]} Pad {pad_index + 1} (PAD MODE {mode_index + 1}){suffix}"
    return ControlInfo(CONTROLLER, "PAD", name, "NOTE", (channel,), data1)


register(
    ControllerDefinition(
        name=CONTROLLER,
        plugin_id="hercules.djcontrol-inpulse-500",
        manufacturer="Hercules",
        supported_software=("serato", "virtualdj"),
        reference_image="hardware/hercules/DJControl-Inpulse-500/reference.png",
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=PADS,
        pad_columns=4,
        section_order=("DECK", "PAD MODE", "PAD", "MIXER", "FX", "BROWSER"),
        display_order=50,
    )
)
