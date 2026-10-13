"""MIDI macros (issue #228): named, user-defined sequences of MIDI messages
played on demand from the Macros menu or a keyboard shortcut.

Qt-free so the file store, the GUI and tests share one contract. A macro
reuses the controller Sync building blocks -- :class:`SyncMessage` for each
message and :func:`resolve_output_port` to find its port -- and adds what a
sync set deliberately leaves out: an optional delay before each message, so
a macro can, say, press a button, wait 200 ms and release it.

Storage mirrors the sync sets: one JSON file per macro in the user's
``Macros`` folder (:func:`load_macros` / :func:`save_macros`), the name only
a label (loading reads the macro's name from the file's content).

A macro can also be bound to a controller button (issue #252, MIDI Learn
for macros): :class:`MacroTrigger` is the Note On / Control Change the
macro editor's Learn button captured, stored in the macro's own file, and
:func:`macros_for_event` finds the macros a live press fires. Only a press
counts -- the same rule as the mapping editor's MIDI Learn
(:func:`djmidi.midi_learn.trigger_from_event`) -- so a button's release
never plays its macro a second time.

Playing is split in two so the GUI never blocks its event loop on a delay:
:func:`macro_schedule` turns the per-step delays into absolute offsets the
GUI feeds to timers, and :func:`run_macro` plays the same schedule
synchronously with an injectable ``sleep`` (tests, scripts).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from djmidi.controller_sync import ControllerSyncSet, SyncMessage, resolve_output_port
from djmidi.midi_learn import trigger_from_event

if TYPE_CHECKING:
    from djmidi.midi_io import MidiEvent

_LOGGER = logging.getLogger(__name__)

FORMAT_VERSION = 1
# A macro is a quick on-stage action, not a sequencer: one minute per step
# is far beyond any sensible use and bounds a typo like "20000000".
MAX_DELAY_MS = 60_000


def _delay(value: object) -> int:
    text = str(value if value is not None else "").strip() or "0"
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError("delay must be an integer number of milliseconds") from exc
    if not 0 <= number <= MAX_DELAY_MS:
        raise ValueError(f"delay must be in [0, {MAX_DELAY_MS}] ms")
    return number


TRIGGER_EVENT_TYPES = ("Note On", "Control Change")


def _port_key(port: str) -> str:
    """A port name compared case/punctuation-insensitively."""
    return "".join(char for char in port.casefold() if char.isalnum())


def _bounded(value: object, label: str, low: int, high: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if not low <= number <= high:
        raise ValueError(f"{label} must be in [{low}, {high}]")
    return number


@dataclass(frozen=True)
class MacroTrigger:
    """The controller press that fires a macro: a Note On (any velocity
    above 0) or a Control Change (any value) on ``channel``/``data1``.
    ``port`` is the input port it was learned on; blank matches every input
    -- two controllers on one setup often send the same note, so a learned
    trigger keeps its port by default."""

    event_type: str
    channel: int  # 1-based
    data1: int
    port: str = ""

    @classmethod
    def create(cls, event_type: object, channel: object, data1: object, port: object = "") -> MacroTrigger:
        kind = str(event_type or "").strip()
        if kind not in TRIGGER_EVENT_TYPES:
            raise ValueError(f"a trigger must be a {' or a '.join(TRIGGER_EVENT_TYPES)}")
        return cls(kind, _bounded(channel, "channel", 1, 16), _bounded(data1, "data1", 0, 127), str(port or "").strip())

    @classmethod
    def from_event(cls, event: MidiEvent) -> MacroTrigger | None:
        """The trigger a live event would bind, or ``None`` when it isn't a
        press (a release, a velocity-0 Note On, LED feedback)."""
        learned = trigger_from_event(event)
        if learned is None:
            return None
        try:
            return cls.create(learned.event_type, learned.channel, learned.control, event.port)
        except ValueError:
            return None

    def matches(self, event: MidiEvent) -> bool:
        """Whether a live event is a press of this trigger."""
        pressed = MacroTrigger.from_event(event)
        if pressed is None or (pressed.event_type, pressed.channel, pressed.data1) != (
            self.event_type,
            self.channel,
            self.data1,
        ):
            return False
        return not self.port or _port_key(self.port) == _port_key(pressed.port)

    def label(self) -> str:
        kind = "Note" if self.event_type == "Note On" else "CC"
        where = f" on {self.port}" if self.port else ""
        return f"{kind} {self.data1}, ch {self.channel}{where}"

    def to_dict(self) -> dict[str, object]:
        return {"event_type": self.event_type, "channel": self.channel, "data1": self.data1, "port": self.port}

    @classmethod
    def from_dict(cls, raw: object) -> MacroTrigger:
        if not isinstance(raw, dict):
            raise TypeError("A macro trigger must be an object")
        return cls.create(raw.get("event_type"), raw.get("channel"), raw.get("data1"), raw.get("port", ""))


@dataclass(frozen=True)
class MacroStep:
    message: SyncMessage
    # Pause before this message is sent, in milliseconds.
    delay_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {**self.message.to_dict(), "delay_ms": self.delay_ms}

    @classmethod
    def from_dict(cls, raw: object) -> MacroStep:
        if not isinstance(raw, dict):
            raise TypeError("A macro step must be an object")
        return cls(SyncMessage.from_dict(raw), _delay(raw.get("delay_ms", 0)))


@dataclass(frozen=True)
class MidiMacro:
    name: str
    # Output port, or a controller name: resolved like a sync set's port
    # (exact match, else case/punctuation-insensitive containment).
    output_port: str = ""
    steps: tuple[MacroStep, ...] = field(default_factory=tuple)
    # QKeySequence portable text ("Ctrl+Shift+1"), "" for none.
    shortcut: str = ""
    # Controller press that plays the macro (issue #252), None for none.
    trigger: MacroTrigger | None = None

    @property
    def duration_ms(self) -> int:
        return sum(step.delay_ms for step in self.steps)

    def to_dict(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "version": FORMAT_VERSION,
            "name": self.name,
            "output_port": self.output_port,
            "shortcut": self.shortcut,
            "steps": [step.to_dict() for step in self.steps],
        }
        # Only written when set, so a macro without one keeps its old file shape.
        if self.trigger is not None:
            raw["trigger"] = self.trigger.to_dict()
        return raw

    @classmethod
    def from_dict(cls, raw: object) -> MidiMacro:
        if not isinstance(raw, dict):
            raise TypeError("A macro must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A macro needs a name")
        steps = raw.get("steps", [])
        if not isinstance(steps, list):
            raise TypeError("A macro's steps must be a list")
        return cls(
            name=name.strip(),
            output_port=str(raw.get("output_port", "") or ""),
            steps=tuple(MacroStep.from_dict(step) for step in steps),
            shortcut=str(raw.get("shortcut", "") or "").strip(),
            trigger=MacroTrigger.from_dict(raw["trigger"]) if raw.get("trigger") else None,
        )


def steps_from_rows(rows: Iterable[Sequence[object]]) -> tuple[MacroStep, ...]:
    """Validates edited ``(event_type, channel, data1, data2, delay_ms)`` rows,
    raising ``ValueError`` naming the first bad one (1-based)."""
    steps: list[MacroStep] = []
    for number, row in enumerate(rows, start=1):
        try:
            event_type, channel, data1, data2, delay_ms = row
            steps.append(MacroStep(SyncMessage.create(event_type, channel, data1, data2), _delay(delay_ms)))
        except ValueError as exc:
            raise ValueError(f"Step {number}: {exc}") from None
    return tuple(steps)


def _triggers_overlap(a: MacroTrigger, b: MacroTrigger) -> bool:
    if (a.event_type, a.channel, a.data1) != (b.event_type, b.channel, b.data1):
        return False
    return not a.port or not b.port or _port_key(a.port) == _port_key(b.port)


def retriggers_itself(macro: MidiMacro) -> bool:
    """Whether playing ``macro`` sends its own trigger back to the port it
    listens on -- a virtual loopback port (IAC, loopMIDI) would then fire it
    forever. Only checked when both ports are named and equal."""
    trigger = macro.trigger
    if trigger is None or not trigger.port or _port_key(trigger.port) != _port_key(macro.output_port):
        return False
    for step in macro.steps:
        message = step.message
        if (message.event_type, message.channel, message.data1) != (trigger.event_type, trigger.channel, trigger.data1):
            continue
        if message.event_type == "Control Change" or message.data2 > 0:
            return True
    return False


def validate_macros(macros: Sequence[MidiMacro]) -> list[str]:
    """Problems that must be fixed before saving: a blank or duplicate name
    (case-insensitive -- names become file names), a shortcut or controller
    trigger used twice, a macro that would retrigger itself."""
    problems: list[str] = []
    names: set[str] = set()
    shortcuts: dict[str, str] = {}
    triggers: list[tuple[MacroTrigger, str]] = []
    for macro in macros:
        name = macro.name.strip()
        if not name:
            problems.append("A macro has no name")
            continue
        if name.casefold() in names:
            problems.append(f"Two macros are named \"{name}\"")
        names.add(name.casefold())
        if macro.shortcut:
            other = shortcuts.get(macro.shortcut.casefold())
            if other is not None:
                problems.append(f"\"{name}\" and \"{other}\" use the same shortcut {macro.shortcut}")
            else:
                shortcuts[macro.shortcut.casefold()] = name
        if macro.trigger is not None:
            other = next((owner for trigger, owner in triggers if _triggers_overlap(trigger, macro.trigger)), None)
            if other is not None:
                problems.append(f"\"{name}\" and \"{other}\" use the same controller trigger {macro.trigger.label()}")
            else:
                triggers.append((macro.trigger, name))
            if retriggers_itself(macro):
                problems.append(f"\"{name}\" sends its own trigger back to {macro.output_port} and would loop")
    return problems


def macros_for_event(macros: Iterable[MidiMacro], event: MidiEvent) -> list[MidiMacro]:
    """The macros a live MIDI event fires (only presses do)."""
    return [macro for macro in macros if macro.trigger is not None and macro.trigger.matches(event)]


def macro_schedule(macro: MidiMacro) -> list[tuple[int, SyncMessage]]:
    """Each message with its offset in ms from the start of the macro."""
    offset = 0
    schedule: list[tuple[int, SyncMessage]] = []
    for step in macro.steps:
        offset += step.delay_ms
        schedule.append((offset, step.message))
    return schedule


def resolve_macro_port(macro: MidiMacro, available_ports: Sequence[str]) -> str | None:
    """The connected port ``macro`` plays to, or ``None``."""
    target = macro.output_port.strip()
    if not target:
        return None
    return resolve_output_port(ControllerSyncSet(target, target), available_ports)


def send_message(message: SyncMessage, port: str, sender: Callable[..., None] | None = None) -> None:
    if sender is None:
        from djmidi.midi_io import send_midi_message

        sender = send_midi_message
    sender(
        output_port_name=port,
        event_type=message.event_type,
        channel_1_based=message.channel,
        data1=message.data1,
        data2=message.data2,
    )


@dataclass(frozen=True)
class MacroResult:
    name: str
    port: str | None
    sent: int = 0
    total: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.port is not None and not self.error

    def summary(self) -> str:
        """One status-bar line."""
        if self.ok:
            return f"Macro \"{self.name}\": sent {self.sent} message(s) to {self.port}"
        if self.port is None:
            return f"Macro \"{self.name}\" not played: {self.error}"
        return f"Macro \"{self.name}\" stopped after {self.sent}/{self.total} message(s): {self.error}"


def unplayable_result(macro: MidiMacro, available_ports: Sequence[str]) -> MacroResult | None:
    """The failed result to report instead of playing ``macro``, or ``None``
    when it can play (it has steps and its port is connected)."""
    if not macro.steps:
        return MacroResult(macro.name, None, error="no message to send")
    if not macro.output_port.strip():
        return MacroResult(macro.name, None, total=len(macro.steps), error="no output port chosen")
    if resolve_macro_port(macro, available_ports) is None:
        return MacroResult(macro.name, None, total=len(macro.steps), error=f"{macro.output_port} is not connected")
    return None


def run_macro(
    macro: MidiMacro,
    available_ports: Sequence[str],
    sender: Callable[..., None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> MacroResult:
    """Plays ``macro`` synchronously, sleeping each step's delay. A failing
    send stops the macro (later steps may depend on it) and is reported."""
    failed = unplayable_result(macro, available_ports)
    if failed is not None:
        return failed
    port = resolve_macro_port(macro, available_ports)
    assert port is not None  # checked by unplayable_result
    sent = 0
    for step in macro.steps:
        if step.delay_ms:
            sleep(step.delay_ms / 1000)
        try:
            send_message(step.message, port, sender)
        except Exception as exc:  # noqa: BLE001 - report the failure instead of crashing the caller
            _LOGGER.warning("Macro %r: sending to %r failed after %d message(s): %s", macro.name, port, sent, exc)
            return MacroResult(macro.name, port, sent, len(macro.steps), str(exc))
        sent += 1
    return MacroResult(macro.name, port, sent, len(macro.steps))


def macro_from_sync_set(name: str, sync_set: ControllerSyncSet) -> MidiMacro:
    """A macro starting from a recorded sync set's messages (no delays)."""
    return MidiMacro(name, sync_set.output_port or sync_set.controller, tuple(MacroStep(m) for m in sync_set.messages))


# --- file store ------------------------------------------------------------


def _slug(text: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in text.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "macro"


def macro_file_name(name: str) -> str:
    return f"{_slug(name)}.json"


def load_macros(directory: str | Path) -> list[MidiMacro]:
    """Every readable macro in ``directory``, sorted by name; a broken file
    is logged and skipped rather than losing the others, and of two files
    holding the same name the last one (by file name) wins."""
    folder = Path(directory)
    if not folder.is_dir():
        return []
    macros: dict[str, MidiMacro] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            macro = MidiMacro.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            _LOGGER.warning("Skipped macro file %s: %s", path, exc)
            continue
        macros[macro.name.casefold()] = macro
    return sorted(macros.values(), key=lambda macro: macro.name.casefold())


def save_macros(directory: str | Path, macros: Iterable[MidiMacro]) -> None:
    """One file per macro; files of macros that are gone are removed, so the
    folder always mirrors the app's list (a file that isn't a readable macro
    is left alone -- it may be one the user is still editing by hand). Two
    names slugging to the same file get a numbered suffix rather than
    overwriting each other."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    keep: set[str] = set()
    for macro in macros:
        name = macro_file_name(macro.name)
        stem, number = name.removesuffix(".json"), 2
        while name in keep:
            name, number = f"{stem}-{number}.json", number + 1
        keep.add(name)
        (folder / name).write_text(json.dumps(macro.to_dict(), indent=2) + "\n", encoding="utf-8")
    for path in folder.glob("*.json"):
        if path.name in keep:
            continue
        try:
            MidiMacro.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError):
            continue
        path.unlink()


__all__ = [
    "MAX_DELAY_MS",
    "MacroResult",
    "MacroStep",
    "MacroTrigger",
    "MidiMacro",
    "load_macros",
    "macro_file_name",
    "macro_from_sync_set",
    "macro_schedule",
    "macros_for_event",
    "resolve_macro_port",
    "retriggers_itself",
    "run_macro",
    "save_macros",
    "send_message",
    "steps_from_rows",
    "unplayable_result",
    "validate_macros",
]
