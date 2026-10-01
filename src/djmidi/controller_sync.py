"""One-click controller "Sync": send a pre-recorded set of MIDI messages to
every connected controller to bring it into a known state.

Qt-free so the preferences store, the GUI and tests share one contract. A
:class:`ControllerSyncSet` is one controller's recorded messages (captured in
Controller Setup and saved into ``PluginPreferences``, one set per
controller); :func:`run_sync` sends every set to its controller's output port
in recorded order. Timing between recorded events is deliberately dropped:
an initialization burst only needs the order, and sending it immediately
keeps "Sync" a single, instant action.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

_EVENT_TYPES = {
    "note on": "Note On",
    "note off": "Note Off",
    "control change": "Control Change",
    "cc": "Control Change",
}


def _normalize_event_type(text: str) -> str:
    key = str(text).strip().lower().replace("-", " ").replace("_", " ")
    try:
        return _EVENT_TYPES[key]
    except KeyError:
        raise ValueError(f"Unsupported event_type: {text!r}") from None


def _bounded(value: object, field_name: str, low: int, high: int) -> int:
    try:
        number = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if not low <= number <= high:
        raise ValueError(f"{field_name} must be in [{low}, {high}]")
    return number


@dataclass(frozen=True)
class SyncMessage:
    event_type: str  # "Note On" / "Note Off" / "Control Change"
    channel: int  # 1-based
    data1: int
    data2: int

    @classmethod
    def create(cls, event_type: object, channel: object, data1: object, data2: object) -> SyncMessage:
        return cls(
            event_type=_normalize_event_type(str(event_type)),
            channel=_bounded(channel, "channel", 1, 16),
            data1=_bounded(data1, "data1", 0, 127),
            data2=_bounded(data2, "data2", 0, 127),
        )

    def to_dict(self) -> dict[str, object]:
        return {"event_type": self.event_type, "channel": self.channel, "data1": self.data1, "data2": self.data2}

    @classmethod
    def from_dict(cls, raw: object) -> SyncMessage:
        if not isinstance(raw, dict):
            raise TypeError("A sync message must be an object")
        return cls.create(raw.get("event_type", ""), raw.get("channel"), raw.get("data1"), raw.get("data2"))


@dataclass(frozen=True)
class ControllerSyncSet:
    controller: str
    # Preferred output port. "" (or a port that isn't connected right now)
    # falls back to matching the controller name against the port names.
    output_port: str = ""
    messages: tuple[SyncMessage, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "controller": self.controller,
            "output_port": self.output_port,
            "messages": [message.to_dict() for message in self.messages],
        }

    @classmethod
    def from_dict(cls, raw: object) -> ControllerSyncSet:
        if not isinstance(raw, dict):
            raise TypeError("A controller sync set must be an object")
        controller = raw.get("controller")
        if not isinstance(controller, str) or not controller.strip():
            raise ValueError("A controller sync set needs a controller name")
        messages = raw.get("messages", [])
        if not isinstance(messages, list):
            raise TypeError("A controller sync set's messages must be a list")
        return cls(
            controller=controller.strip(),
            output_port=str(raw.get("output_port", "")),
            messages=tuple(SyncMessage.from_dict(message) for message in messages),
        )


def sync_set_from_events(controller: str, events: Iterable[object], output_port: str = "") -> ControllerSyncSet:
    """Builds a sync set from recorded ``midi_io.MidiEvent``-like objects.

    Only input-direction note/CC events are kept (an output-direction event
    is Serato talking to the controller, not something the user recorded);
    an event that doesn't parse is skipped. Without an explicit
    ``output_port``, the port the first kept event arrived on is used -- a
    controller's input and output ports normally share its device name.
    """
    if not controller.strip():
        raise ValueError("A controller name is required")
    messages: list[SyncMessage] = []
    first_port = ""
    for event in events:
        if getattr(event, "direction", "in") != "in":
            continue
        try:
            message = SyncMessage.create(event.event_type, event.channel, event.data1, event.data2)
        except (AttributeError, ValueError) as exc:
            _LOGGER.debug("Skipping unrecordable sync event %r: %s", event, exc)
            continue
        messages.append(message)
        if not first_port:
            first_port = str(getattr(event, "port", "") or "")
    return ControllerSyncSet(controller.strip(), output_port or first_port, tuple(messages))


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def resolve_output_port(sync_set: ControllerSyncSet, available_ports: Sequence[str]) -> str | None:
    """Picks the output port to send ``sync_set`` to, or ``None`` if its
    controller doesn't look connected.

    Exact ``output_port`` match first; otherwise a punctuation/case-insensitive
    containment match on the recorded port name (port names gain a numeric
    suffix on some platforms), then on the controller name itself
    (``"DDJ-XP2"`` matches ``"PIONEER DDJ-XP2"``).
    """
    if sync_set.output_port and sync_set.output_port in available_ports:
        return sync_set.output_port
    for needle in (sync_set.output_port, sync_set.controller):
        squashed = _squash(needle)
        if not squashed:
            continue
        for port in available_ports:
            squashed_port = _squash(port)
            if squashed in squashed_port or (squashed_port and squashed_port in squashed):
                return port
    return None


@dataclass(frozen=True)
class SyncResult:
    controller: str
    port: str | None
    sent: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.port is not None and not self.error


def run_sync(
    sync_sets: Iterable[ControllerSyncSet],
    available_ports: Sequence[str],
    sender: Callable[..., None] | None = None,
) -> list[SyncResult]:
    """Sends every set to its controller's port; one :class:`SyncResult` per
    set. A disconnected controller or a failing port never stops the others."""
    if sender is None:
        from djmidi.midi_io import send_midi_message

        sender = send_midi_message
    results: list[SyncResult] = []
    for sync_set in sync_sets:
        port = resolve_output_port(sync_set, available_ports)
        if port is None:
            _LOGGER.info("Sync: %s not connected, skipped", sync_set.controller)
            results.append(SyncResult(sync_set.controller, None, error="not connected"))
            continue
        sent = 0
        try:
            for message in sync_set.messages:
                sender(
                    output_port_name=port,
                    event_type=message.event_type,
                    channel_1_based=message.channel,
                    data1=message.data1,
                    data2=message.data2,
                )
                sent += 1
        except Exception as exc:  # noqa: BLE001 - one failing port must not abort the other controllers
            _LOGGER.warning("Sync: sending to %r for %s failed after %d message(s): %s", port, sync_set.controller, sent, exc)
            results.append(SyncResult(sync_set.controller, port, sent, str(exc)))
            continue
        _LOGGER.info("Sync: sent %d message(s) to %r for %s", sent, port, sync_set.controller)
        results.append(SyncResult(sync_set.controller, port, sent))
    return results


def summarize_results(results: Sequence[SyncResult]) -> str:
    """One status-bar line, e.g. ``"Synced 1/2 controller(s): DDJ-XP2 (12 msg), XDJ-XZ (not connected)"``."""
    if not results:
        return "No controller sync set recorded"
    ok = sum(1 for result in results if result.ok)
    parts = [
        f"{result.controller} ({result.sent} msg)" if result.ok else f"{result.controller} ({result.error})"
        for result in results
    ]
    return f"Synced {ok}/{len(results)} controller(s): " + ", ".join(parts)


__all__ = [
    "ControllerSyncSet",
    "SyncMessage",
    "SyncResult",
    "resolve_output_port",
    "run_sync",
    "summarize_results",
    "sync_set_from_events",
]
