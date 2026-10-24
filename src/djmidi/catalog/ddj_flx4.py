"""DDJ-FLX4 controller definition, transcribed from Pioneer's official MIDI
Message List PDF (controllers/hardware/pioneer/DDJ-FLX4/ddj-flx4-midi-message-list-e1.pdf,
Ver 1.0), every table read from a 300 DPI ``pdftoppm`` render.

Replaces an earlier "conservative" community profile (PLAY/PAUSE on note 0,
pads on channels 6/7, plus KEYLOCK/SLIP/REVERSE/QUANTIZE buttons the FLX4
doesn't physically have) that contradicted the official list (issue #338).

Layout per the PDF: deck buttons on channel 1 (deck 1) / 2 (deck 2); the
mixer's browse/load/master-cue/Smart buttons on the shared channel 7; Beat
FX on channel 5 (and 6 for FX ON/OFF when the FX CH SELECT switch targets
CH2); the performance pads on channels 8/9 (deck 1, plain/+SHIFT) and
10/11 (deck 2), ``note = 16 * mode + (pad - 1)`` over eight named modes --
every one of the 256 pad rows checked against that formula.

Same conservative scope as DDJ-800/DDJ-1000: one entry per physical
button's plain press -- its +SHIFT / long-press rows (different Data1 on
the same channel) aren't separate entries. Left out:

- FX CH SELECT (Fig. 2-1): a three-position slide switch sending four NOTE
  messages per position, not one trigger.
- Android MONO/STEREO (3-14): a rear-panel slide switch.
- Jog touch (1-4 Touch): part of the jog wheel, a continuous control
  (its rotation CCs live in ``gui/jog.py``).
- Faders/knobs: continuous, out of catalog scope.
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

_STATIC: list[ControlInfo] = [
    # DECK group (Fig. 1-x), channel 1 = deck 1, 2 = deck 2.
    ControlInfo("DDJ-FLX4", "DECK", "PLAY/PAUSE", "NOTE", _DECK_CHANNELS, "11"),
    ControlInfo("DDJ-FLX4", "DECK", "CUE", "NOTE", _DECK_CHANNELS, "12"),
    ControlInfo("DDJ-FLX4", "DECK", "SHIFT", "NOTE", _DECK_CHANNELS, "63"),
    ControlInfo("DDJ-FLX4", "DECK", "IN", "NOTE", _DECK_CHANNELS, "16"),
    ControlInfo("DDJ-FLX4", "DECK", "OUT", "NOTE", _DECK_CHANNELS, "17"),
    ControlInfo("DDJ-FLX4", "DECK", "4 BEAT/EXIT", "NOTE", _DECK_CHANNELS, "77"),
    ControlInfo("DDJ-FLX4", "DECK", "CUE/LOOP CALL <", "NOTE", _DECK_CHANNELS, "81"),
    ControlInfo("DDJ-FLX4", "DECK", "CUE/LOOP CALL >", "NOTE", _DECK_CHANNELS, "83"),
    # The PDF's footnote *3: BEAT SYNC sends on release, not on press.
    ControlInfo("DDJ-FLX4", "DECK", "BEAT SYNC", "NOTE", _DECK_CHANNELS, "88"),
    # Pad-mode select buttons (Fig. 5-1..5-4). Their +SHIFT rows (105/107/
    # 109/111) select KEYBOARD / PAD FX 2 / BEAT LOOP / KEY SHIFT.
    ControlInfo("DDJ-FLX4", "DECK", "HOT CUE MODE", "NOTE", _DECK_CHANNELS, "27"),
    ControlInfo("DDJ-FLX4", "DECK", "PAD FX 1 MODE", "NOTE", _DECK_CHANNELS, "30"),
    ControlInfo("DDJ-FLX4", "DECK", "BEAT JUMP MODE", "NOTE", _DECK_CHANNELS, "32"),
    ControlInfo("DDJ-FLX4", "DECK", "SAMPLER MODE", "NOTE", _DECK_CHANNELS, "34"),
    # BROWSE group (Fig. 4-x), channel 7.
    ControlInfo("DDJ-FLX4", "BROWSE", "BROWSE", "NOTE", ("7",), "65"),
    ControlInfo("DDJ-FLX4", "BROWSE", "LOAD DECK 1", "NOTE", ("7",), "70"),
    ControlInfo("DDJ-FLX4", "BROWSE", "LOAD DECK 2", "NOTE", ("7",), "71"),
    # EFFECT group (Fig. 2-x).
    ControlInfo("DDJ-FLX4", "EFFECT", "FX SELECT", "NOTE", ("5",), "99"),
    ControlInfo("DDJ-FLX4", "EFFECT", "BEAT <", "NOTE", ("5",), "74"),
    ControlInfo("DDJ-FLX4", "EFFECT", "BEAT >", "NOTE", ("5",), "75"),
    # Channel 5 when FX CH SELECT is on CH1 or CH1&CH2, channel 6 on CH2.
    ControlInfo("DDJ-FLX4", "EFFECT", "FX ON/OFF", "NOTE", ("5", "6"), "71"),
    # MIXER group (Fig. 3-x).
    ControlInfo("DDJ-FLX4", "MIXER", "CH CUE", "NOTE", _DECK_CHANNELS, "84"),
    ControlInfo("DDJ-FLX4", "MIXER", "MASTER CUE", "NOTE", ("7",), "99"),
    ControlInfo("DDJ-FLX4", "MIXER", "SMART CFX", "NOTE", ("7",), "0"),
    ControlInfo("DDJ-FLX4", "MIXER", "SMART FADER", "NOTE", ("7",), "1"),
]

# Row order of the PDF's PERFORMANCE PAD tables (Fig. 5-5); the last four
# are the SHIFT + pad-mode-button modes.
_PAD_MODE_NAMES = (
    "HOT CUE",
    "PAD FX 1",
    "BEAT JUMP",
    "SAMPLER",
    "KEYBOARD",
    "PAD FX 2",
    "BEAT LOOP",
    "KEY SHIFT",
)

# channel -> (deck, is_shifted): SHIFT moves a pad hit to the next channel
# with the same note, like DDJ-800/DDJ-1000/DDJ-FLX10.
_PAD_CHANNELS = {
    "8": (1, False),
    "9": (1, True),
    "10": (2, False),
    "11": (2, True),
}


def _pad_lookup(channel: str, kind: NoteOrCC, data1: str) -> ControlInfo | None:
    if kind != "NOTE" or channel not in _PAD_CHANNELS:
        return None
    note = _parse_midi_note(data1)
    if note is None:
        return None
    mode, pad = divmod(note, 16)
    if mode >= len(_PAD_MODE_NAMES) or pad >= 8:
        return None
    deck, shifted = _PAD_CHANNELS[channel]
    suffix = " (+SHIFT)" if shifted else ""
    return ControlInfo(
        "DDJ-FLX4",
        "PAD",
        f"Deck {deck} Pad {pad + 1} ({_PAD_MODE_NAMES[mode]}){suffix}",
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
        reference_image="hardware/pioneer/DDJ-FLX4/reference.png",
        display_order=25,
        static_entries=_STATIC,
        pad_lookup=_pad_lookup,
        pad_count=8,
        pad_columns=4,
        section_order=("DECK", "BROWSE", "EFFECT", "MIXER", "PAD"),
    )
)
