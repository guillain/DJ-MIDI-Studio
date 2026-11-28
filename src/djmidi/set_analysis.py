"""What a recorded live set says about how the DJ plays (Qt-free).

Reads a recording (`session_recorder`, or the standalone ``live_rec.py``
format with raw ``bytes``) and counts: button presses per physical control
(named by the catalog, restricted to the controller the port names), the
continuous controls that moved (knobs, faders, jogs), the presses that
follow each other within :data:`SEQUENCE_GAP_S`, and the presses per slice
of :data:`ACTIVITY_SLICE_S`. Nothing here guesses a name: a message no
profile knows keeps its raw "channel / number" label.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from djmidi import catalog
from djmidi.atelier.describe import controller_for_port
from djmidi.continuous_controls import continuous_name
from djmidi.gui.jog import jog_cell_keys_for_event  # Qt-free tables
from djmidi.session_recorder import read_recording

SEQUENCE_GAP_S = 1.5
ACTIVITY_SLICE_S = 600
NOTE, CC, BEND = "note", "cc", "bend"


@dataclass(frozen=True)
class SetEvent:
    t: float
    port: str
    kind: str  # NOTE (a press: velocity > 0), CC or BEND; releases are dropped
    channel: int
    number: int
    value: int


@dataclass(frozen=True)
class ControlKey:
    port: str
    kind: str
    channel: int
    number: int


@dataclass
class SetAnalysis:
    duration_s: float = 0.0
    events: int = 0
    presses: int = 0
    ports: Counter = field(default_factory=Counter)
    buttons: list[tuple[ControlKey, str, int]] = field(default_factory=list)
    continuous: list[tuple[ControlKey, str, int]] = field(default_factory=list)
    sequences: list[tuple[str, str, int]] = field(default_factory=list)
    activity: list[int] = field(default_factory=list)
    unnamed_presses: int = 0


def _event_from_row(row: dict) -> SetEvent | None:
    """One recording row as a SetEvent, or None for a release, a message type
    not analysed, or a malformed row."""
    try:
        t = float(row["t"])
        port = str(row.get("port", row.get("p", "")))
        raw = row.get("bytes", row.get("b"))  # standalone recorders: raw MIDI bytes
        if raw is not None:
            if row.get("dir", "in") != "in":
                return None
            status, number, value = (list(raw) + [0, 0])[:3]
            high, channel = status & 0xF0, (status & 0x0F) + 1
            kind = {0x90: NOTE, 0xB0: CC, 0xE0: BEND}.get(high)
            if kind == BEND:
                number, value = 0, number | (value << 7)
        else:
            kind = {"Note On": NOTE, "Control Change": CC, "Pitch Bend": BEND}.get(str(row.get("type")))
            channel, number, value = int(row["ch"]), int(row["d1"]), int(row["d2"])
            if row.get("dir", "in") != "in":
                return None
    except (KeyError, TypeError, ValueError):
        return None
    if kind is None or (kind == NOTE and value == 0):
        return None
    return SetEvent(t, port, kind, int(channel), int(number), int(value))


def load_set(path: str | Path) -> list[SetEvent]:
    return [event for row in read_recording(Path(path)) if (event := _event_from_row(row)) is not None]


def _controller(port: str) -> str | None:
    exact = controller_for_port(port)
    if exact is not None:
        return exact
    matches = catalog.detect_controller(port, include_disabled=True)
    return matches[0].controller.name if matches and matches[0].score > 0 else None


class _Namer:
    def __init__(self) -> None:
        self._controllers: dict[str, str | None] = {}
        self._names: dict[ControlKey, str] = {}

    def __call__(self, key: ControlKey) -> str:
        name = self._names.get(key)
        if name is None:
            name = self._names[key] = self._name(key)
        return name

    def _name(self, key: ControlKey) -> str:
        if key.kind == BEND:
            return f"Pitch bend · ch {key.channel}"
        if key.port not in self._controllers:
            self._controllers[key.port] = _controller(key.port)
        controller = self._controllers[key.port]
        event_type = "Note On" if key.kind == NOTE else "Control Change"
        if key.kind == CC:
            jogs = [cell for cell in jog_cell_keys_for_event(str(key.channel), event_type, str(key.number))
                    if controller is None or cell[0] == controller]
            if jogs:
                return f"{jogs[0][1]} · {jogs[0][2]} · ch {key.channel}"
            named = continuous_name(controller, key.channel, key.number)
            if named is not None:
                return f"{named[0]} · {named[1]} · ch {key.channel}"
        hits = catalog.lookup(str(key.channel), event_type, str(key.number))
        if controller is not None:
            hits = [hit for hit in hits if hit.controller == controller]
        if hits:
            # The channel tells the decks apart (deck 1 and 2's CUE share a note).
            return f"{hits[0].section} · {hits[0].name} · ch {key.channel}"
        return f"{'Note' if key.kind == NOTE else 'CC'} {key.number} · ch {key.channel}"  # no profile names it

    def known(self, key: ControlKey) -> bool:
        return not self(key).startswith(("Note ", "CC "))


def analyse(events: Iterable[SetEvent], limit: int = 50) -> SetAnalysis:
    events = sorted(events, key=lambda event: event.t)
    result = SetAnalysis()
    if not events:
        return result
    namer = _Namer()
    start = events[0].t
    result.duration_s = events[-1].t - start
    result.events = len(events)
    buttons: Counter = Counter()
    continuous: Counter = Counter()
    pairs: Counter = Counter()
    activity: Counter = Counter()
    previous: tuple[float, ControlKey] | None = None
    for event in events:
        key = ControlKey(event.port, event.kind, event.channel, event.number)
        result.ports[event.port] += 1
        if event.kind != NOTE:
            continuous[key] += 1
            continue
        buttons[key] += 1
        activity[int((event.t - start) // ACTIVITY_SLICE_S)] += 1
        if previous is not None and previous[1] != key and event.t - previous[0] <= SEQUENCE_GAP_S:
            pairs[(previous[1], key)] += 1
        previous = (event.t, key)
    result.presses = sum(buttons.values())
    result.unnamed_presses = sum(count for key, count in buttons.items() if not namer.known(key))
    result.buttons = [(key, namer(key), count) for key, count in buttons.most_common(limit)]
    result.continuous = [(key, namer(key), count) for key, count in continuous.most_common(limit)]
    result.sequences = [
        (f"{namer(a)} ({a.port})", f"{namer(b)} ({b.port})", count) for (a, b), count in pairs.most_common(limit)
    ]
    slices = int(result.duration_s // ACTIVITY_SLICE_S) + 1
    result.activity = [activity.get(index, 0) for index in range(slices)]
    return result


__all__ = ["ACTIVITY_SLICE_S", "SEQUENCE_GAP_S", "ControlKey", "SetAnalysis", "SetEvent", "analyse", "load_set"]
