"""Behringer CMD Studio 4a MIDI profile.

Behringer publishes no MIDI message list for this controller (its Quick Start
Guide, controllers/hardware/behringer/CMD-studio-4a/, has no MIDI table).
Every value here was captured from the maintainer's own unit, one dictated
button at a time, in all four deck layers, and cross-checked against their
real Traktor export (data/traktor/cmd-studio-4a.tsi.zip, device
"S4A_MAPPING").

Each side switches between two deck layers, and the layer only changes the
MIDI channel, never the note: the left side sends on channel 1 for deck A and
channel 3 for deck C, the right side on channel 2 for deck B and channel 4 for
deck D. The deck-select buttons themselves are the exception, each sending on
its own layer's channel only. The BROWSE buttons send on channel 1 whatever
the layer.

The two sides are not exact copies of each other: the right LOOP arrows are
reversed (55 is right, 56 is left; checked twice on the unit), and the right
HOT CUE DEL sits before pad 1 rather than after pad 4, as printed.

Knobs (BROWSE, FX, EQ, MAIN), faders, the crossfader and the jog wheels are
continuous controls and are left out like everywhere else. None of the knobs
has a push switch.
"""

from __future__ import annotations

from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register

_NAME = "Behringer CMD Studio 4a"
_LEFT = ("1", "3")
_RIGHT = ("2", "4")

# Printed label -> note, per side. Names get an "(A/C)" / "(B/D)" suffix.
_LEFT_NOTES = {
    "FX": {"FX 1 1": 16, "FX 1 2": 17, "FX 1 3": 18, "FX 1 4": 19},
    "LOOP": {"LOOP <": 23, "LOOP >": 24, "LOOP ON/OFF": 25},
    "TRANSPORT": {
        "SCRATCH": 22,
        "LOCK": 27,
        "PITCH BEND -": 32,
        "PITCH BEND +": 33,
        "CUE": 43,
        "PLAY/PAUSE": 44,
        "SYNC": 45,
    },
    "HOT CUE": {**{f"HOT CUE {n}": 33 + n for n in range(1, 9)}, "HOT CUE DEL": 42},
    "MIXER": {
        "LOAD": 80,
        "FX ASSIGN 1": 82,
        "FX ASSIGN 2": 83,
        "KILL HIGH": 96,
        "KILL MID": 97,
        "KILL LOW": 98,
        "PHONES": 106,
    },
}
_RIGHT_NOTES = {
    "FX": {"FX 2 1": 48, "FX 2 2": 49, "FX 2 3": 50, "FX 2 4": 51},
    "LOOP": {"LOOP <": 56, "LOOP >": 55, "LOOP ON/OFF": 57},
    "TRANSPORT": {
        "SCRATCH": 54,
        "LOCK": 59,
        "PITCH BEND -": 64,
        "PITCH BEND +": 65,
        "CUE": 75,
        "PLAY/PAUSE": 76,
        "SYNC": 77,
    },
    "HOT CUE": {**{f"HOT CUE {n}": 65 + n for n in range(1, 9)}, "HOT CUE DEL": 74},
    "MIXER": {
        "LOAD": 81,
        "FX ASSIGN 1": 84,
        "FX ASSIGN 2": 85,
        "KILL HIGH": 99,
        "KILL MID": 100,
        "KILL LOW": 101,
        "PHONES": 107,
    },
}


def _side(notes: dict[str, dict[str, int]], decks: str, channels: tuple[str, ...]) -> list[ControlInfo]:
    return [
        ControlInfo(_NAME, section, f"{label} ({decks})", "NOTE", channels, str(note))
        for section, labels in notes.items()
        for label, note in labels.items()
    ]


_STATIC = [
    *(ControlInfo(_NAME, "BROWSE", label, "NOTE", ("1",), str(note)) for label, note in (("ENTER", 1), ("<", 2), (">", 3))),
    *(
        ControlInfo(_NAME, "DECK SELECT", f"DECK {deck}", "NOTE", (channel,), str(note))
        for deck, channel, note in (("A", "1", 20), ("C", "3", 21), ("B", "2", 52), ("D", "4", 53))
    ),
    *_side(_LEFT_NOTES, "A/C", _LEFT),
    *_side(_RIGHT_NOTES, "B/D", _RIGHT),
]


register(
    ControllerDefinition(
        name=_NAME,
        plugin_id="behringer.cmd-studio-4a",
        manufacturer="Behringer",
        port_names=("Studio 4A",),
        reference_image="hardware/behringer/CMD-studio-4a/reference.png",
        static_entries=_STATIC,
        section_order=("BROWSE", "DECK SELECT", "FX", "LOOP", "TRANSPORT", "HOT CUE", "MIXER"),
        display_order=72,
    )
)
