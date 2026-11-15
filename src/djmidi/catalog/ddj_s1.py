"""Pioneer DDJ-S1 (Serato DJ Edition) controller definition.

Pioneer's "List of MIDI Messages" for the DDJ-S1 is no longer online (the
manual's pioneerdj.com/support link and the old software-info PDF paths all
redirect to the AlphaTheta support home). Every MIDI value here therefore
comes from a real capture of a real unit made with Controller Setup's live
learning (data/controllers/ddj_s1.json: 96 learned rows, each backed by the
recorded events in the same file). Control names follow the printed panel
and the owner's manual (controllers/hardware/pioneer/DDJ-S1/
DDJ-S1_DRI1137A_manual.pdf, French edition): the capture's "RecMode" is the
button printed REC MODE under the hot cues, "Rev" is CENSOR (printed REV),
"BtVinyl" is VINYL (JOG MODE), "MasterTempo" is MASTER TEMPO (the manual's
KEY LOCK), "Select-Loop" is LOOP SELECT, "SizeLoop-Push" is the AUTO LOOP
knob's push, "AreaMove/Rec" is AREA MOVE (REC), "BTCrate"/"BTFiles" are
CRATES/FILES and "Browse-Bt" the BROWSE knob's push.

Layout: deck buttons on channel 1 (deck A, left) / 2 (deck B, right) with
the same notes; FX1 on channel 3, FX2 on channel 4; browser and mixer
buttons on channel 5.

Same scope as the other Pioneer profiles: one entry per button's plain
press. Not captured, so not listed: SHIFT and every SHIFT layer, the two
headphone CUE buttons. Left out as continuous controls: jog wheels (and the
jog touch, note 54), NEEDLE SEARCH strips, knobs, faders, the FADER START /
C.F.REV / crossfader-curve switches (CC on channel 5).
"""

from __future__ import annotations

from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register

_NAME = "DDJ-S1"
_DECKS = ("1", "2")
_FX = ("3", "4")
_BROWSER = ("5",)


def _entry(section: str, name: str, channels: tuple[str, ...], note: int) -> ControlInfo:
    return ControlInfo(_NAME, section, name, "NOTE", channels, str(note))


_STATIC: list[ControlInfo] = [
    _entry("DECK", "PLAY/PAUSE", _DECKS, 11),
    _entry("DECK", "CUE", _DECKS, 12),
    _entry("DECK", "LOOP IN", _DECKS, 16),
    _entry("DECK", "LOOP OUT", _DECKS, 17),
    _entry("DECK", "RELOOP/EXIT", _DECKS, 18),
    _entry("DECK", "AUTO LOOP", _DECKS, 20),
    _entry("DECK", "LOOP SELECT", _DECKS, 21),
    _entry("DECK", "TEMPO RANGE", _DECKS, 25),
    _entry("DECK", "MASTER TEMPO", _DECKS, 26),
    _entry("DECK", "SYNC", _DECKS, 27),
    _entry("DECK", "VINYL", _DECKS, 53),
    _entry("DECK", "CENSOR", _DECKS, 56),
    _entry("DECK", "LOAD", _DECKS, 61),
    _entry("DECK", "SLIP", _DECKS, 64),
    *(_entry("HOT CUE", f"HOT CUE {n}", _DECKS, 41 + n) for n in range(1, 6)),
    _entry("HOT CUE", "REC MODE", _DECKS, 47),
    _entry("EFFECT", "FX ON/OFF", _FX, 64),
    _entry("EFFECT", "TAP", _FX, 65),
    _entry("BROWSE", "BROWSE (push)", _BROWSER, 65),
    _entry("BROWSE", "BACK", _BROWSER, 66),
    _entry("BROWSE", "AREA MOVE", _BROWSER, 67),
    _entry("BROWSE", "LOAD PREPARE", _BROWSER, 68),
    _entry("BROWSE", "CRATES", _BROWSER, 69),
    _entry("BROWSE", "FILES", _BROWSER, 70),
    _entry("BROWSE", "BROWSE", _BROWSER, 71),
    _entry("BROWSE", "PREPARE", _BROWSER, 72),
]


register(
    ControllerDefinition(
        name=_NAME,
        plugin_id="pioneer.ddj-s1",
        manufacturer="Pioneer DJ",
        supported_software=("serato",),
        port_names=("PIONEER DDJ-S1",),
        reference_image="hardware/pioneer/DDJ-S1/reference.png",
        display_order=26,
        static_entries=_STATIC,
        section_order=("DECK", "HOT CUE", "EFFECT", "BROWSE"),
    )
)
