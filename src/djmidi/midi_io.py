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

import logging
import os
import time
from dataclasses import dataclass
from typing import Literal

import mido

from djmidi.midi_api import MidiPortInfo

Direction = Literal["in", "out"]
_LOGGER = logging.getLogger(__name__)


def _midi_disabled() -> bool:
    """Disable native MIDI probing for headless packaged smoke tests."""
    return os.environ.get("DJMIDI_DISABLE_MIDI") == "1"

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
    if _midi_disabled():
        _LOGGER.debug("MIDI probing disabled (DJMIDI_DISABLE_MIDI=1); returning no input ports")
        return []
    try:
        ports = mido.get_input_names()
    except Exception as exc:  # noqa: BLE001 - MIDI availability is optional at startup
        _LOGGER.warning("Unable to enumerate MIDI input ports: %s", exc)
        return []
    _LOGGER.debug("Found %d MIDI input port(s): %s", len(ports), ports)
    return ports


def list_output_ports() -> list[str]:
    if _midi_disabled():
        _LOGGER.debug("MIDI probing disabled (DJMIDI_DISABLE_MIDI=1); returning no output ports")
        return []
    try:
        ports = mido.get_output_names()
    except Exception as exc:  # noqa: BLE001 - MIDI availability is optional at startup
        _LOGGER.warning("Unable to enumerate MIDI output ports: %s", exc)
        return []
    _LOGGER.debug("Found %d MIDI output port(s): %s", len(ports), ports)
    return ports


def list_port_info() -> list[MidiPortInfo]:
    """Expose available mido ports using the normalized MIDI API shape."""
    inputs = [
        MidiPortInfo(id=name, name=name, type="input")
        for name in list_input_ports()
    ]
    outputs = [
        MidiPortInfo(id=name, name=name, type="output")
        for name in list_output_ports()
    ]
    return inputs + outputs


def _bounded_midi_byte(value: int, *, field_name: str) -> int:
    if not 0 <= value <= 127:
        raise ValueError(f"{field_name} must be in [0, 127], got {value}")
    return value


def _bounded_channel(channel_1_based: int) -> int:
    if not 1 <= channel_1_based <= 16:
        raise ValueError(f"channel must be in [1, 16], got {channel_1_based}")
    return channel_1_based - 1


def send_midi_message(
    *,
    output_port_name: str,
    event_type: str,
    channel_1_based: int,
    data1: int,
    data2: int,
) -> None:
    """Sends a single NOTE/CC style MIDI message to a hardware/virtual output.

    Parameters follow the same 1-based channel convention used elsewhere in this
    project's model/UI. `event_type` accepts common aliases (e.g. "Note On",
    "note_on", "Control Change", "cc").
    """
    event_key = event_type.strip().lower().replace("-", " ").replace("_", " ")
    msg_type_map = {
        "note on": "note_on",
        "note off": "note_off",
        "control change": "control_change",
        "cc": "control_change",
    }
    msg_type = msg_type_map.get(event_key)
    if msg_type is None:
        raise ValueError(f"Unsupported event_type: {event_type!r}")

    channel = _bounded_channel(channel_1_based)
    d1 = _bounded_midi_byte(data1, field_name="data1")
    d2 = _bounded_midi_byte(data2, field_name="data2")

    kwargs = {"channel": channel}
    if msg_type in ("note_on", "note_off"):
        kwargs["note"] = d1
        kwargs["velocity"] = d2
    else:
        kwargs["control"] = d1
        kwargs["value"] = d2

    message = mido.Message(msg_type, **kwargs)
    _LOGGER.info(
        "Sending MIDI %s to %r: channel=%d data1=%d data2=%d",
        msg_type,
        output_port_name,
        channel_1_based,
        d1,
        d2,
    )
    try:
        with mido.open_output(output_port_name) as output_port:
            output_port.send(message)
    except Exception:
        _LOGGER.exception("Failed to send MIDI message to %r", output_port_name)
        raise


class MidiMonitor:
    """Owns zero or more open MIDI input ports (real device sources) plus an
    optional virtual destination this app creates so Serato's *output* can be
    routed to it (see README/CLAUDE.md — this requires the user to manually
    add it as an extra MIDI output in Serato, CoreMIDI doesn't let a third
    app silently see what another app sends to a hardware destination)."""

    VIRTUAL_MONITOR_NAME = "DJMidiStudio Monitor"

    def __init__(self) -> None:
        self._input_ports: dict[str, mido.ports.BaseInput] = {}
        self._virtual_port: mido.ports.BaseInput | None = None

    def open_input(self, name: str) -> None:
        if name in self._input_ports:
            return
        _LOGGER.info("Opening MIDI input port %r", name)
        try:
            self._input_ports[name] = mido.open_input(name)
        except Exception:
            _LOGGER.exception("Failed to open MIDI input port %r", name)
            raise

    def close_input(self, name: str) -> None:
        port = self._input_ports.pop(name, None)
        if port is not None:
            _LOGGER.info("Closing MIDI input port %r", name)
            try:
                port.close()
            except Exception:
                _LOGGER.warning("Failed to close MIDI input port %r", name, exc_info=True)

    def open_virtual_monitor(self) -> None:
        if self._virtual_port is None:
            _LOGGER.info("Opening virtual monitor input port %r", self.VIRTUAL_MONITOR_NAME)
            try:
                self._virtual_port = mido.open_input(self.VIRTUAL_MONITOR_NAME, virtual=True)
            except Exception:
                _LOGGER.exception("Failed to open virtual monitor port %r", self.VIRTUAL_MONITOR_NAME)
                raise

    def close_virtual_monitor(self) -> None:
        if self._virtual_port is not None:
            _LOGGER.info("Closing virtual monitor input port %r", self.VIRTUAL_MONITOR_NAME)
            try:
                self._virtual_port.close()
            except Exception:
                _LOGGER.warning(
                    "Failed to close virtual monitor port %r", self.VIRTUAL_MONITOR_NAME, exc_info=True
                )
            self._virtual_port = None

    def close_all(self) -> None:
        _LOGGER.debug("Closing all MidiMonitor ports (%d input, virtual=%s)", len(self._input_ports), self._virtual_port is not None)
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
        if events:
            _LOGGER.debug("MidiMonitor.poll: %d event(s) received", len(events))
        return events


__all__ = [
    "MidiEvent",
    "MidiMonitor",
    "list_input_ports",
    "list_output_ports",
    "list_port_info",
    "mido_message_to_event",
    "send_midi_message",
]
