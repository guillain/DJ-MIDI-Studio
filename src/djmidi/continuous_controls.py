"""Names of continuous controls (faders, knobs) that the catalog leaves out.

The catalog only holds discrete press/toggle controls. Set analysis still wants
to say "EQ LOW · Deck 1" rather than "CC 4 · ch 5", so this table names the
continuous controls, transcribed only from official documents:

- XDJ-XZ: Pioneer's MIDI Message List (controllers/hardware/pioneer/XDJ-XZ/
  xdj-xz-midi-message-list-e3.pdf), sections "2, EFFECT" and "3, MIXER"
  (channel 5) and the deck TEMPO slider (channels 1-4, CC 0 MSB / 32 LSB).

- DDJ-XP2: Pioneer's MIDI Message List (controllers/hardware/pioneer/DDJ-XP2/
  ddj-xp2-midi-message-list-e1.pdf): TOUCH STRIP slide (channels 5/6, CC 2-4
  MSB / 34-36 LSB) and the BROWSE knob (channel 7, CC 64).

Rows the document leaves ambiguous (the deck CC 28 printed between LOAD and
NEEDLE POSITION) are not named.
"""

from __future__ import annotations

# (section, name) per (channel, CC number), per controller name.
_XDJ_XZ: dict[tuple[int, int], tuple[str, str]] = {}


def _decks(section: str, name: str, numbers: tuple[int, int, int, int], channel: int = 5) -> None:
    for deck, number in enumerate(numbers, start=1):
        _XDJ_XZ[(channel, number)] = (section, f"{name} · Deck {deck}")


_decks("MIXER", "CH FADER", (17, 18, 19, 20))
_decks("MIXER", "TRIM", (1, 6, 12, 80))
_decks("MIXER", "EQ HIGH", (2, 7, 14, 81))
_decks("MIXER", "EQ MID", (3, 8, 15, 92))
_decks("MIXER", "EQ LOW", (4, 9, 21, 82))
_decks("MIXER", "CROSSFADER ASSIGN", (65, 66, 67, 68))
_decks("MIXER", "CH CUE (Headphone)", (70, 71, 72, 73))
_decks("EFFECT", "COLOR", (5, 10, 22, 83))
_XDJ_XZ.update({
    (5, 11): ("MIXER", "CROSSFADER"),
    (5, 24): ("MIXER", "MASTER LEVEL"),
    (5, 25): ("MIXER", "BOOTH MONITOR LEVEL"),
    (5, 26): ("MIXER", "HEADPHONES LEVEL"),
    (5, 27): ("MIXER", "HEADPHONES MIXING"),
    (5, 47): ("MIXER", "MASTER EQ HI"),
    (5, 48): ("MIXER", "MASTER EQ MID"),
    (5, 49): ("MIXER", "MASTER EQ LOW"),
    (5, 74): ("MIXER", "MASTER CUE (Headphone)"),
    (5, 91): ("EFFECT", "LEVEL DEPTH"),
    (5, 108): ("EFFECT", "PARAMETER"),
})
for _deck in (1, 2, 3, 4):
    _XDJ_XZ[(_deck, 0)] = ("DECK", "TEMPO")
    _XDJ_XZ[(_deck, 32)] = ("DECK", "TEMPO (fine)")

_DDJ_XP2: dict[tuple[int, int], tuple[str, str]] = {(7, 64): ("BROWSE", "BROWSE rotate")}
for _channel in (5, 6):
    for _msb in (2, 3, 4):
        _DDJ_XP2[(_channel, _msb)] = ("EFFECT", "TOUCH STRIP")
        _DDJ_XP2[(_channel, _msb + 32)] = ("EFFECT", "TOUCH STRIP (fine)")

_TABLES: dict[str, dict[tuple[int, int], tuple[str, str]]] = {"XDJ-XZ": _XDJ_XZ, "DDJ-XP2": _DDJ_XP2}


def continuous_name(controller: str | None, channel: int, number: int) -> tuple[str, str] | None:
    """(section, name) of a documented continuous control, or None."""
    return _TABLES.get(controller or "", {}).get((channel, number))


__all__ = ["continuous_name"]
