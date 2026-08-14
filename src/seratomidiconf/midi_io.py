"""Real-time MIDI I/O for the Live Monitor tab.

Polled, not callback-based: mido/rtmidi callbacks fire on a librtmidi-owned
thread, which would need careful marshalling back to the Qt main thread.
Instead, MidiMonitor.poll() is meant to be called from a Qt QTimer on the
main thread and drains whatever arrived via mido's non-blocking
iter_pending() — simple, thread-safe by construction, and more than fast
enough for a visual monitor (no hard real-time requirement here).

MidiEvent's channel/event_type/data1 fields deliberately match the string
format of model.Control (1-indexed decimal channel, "Note On"/"Note Off"/
"Control Change", decimal data1) so a live event can be passed straight into
catalog.lookup() without any translation at the call site.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import mido

Direction = Literal["in", "out"]

_TYPE_TO_EVENT_TYPE = {
    "note_on": "Note On",
    "note_off": "Note Off",
    "control_change": "Control Change",
}


@dataclass(frozen=True)
class MidiEvent:
    direction: Direction
    channel: str
    event_type: str
    data1: str
    data2: str
    timestamp: float
    port: str = ""


def mido_message_to_event(
    msg: mido.Message, direction: Direction, timestamp: float | None = None, port: str = ""
) -> MidiEvent | None:
    """Converts a mido Message to a MidiEvent, or None for message types this
    tool doesn't map (clock, sysex, pitchwheel, ...) — only the note/CC
    triggers a Serato MIDI mapping can actually bind to are meaningful here."""
    event_type = _TYPE_TO_EVENT_TYPE.get(msg.type)
    if event_type is None:
        return None
    channel = str(msg.channel + 1)  # mido is 0-indexed; our model/catalog are 1-indexed
    if msg.type in ("note_on", "note_off"):
        data1, data2 = str(msg.note), str(msg.velocity)
    else:  # control_change
        data1, data2 = str(msg.control), str(msg.value)
    return MidiEvent(
        direction=direction,
        channel=channel,
        event_type=event_type,
        data1=data1,
        data2=data2,
        timestamp=timestamp if timestamp is not None else time.monotonic(),
        port=port,
    )


def list_input_ports() -> list[str]:
    return mido.get_input_names()


class MidiMonitor:
    """Owns zero or more open MIDI input ports (real device sources) plus an
    optional virtual destination this app creates so Serato's *output* can be
    routed to it (see README/CLAUDE.md — this requires the user to manually
    add it as an extra MIDI output in Serato, CoreMIDI doesn't let a third
    app silently see what another app sends to a hardware destination)."""

    VIRTUAL_MONITOR_NAME = "SeratoMidiConf Monitor"

    def __init__(self) -> None:
        self._input_ports: dict[str, mido.ports.BaseInput] = {}
        self._virtual_port: mido.ports.BaseInput | None = None

    def open_input(self, name: str) -> None:
        if name in self._input_ports:
            return
        self._input_ports[name] = mido.open_input(name)

    def close_input(self, name: str) -> None:
        port = self._input_ports.pop(name, None)
        if port is not None:
            port.close()

    def open_virtual_monitor(self) -> None:
        if self._virtual_port is None:
            self._virtual_port = mido.open_input(self.VIRTUAL_MONITOR_NAME, virtual=True)

    def close_virtual_monitor(self) -> None:
        if self._virtual_port is not None:
            self._virtual_port.close()
            self._virtual_port = None

    def close_all(self) -> None:
        for name in list(self._input_ports):
            self.close_input(name)
        self.close_virtual_monitor()

    def poll(self) -> list[MidiEvent]:
        events: list[MidiEvent] = []
        for name, port in self._input_ports.items():
            for msg in port.iter_pending():
                event = mido_message_to_event(msg, "in", port=name)
                if event is not None:
                    events.append(event)
        if self._virtual_port is not None:
            for msg in self._virtual_port.iter_pending():
                event = mido_message_to_event(msg, "out", port=self.VIRTUAL_MONITOR_NAME)
                if event is not None:
                    events.append(event)
        return events


__all__ = ["MidiEvent", "MidiMonitor", "list_input_ports", "mido_message_to_event"]
