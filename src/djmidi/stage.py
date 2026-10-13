"""Qt-free core of the full-screen Stage Mode (issue #230).

Stage Mode shows only a Controller Emulator and a compact Live Monitor,
large and high-contrast, for reading from a distance on stage. The window
itself lives in ``gui/stage_window.py``; this module holds the parts that
don't need a ``QApplication``: turning a live ``MidiEvent`` into one short,
readable line, and the bounded list of recent lines the compact monitor
shows (newest first), so both can be tested without Qt.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from djmidi import catalog
from djmidi.midi_io import MidiEvent

# How many recent events the compact monitor keeps. Deliberately small: at
# stage font sizes only a handful of lines fit, and older traffic belongs in
# the full Live Monitor dock, not here.
DEFAULT_MAX_LINES = 6

_SEPARATOR = " · "


def hits_for_port(hits: Iterable[catalog.ControlInfo], port: str) -> list[catalog.ControlInfo]:
    """Keep only the catalog hits whose controller name appears in the
    source port's name -- the same disambiguation the Live Monitor log
    applies, since ``catalog.lookup()`` is controller-agnostic and the same
    raw trigger often means something on several registered controllers.
    An unknown port (empty string) keeps every hit."""
    hits = list(hits)
    if not port:
        return hits
    source = port.casefold()
    return [hit for hit in hits if hit.controller.casefold() in source]


def _value_text(event: MidiEvent) -> str:
    if event.event_type == "Note Off":
        return "OFF"
    if event.event_type == "Note On":
        return "ON" if event.data2 not in ("", "0") else "OFF"
    return event.data2


def format_stage_line(event: MidiEvent, hits: Iterable[catalog.ControlInfo] = ()) -> str:
    """One short line for the compact stage monitor: direction, then the
    physical control's name(s) when the catalog knows it, else the raw
    trigger, then the value (ON/OFF for a note, the 0-127 value for a CC).
    The port is left out on purpose -- at stage font sizes it would push
    the control name off the line, and the full Live Monitor keeps it."""
    names: list[str] = []
    for hit in hits_for_port(hits, event.port):
        label = f"{hit.controller} {hit.name}"
        if label not in names:
            names.append(label)
    what = "; ".join(names) or f"Ch {event.channel} {event.event_type} {event.data1}"
    return _SEPARATOR.join((event.direction.upper(), what, _value_text(event)))


class StageLog:
    """Bounded, newest-first list of stage monitor lines."""

    def __init__(self, max_lines: int = DEFAULT_MAX_LINES) -> None:
        if max_lines < 1:
            raise ValueError("max_lines must be at least 1")
        self._lines: deque[str] = deque(maxlen=max_lines)

    @property
    def max_lines(self) -> int:
        return self._lines.maxlen or 0

    def add(self, line: str) -> None:
        self._lines.appendleft(line)

    def lines(self) -> list[str]:
        return list(self._lines)

    def clear(self) -> None:
        self._lines.clear()
