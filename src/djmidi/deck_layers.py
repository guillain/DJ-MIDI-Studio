"""Which deck each side of each controller is on (decks 1/3 left, 2/4 right), Qt-free.

A DJ with two controllers on four decks switches each one on its own: the
controller keeps its deck layer itself and Serato follows the channel it
sends on. Nothing tells the DJ when one controller is on deck 3 and the
other still on deck 1. :class:`DeckLayers` reads the messages each
controller sends when it switches and :meth:`DeckLayers.summary` says where
they stand and when they differ.

The messages, never guessed:

- **XDJ-XZ**: SHIFT pressed twice sends CC 102 on the deck channel (official
  MIDI Message List). A real switch, with Serato running (2026-11-27), sent
  CC 102 = 127 on the new deck's channel and 0 on the old one's.
- **DDJ-XP2**: a real switch from deck 1 to 3 and back, with Serato running
  (2026-11-27), sent Note 60 = 127 on the new deck's channel and 0 on the old
  one's; the right side (2/4) does the same on channels 2 and 4 (2026-11-28).

Nothing is sent: neither controller switched when sent its own messages back
(test of 2026-11-28, #550), so the app warns instead (:meth:`DeckLayers.alert`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

LEFT, RIGHT = "left", "right"

# controller -> (event type, number): the message whose value 127 on deck
# channel n says "this side is on deck n".
SWITCH_MESSAGES: dict[str, tuple[str, int]] = {
    "XDJ-XZ": ("Control Change", 102),
    "DDJ-XP2": ("Note On", 60),
}

_SIDE_NAMES = {
    LEFT: QT_TRANSLATE_NOOP("DeckLayers", "left"),
    RIGHT: QT_TRANSLATE_NOOP("DeckLayers", "right"),
}
_LINE = QT_TRANSLATE_NOOP("DeckLayers", "Decks: {controllers}")
_UNSEEN = QT_TRANSLATE_NOOP(
    "DeckLayers", "{first} is on deck {deck} ({side} side): is {second} on deck {deck} too? It hasn't switched since the app started."
)
_ALERT = QT_TRANSLATE_NOOP("DeckLayers", "⚠ {first} on deck {a} · {second} on deck {b}")
_ALERT_UNSEEN = QT_TRANSLATE_NOOP("DeckLayers", "⚠ {first} on deck {a} · {second} too?")
_DIFFER = QT_TRANSLATE_NOOP(
    "DeckLayers", "⚠ {side} side: {first} is on deck {a}, {second} on deck {b}: switch one so both play the same deck."
)


def side_of(deck: int) -> str:
    return LEFT if deck % 2 else RIGHT


def controller_for_port(port: str) -> str:
    """The controller (of SWITCH_MESSAGES) a port name belongs to, "" if none."""
    haystack = (port or "").casefold()
    return next((name for name in SWITCH_MESSAGES if name.casefold() in haystack), "")


@dataclass
class DeckLayers:
    # controller -> side -> deck; a side is absent until its controller switched.
    decks: dict[str, dict[str, int]] = field(default_factory=dict)
    # controllers (of SWITCH_MESSAGES) heard at all
    present: set[str] = field(default_factory=set)

    def feed(self, port: str, direction: str, event_type: str, channel: str, data1: str, data2: str) -> bool:
        """Reads one live event; True when a deck layer changed."""
        controller = controller_for_port(port)
        if not controller or direction != "in":
            return False
        if controller not in self.present:
            self.present.add(controller)
        if (event_type, _int(data1)) != SWITCH_MESSAGES[controller] or _int(data2) != 127:
            return False
        deck = _int(channel)
        if deck not in (1, 2, 3, 4):
            return False
        sides = self.decks.setdefault(controller, {})
        if sides.get(side_of(deck)) == deck:
            return False
        sides[side_of(deck)] = deck
        return True

    def differences(self) -> list[tuple[str, str, int, str, int]]:
        """(side, controller, deck, other controller, its deck) where two
        controllers that both switched say different decks."""
        found = []
        names = sorted(self.decks)
        for side in (LEFT, RIGHT):
            seen = [(name, self.decks[name][side]) for name in names if side in self.decks[name]]
            for (first, a), (second, b) in pairwise(seen):
                if a != b:
                    found.append((side, first, a, second, b))
        return found

    def unseen(self) -> list[tuple[str, str, int, str]]:
        """(side, controller, deck, other controller): a side moved to deck
        3/4 while another controller heard never switched that side."""
        found = []
        for side in (LEFT, RIGHT):
            for name in sorted(self.decks):
                deck = self.decks[name].get(side)
                if deck not in (3, 4):
                    continue
                for other in sorted(self.present - {name}):
                    if side not in self.decks.get(other, {}):
                        found.append((side, name, deck, other))
        return found

    def alert(self, translate: Translate = untranslated) -> str:
        """One short line for a big warning (Stage Mode, over other apps):
        the first side where two controllers differ, "" when none does."""
        for _side, first, a, second, b in self.differences():
            return translate(_ALERT).format(first=first, a=a, second=second, b=b)
        for _side, first, deck, second in self.unseen():
            return translate(_ALERT_UNSEEN).format(first=first, a=deck, second=second)
        return ""

    def summary(self, translate: Translate = untranslated) -> str:
        """One line per state: "" until a controller switched."""
        if not self.decks:
            return ""
        parts = []
        for name in sorted(self.decks):
            sides = self.decks[name]
            parts.append(f"{name} {sides.get(LEFT, '?')} | {sides.get(RIGHT, '?')}")
        lines = [translate(_LINE).format(controllers=" · ".join(parts))]
        for side, first, a, second, b in self.differences():
            lines.append(
                translate(_DIFFER).format(side=translate(_SIDE_NAMES[side]), first=first, a=a, second=second, b=b)
            )
        for side, first, deck, second in self.unseen():
            lines.append(translate(_UNSEEN).format(side=translate(_SIDE_NAMES[side]), first=first, deck=deck, second=second))
        return "\n".join(lines)


def _int(text: object) -> int:
    try:
        return int(str(text))
    except ValueError:
        return -1


__all__ = ["LEFT", "RIGHT", "SWITCH_MESSAGES", "DeckLayers", "controller_for_port", "side_of"]
