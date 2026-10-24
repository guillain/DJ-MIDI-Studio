"""One-click controller "Sync": send a pre-recorded set of MIDI messages to
every connected controller to bring it into a known state.

Qt-free so the preferences store, the GUI and tests share one contract. A
:class:`ControllerSyncSet` is one controller's recorded messages (captured in
Controller Setup and saved into ``PluginPreferences``, one set per
controller and scene); :func:`run_sync` sends every set to its controller's output port
in recorded order. Timing between recorded events is deliberately dropped:
an initialization burst only needs the order, and sending it immediately
keeps "Sync" a single, instant action.

Scenes (issue #188): a controller may have several named sets ("Tek",
"DnB", "Warm-up"...), keyed by ``(controller, scene)``. One scene is active
at a time; :func:`sets_for_scene` picks, for each controller, its set for
that scene and falls back to its :data:`DEFAULT_SCENE` set when it has none
-- so a controller recorded only once keeps syncing whatever scene is active.
A set saved before scenes existed carries no ``scene`` key and loads as
:data:`DEFAULT_SCENE`.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from functools import partial

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

_LOGGER = logging.getLogger(__name__)

# Status-bar texts (issue #313): English templates, translated by the caller.
NOT_CONNECTED = QT_TRANSLATE_NOOP("ControllerSync", "not connected")
_NO_SET = QT_TRANSLATE_NOOP("ControllerSync", "No controller sync set recorded")
_SENT = QT_TRANSLATE_NOOP("ControllerSync", "{controller} ({count} msg)")
_FAILED = QT_TRANSLATE_NOOP("ControllerSync", "{controller} ({error})")
_SYNCED = QT_TRANSLATE_NOOP("ControllerSync", "Synced {ok}/{total} controller(s): {parts}")
# Message validation errors, shown by the sync set editor (issue #337).
_UNSUPPORTED_TYPE = QT_TRANSLATE_NOOP("ControllerSync", "Unsupported event_type: {type}")
_NOT_INTEGER = QT_TRANSLATE_NOOP("ControllerSync", "{field} must be an integer")
_OUT_OF_RANGE = QT_TRANSLATE_NOOP("ControllerSync", "{field} must be in [{low}, {high}]")
_MESSAGE_ERROR = QT_TRANSLATE_NOOP("ControllerSync", "Message {number}: {error}")
_FIELD_CHANNEL = QT_TRANSLATE_NOOP("ControllerSync", "channel")
_FIELD_DATA1 = QT_TRANSLATE_NOOP("ControllerSync", "data1")
_FIELD_DATA2 = QT_TRANSLATE_NOOP("ControllerSync", "data2")

_EVENT_TYPES = {
    "note on": "Note On",
    "note off": "Note Off",
    "control change": "Control Change",
    "cc": "Control Change",
}


def _normalize_event_type(text: str, translate: Translate = untranslated) -> str:
    key = str(text).strip().lower().replace("-", " ").replace("_", " ")
    try:
        return _EVENT_TYPES[key]
    except KeyError:
        raise ValueError(translate(_UNSUPPORTED_TYPE).format(type=repr(text))) from None


def _bounded(value: object, field_name: str, low: int, high: int, translate: Translate = untranslated) -> int:
    try:
        number = int(str(value).strip())
    except ValueError as exc:
        raise ValueError(translate(_NOT_INTEGER).format(field=translate(field_name))) from exc
    if not low <= number <= high:
        raise ValueError(translate(_OUT_OF_RANGE).format(field=translate(field_name), low=low, high=high))
    return number


@dataclass(frozen=True)
class SyncMessage:
    event_type: str  # "Note On" / "Note Off" / "Control Change"
    channel: int  # 1-based
    data1: int
    data2: int

    @classmethod
    def create(
        cls,
        event_type: object,
        channel: object,
        data1: object,
        data2: object,
        translate: Translate = untranslated,
    ) -> SyncMessage:
        """`translate` words a validation error in the interface language."""
        return cls(
            event_type=_normalize_event_type(str(event_type), translate),
            channel=_bounded(channel, _FIELD_CHANNEL, 1, 16, translate),
            data1=_bounded(data1, _FIELD_DATA1, 0, 127, translate),
            data2=_bounded(data2, _FIELD_DATA2, 0, 127, translate),
        )

    def to_dict(self) -> dict[str, object]:
        return {"event_type": self.event_type, "channel": self.channel, "data1": self.data1, "data2": self.data2}

    @classmethod
    def from_dict(cls, raw: object) -> SyncMessage:
        if not isinstance(raw, dict):
            raise TypeError("A sync message must be an object")
        return cls.create(raw.get("event_type", ""), raw.get("channel"), raw.get("data1"), raw.get("data2"))


DEFAULT_SCENE = "Default"


def normalize_scene(name: object) -> str:
    """A scene name stripped of surrounding blanks; blank means :data:`DEFAULT_SCENE`."""
    text = str(name or "").strip()
    return text or DEFAULT_SCENE


@dataclass(frozen=True)
class ControllerSyncSet:
    controller: str
    # Preferred output port. "" (or a port that isn't connected right now)
    # falls back to matching the controller name against the port names.
    output_port: str = ""
    messages: tuple[SyncMessage, ...] = field(default_factory=tuple)
    # Named scene this set belongs to (issue #188); see sets_for_scene.
    scene: str = DEFAULT_SCENE

    @property
    def key(self) -> tuple[str, str]:
        return (self.controller, self.scene)

    @property
    def label(self) -> str:
        """``"DDJ-XP2"`` for the default scene, ``"DDJ-XP2 — Tek"`` otherwise."""
        return self.controller if self.scene == DEFAULT_SCENE else f"{self.controller} — {self.scene}"

    def to_dict(self) -> dict[str, object]:
        return {
            "controller": self.controller,
            "scene": self.scene,
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
            scene=normalize_scene(raw.get("scene")),
        )

    def with_messages(self, messages: Iterable[SyncMessage]) -> ControllerSyncSet:
        """A copy with its messages replaced (the Preferences editor's result)."""
        return ControllerSyncSet(self.controller, self.output_port, tuple(messages), self.scene)

    def in_scene(self, scene: object) -> ControllerSyncSet:
        """A copy filed under another scene."""
        return ControllerSyncSet(self.controller, self.output_port, self.messages, normalize_scene(scene))


def scene_names(sync_sets: Iterable[ControllerSyncSet], *extra: str) -> list[str]:
    """Every scene in use (plus ``extra``), :data:`DEFAULT_SCENE` first, the
    others in case-insensitive alphabetical order."""
    names = {sync_set.scene for sync_set in sync_sets} | {normalize_scene(name) for name in extra}
    names.discard(DEFAULT_SCENE)
    return [DEFAULT_SCENE, *sorted(names, key=str.casefold)]


def sets_for_scene(sync_sets: Iterable[ControllerSyncSet], scene: object) -> list[ControllerSyncSet]:
    """The sets to send while ``scene`` is active: for each controller (in
    first-seen order) its set for that scene, else its default-scene set; a
    controller with neither is left out."""
    wanted = normalize_scene(scene)
    by_controller: dict[str, dict[str, ControllerSyncSet]] = {}
    for sync_set in sync_sets:
        by_controller.setdefault(sync_set.controller, {})[sync_set.scene] = sync_set
    chosen = (scenes.get(wanted) or scenes.get(DEFAULT_SCENE) for scenes in by_controller.values())
    return [sync_set for sync_set in chosen if sync_set is not None]


def move_message(messages: Sequence[SyncMessage], index: int, offset: int) -> tuple[SyncMessage, ...]:
    """Moves ``messages[index]`` by ``offset`` places (``-1`` = up), clamped to
    the list's ends; an out-of-range ``index`` returns the list unchanged."""
    items = list(messages)
    if not 0 <= index < len(items):
        return tuple(items)
    target = max(0, min(len(items) - 1, index + offset))
    items.insert(target, items.pop(index))
    return tuple(items)


def messages_from_rows(
    rows: Iterable[Sequence[object]], translate: Translate = untranslated
) -> tuple[SyncMessage, ...]:
    """Validates edited ``(event_type, channel, data1, data2)`` rows.

    Raises ``ValueError`` naming the first bad row (1-based), so an editor can
    point at it instead of silently dropping the message; worded in the
    language `translate` gives (issue #337)."""
    messages: list[SyncMessage] = []
    for number, row in enumerate(rows, start=1):
        try:
            event_type, channel, data1, data2 = row
            messages.append(SyncMessage.create(event_type, channel, data1, data2, translate))
        except ValueError as exc:
            raise ValueError(translate(_MESSAGE_ERROR).format(number=number, error=exc)) from None
    return tuple(messages)


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


def collapse_control_changes(messages: Iterable[SyncMessage]) -> tuple[tuple[SyncMessage, ...], int]:
    """Keeps only the last value of each ``(channel, CC number)``, at the
    position of that CC's last occurrence; notes are kept as recorded.

    A fader, knob or jog moved while recording sends hundreds of Control
    Change messages, and a sync set is replayed at every launch: only the
    final position matters. Keeping it where the CC last occurred keeps the
    final state's order relative to the notes. Returns the collapsed
    messages and how many CC messages were dropped."""
    items = list(messages)
    last_index: dict[tuple[int, int], int] = {}
    for index, message in enumerate(items):
        if message.event_type == "Control Change":
            last_index[(message.channel, message.data1)] = index
    kept = tuple(
        message
        for index, message in enumerate(items)
        if message.event_type != "Control Change" or last_index[(message.channel, message.data1)] == index
    )
    return kept, len(items) - len(kept)


def recorded_sync_sets(
    events: Iterable[object], controller_for_port: Callable[[str], str] | None = None
) -> tuple[list[ControllerSyncSet], dict[str, int]]:
    """:func:`sync_sets_from_recording`, plus how many Control Change
    messages :func:`collapse_control_changes` dropped, keyed by each set's
    ``output_port`` (the recorded port)."""
    by_port: dict[str, list[object]] = {}
    for event in events:
        if getattr(event, "direction", "in") != "in":
            continue
        by_port.setdefault(str(getattr(event, "port", "") or ""), []).append(event)
    sync_sets: list[ControllerSyncSet] = []
    collapsed: dict[str, int] = {}
    taken: set[str] = set()
    for port, port_events in by_port.items():
        if not port.strip():
            continue
        controller = ((controller_for_port(port) if controller_for_port else "") or port).strip()
        if controller in taken:
            controller = _unique_name(port.strip(), taken)
        sync_set = sync_set_from_events(controller, port_events, output_port=port)
        if sync_set.messages:
            messages, dropped = collapse_control_changes(sync_set.messages)
            taken.add(sync_set.controller)
            sync_sets.append(sync_set.with_messages(messages))
            collapsed[port] = dropped
    return sync_sets, collapsed


def sync_sets_from_recording(
    events: Iterable[object], controller_for_port: Callable[[str], str] | None = None
) -> list[ControllerSyncSet]:
    """Splits one recording over several input ports into one sync set per
    port, in first-seen order -- the menu bar's Record button listens to
    every controller at once. ``controller_for_port`` names the controller
    behind a port (catalog detection in the GUI); the port name itself is
    used when it returns nothing. The recorded port becomes each set's
    ``output_port``, a controller's input and output ports normally sharing
    its device name. Ports that produced no note/CC message yield no set.

    Sets are stored one per controller name, so a port whose controller is
    already named by an earlier port (two identical units, say) gets its own
    port's name instead -- otherwise saving would keep only the last port's
    recording.

    Control Change traffic is collapsed (:func:`collapse_control_changes`):
    a fader moved while recording keeps only its final value. Controller
    Setup's :func:`sync_set_from_events` doesn't collapse -- there the user
    sees and edits every recorded row before saving."""
    return recorded_sync_sets(events, controller_for_port)[0]


def _unique_name(name: str, taken: set[str]) -> str:
    """``name``, or ``"name (2)"``, ``"name (3)"``... if it's already taken."""
    unique, number = name, 2
    while unique in taken:
        unique, number = f"{name} ({number})", number + 1
    return unique


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
    port_opener: Callable[[str], AbstractContextManager[Callable[..., None]]] | None = None,
) -> list[SyncResult]:
    """Sends every set to its controller's port; one :class:`SyncResult` per
    set. A disconnected controller or a failing port never stops the others.

    Each set's port is opened once, all its messages are sent, then it is
    closed (issue #297) -- by default through :func:`midi_io.open_midi_output`.
    Tests inject either ``port_opener`` (a port name -> context manager
    yielding a per-message sender) or, more simply, ``sender`` (called per
    message with ``output_port_name`` and the message fields)."""
    if port_opener is None:
        if sender is not None:
            per_message = sender

            def port_opener(port: str) -> AbstractContextManager[Callable[..., None]]:
                return nullcontext(partial(per_message, output_port_name=port))
        else:
            from djmidi.midi_io import open_midi_output

            port_opener = open_midi_output
    results: list[SyncResult] = []
    for sync_set in sync_sets:
        port = resolve_output_port(sync_set, available_ports)
        if port is None:
            _LOGGER.info("Sync: %s not connected, skipped", sync_set.controller)
            results.append(SyncResult(sync_set.controller, None, error=NOT_CONNECTED))
            continue
        sent = 0
        try:
            with port_opener(port) as send:
                for message in sync_set.messages:
                    send(
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


_PORT_INDEX_SUFFIX = re.compile(r"\s+\d+$")


def port_identity(port: str) -> str:
    """A port name without the trailing index Windows adds (``"DDJ-XP2 1"``
    -> ``"DDJ-XP2"``), which changes whenever another device comes or goes."""
    return _PORT_INDEX_SUFFIX.sub("", port.strip())


class PlugInSyncTracker:
    """Decides which sync sets to send when a controller is plugged in.

    Remembers the output ports seen on the previous poll; a set is due only
    when the port it resolves to (:func:`resolve_output_port`) wasn't there
    last time -- so a controller staying connected is never re-synced, and
    unplugging then replugging it syncs it again. Tracking ports rather than
    controllers also means a set recorded (or edited) while its controller
    is already connected isn't sent back to it on the next poll.

    Ports are compared by :func:`port_identity`, counted (issue #305): on
    Windows a controller that never left can come back under another index
    (``"DDJ-XP2 1"`` -> ``"DDJ-XP2 0"``) when another device is plugged or
    unplugged, which isn't a plug-in; a second port with the same identity
    (a second identical unit) still is.

    The first :meth:`due` call only records the ports (a controller already
    connected when watching starts wasn't "plugged in"); :meth:`seed` does
    the same explicitly, e.g. with the port list the launch-time Sync just
    used, so a controller isn't synced twice at launch.
    """

    def __init__(self) -> None:
        self._known: Counter[str] | None = None

    @property
    def seeded(self) -> bool:
        return self._known is not None

    def seed(self, available_ports: Iterable[str]) -> None:
        self._known = Counter(port_identity(port) for port in available_ports)

    def reset(self) -> None:
        """Forgets the ports, so the next :meth:`due` call only re-seeds."""
        self._known = None

    def due(self, sync_sets: Iterable[ControllerSyncSet], available_ports: Sequence[str]) -> list[ControllerSyncSet]:
        """The sets whose controller appeared since the previous call."""
        previous = self._known
        self.seed(available_ports)
        if previous is None:
            return []
        appeared = {identity for identity, count in self._known.items() if count > previous[identity]}
        if not appeared:
            return []
        return [
            sync_set
            for sync_set in sync_sets
            if (port := resolve_output_port(sync_set, available_ports)) is not None
            and port_identity(port) in appeared
        ]


def summarize_results(results: Sequence[SyncResult], translate: Translate = untranslated) -> str:
    """One status-bar line, e.g. ``"Synced 1/2 controller(s): DDJ-XP2 (12 msg), XDJ-XZ (not connected)"``.

    ``translate`` turns each English template (and the "not connected"
    error) into the interface language before it is filled in (issue #313);
    an exception's own message has no catalogue entry and passes unchanged."""
    if not results:
        return translate(_NO_SET)
    ok = sum(1 for result in results if result.ok)
    parts = [
        translate(_SENT).format(controller=result.controller, count=result.sent)
        if result.ok
        else translate(_FAILED).format(controller=result.controller, error=translate(result.error))
        for result in results
    ]
    return translate(_SYNCED).format(ok=ok, total=len(results), parts=", ".join(parts))


__all__ = [
    "DEFAULT_SCENE",
    "ControllerSyncSet",
    "PlugInSyncTracker",
    "SyncMessage",
    "SyncResult",
    "collapse_control_changes",
    "messages_from_rows",
    "move_message",
    "normalize_scene",
    "port_identity",
    "recorded_sync_sets",
    "resolve_output_port",
    "run_sync",
    "scene_names",
    "sets_for_scene",
    "summarize_results",
    "sync_set_from_events",
    "sync_sets_from_recording",
]
