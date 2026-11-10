"""What the Live Monitor log shows (issue #447).

Display only: the monitor, the layouts, captures, macros and the saved log
keep every event; a filter only decides which log rows stay visible.
Qt-free; whether an event is a jog-wheel tick is the caller's knowledge
(`gui/jog.py`), passed in as `is_jog`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from djmidi.midi_io import PITCH_BEND, MidiEvent

NOTES = "notes"
CC = "cc"
BEND = "bend"
KINDS = (NOTES, CC, BEND)
ALL_DIRECTIONS = frozenset({"in", "out"})


def kind_of(event: MidiEvent) -> str:
    if event.event_type in ("Note On", "Note Off"):
        return NOTES
    if event.event_type == "Control Change":
        return CC
    if event.event_type == PITCH_BEND:
        return BEND
    return ""


@dataclass(frozen=True)
class LogFilter:
    """``port`` "" = every port; ``kinds`` and ``directions`` = what stays
    shown; ``hide_jogs`` hides jog-wheel ticks (they stream by the dozen)."""

    port: str = ""
    kinds: frozenset[str] = field(default_factory=lambda: frozenset(KINDS))
    directions: frozenset[str] = ALL_DIRECTIONS
    hide_jogs: bool = False

    @property
    def is_default(self) -> bool:
        return self == LogFilter()

    def accepts(self, event: MidiEvent, is_jog: bool = False) -> bool:
        if self.port and event.port != self.port:
            return False
        if event.direction not in self.directions:
            return False
        kind = kind_of(event)
        if kind and kind not in self.kinds:
            return False
        return not (self.hide_jogs and is_jog)


__all__ = ["BEND", "CC", "KINDS", "NOTES", "LogFilter", "kind_of"]
