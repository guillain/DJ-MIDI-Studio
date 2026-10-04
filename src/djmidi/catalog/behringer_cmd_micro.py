"""Behringer CMD Micro MIDI profile.

Behringer publishes no MIDI message list for this controller (its bundled
Traktor map, controllers/hardware/behringer/CMD-micro/, names the controls but
gives no values). Every value here was captured from the maintainer's own unit,
one dictated button at a time, and cross-checked against their real Traktor
export (data/traktor/cmd-studio-4a.tsi.zip, device "CMD MICRO Mixer").

Everything is on MIDI channel 1. The two decks are not exact copies of each
other: on the left, `1` and `2` are notes 18 and 19 and LOAD A is 20; on the
right, `1` is 34, `2` is 36 and LOAD B is 37 (note 35 is unused, which the
Traktor export confirms). That Traktor export also maps notes 1 and 2, but no
button sent them during the capture, so they are left out.

The jog wheels, pitch and volume faders, crossfader and MAIN/CUE LEVEL knobs
are continuous controls and are left out like everywhere else; so is the
BROWSE knob, a relative encoder without a push switch (CC 50).
"""

from __future__ import annotations

from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register

_NAME = "Behringer CMD Micro"
_CHANNELS = ("1",)


def _button(section: str, name: str, note: int) -> ControlInfo:
    return ControlInfo(_NAME, section, name, "NOTE", _CHANNELS, str(note))


def _deck(deck: str, notes: dict[str, int]) -> list[ControlInfo]:
    # LOAD A / CUE A (and B) already carry their deck letter on the hardware.
    return [
        _button(f"DECK {deck}", label if label.endswith(f" {deck}") else f"Deck {deck} {label}", note)
        for label, note in notes.items()
    ]


_STATIC = [
    *_deck(
        "A",
        {
            "1": 18,
            "2": 19,
            "SYNC": 22,
            "PLAY/PAUSE": 23,
            "CUE": 24,
            "PITCHBEND -": 16,
            "PITCHBEND +": 17,
            "LOAD A": 20,
            "CUE A": 25,
        },
    ),
    *_deck(
        "B",
        {
            "1": 34,
            "2": 36,
            "SYNC": 38,
            "PLAY/PAUSE": 39,
            "CUE": 40,
            "PITCHBEND -": 32,
            "PITCHBEND +": 33,
            "LOAD B": 37,
            "CUE B": 41,
        },
    ),
    _button("BROWSE", "LEFT", 48),
    _button("BROWSE", "RIGHT", 49),
]


register(
    ControllerDefinition(
        name=_NAME,
        plugin_id="behringer.cmd-micro",
        manufacturer="Behringer",
        port_names=("CMD Micro",),
        reference_image="hardware/behringer/CMD-micro/reference.png",
        static_entries=_STATIC,
        section_order=("DECK A", "BROWSE", "DECK B"),
        display_order=71,
    )
)
