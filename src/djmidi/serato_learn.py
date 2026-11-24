"""Teach Serato the notes this app sends on a virtual bus (IAC on macOS).

Macros and scenes that drive Serato through a virtual port only work once
Serato has MIDI-learned the notes they send. This is the guided list the
Tests → Serato MIDI Learn window walks through: one step per Serato function,
each a distinct Note On on its own channel/note. The notes are the ones the
maintainer's learn session used (``data/serato/serato-5.1-iac-learn.xml.zip``
is what Serato saved from them), so a learned file reads the same way.

Qt-free: the dialog sends each step and listens for it coming back on the bus
(a macOS IAC bus echoes what it receives to its input).
"""

from __future__ import annotations

from dataclasses import dataclass

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

COUNTDOWN_S = 5  # time to click the function in Serato before the note leaves
NOTE_LENGTH_MS = 150


@dataclass(frozen=True)
class LearnStep:
    deck: int  # 1-based
    function: str  # English, marked for translation (context "SeratoLearn")
    channel: int  # 1-based
    note: int
    number: int = 0  # hot cue number, 0 for none

    def label(self, translate: Translate = untranslated) -> str:
        name = translate(self.function)
        if self.number:
            name = name.format(number=self.number)
        return translate(QT_TRANSLATE_NOOP("SeratoLearn", "Deck {deck} · {function}")).format(
            deck=self.deck, function=name
        )


_PLAY = QT_TRANSLATE_NOOP("SeratoLearn", "PLAY")
_CUE = QT_TRANSLATE_NOOP("SeratoLearn", "CUE")
_SYNC = QT_TRANSLATE_NOOP("SeratoLearn", "SYNC")
_HOT_CUE = QT_TRANSLATE_NOOP("SeratoLearn", "HOT CUE {number}")

STEPS: tuple[LearnStep, ...] = (
    LearnStep(1, _PLAY, 1, 0),
    LearnStep(1, _CUE, 1, 1),
    LearnStep(1, _SYNC, 1, 2),
    LearnStep(2, _PLAY, 2, 0),
    LearnStep(2, _CUE, 2, 1),
    LearnStep(2, _SYNC, 2, 2),
    *(LearnStep(1, _HOT_CUE, 1, 9 + n, n) for n in range(1, 9)),
)


def default_port(outputs: list[str]) -> str:
    """The virtual bus to teach Serato on: an IAC bus first, else ""."""
    for name in outputs:
        if "iac" in name.casefold():
            return name
    return ""


def is_echo(step: LearnStep, event, port: str) -> bool:
    """A live event is this step's note coming back through the bus `port`."""
    return (
        getattr(event, "direction", "in") == "in"
        and getattr(event, "port", "") == port
        and getattr(event, "event_type", "") == "Note On"
        and str(getattr(event, "channel", "")) == str(step.channel)
        and str(getattr(event, "data1", "")) == str(step.note)
        and str(getattr(event, "data2", "0")) != "0"
    )


__all__ = ["COUNTDOWN_S", "NOTE_LENGTH_MS", "STEPS", "LearnStep", "default_port", "is_echo"]
