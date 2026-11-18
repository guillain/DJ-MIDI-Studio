"""Signals between DJs (remote mix, phase 10), Qt-free.

In a club, a B2B is a glance and a nod. From two places there is no glance,
so a DJ sends a signal instead: one button (or a pad of their controller),
and it shows big on every other DJ's screen for a few seconds.

A signal travels on the control line like the shared mixer's moves
(``{"k": "sig", "s": key, "from": dj, "n": serial}``), three times, since a
UDP packet can be lost; each computer shows it once (``from`` + ``n``).

Pads are learned like the mixer's faders, but only a pad press (a Note On)
binds, so a fader moved while learning can't fire a signal. The pads live in
the workspace (``mix-together-signals.json``).
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from djmidi.i18n import QT_TRANSLATE_NOOP

if TYPE_CHECKING:
    from djmidi.midi_io import MidiEvent

_LOGGER = logging.getLogger(__name__)

MESSAGE_KIND = "sig"
REPEATS = 3
SHOW_S = 6.0
FILE_NAME = "mix-together-signals.json"
FORMAT = "djmidi-mix-signals/1"

# key -> English text (the key travels on the wire, never the translated text).
SIGNALS: dict[str, str] = {
    "next": QT_TRANSLATE_NOOP("RemoteSignals", "I'm starting the next track"),
    "drop": QT_TRANSLATE_NOOP("RemoteSignals", "Drop on the next phrase!"),
    "your_turn": QT_TRANSLATE_NOOP("RemoteSignals", "Your turn"),
    "hold": QT_TRANSLATE_NOOP("RemoteSignals", "Hold on, not yet"),
    "love": QT_TRANSLATE_NOOP("RemoteSignals", "Love it!"),
}
# Signals counted to the next phrase on the receiving side (both see the same phrase counter).
PHRASE_SIGNALS = frozenset({"drop"})


@dataclass(frozen=True)
class Signal:
    key: str
    sender: int


@dataclass(frozen=True)
class PadTrigger:
    channel: str
    note: str

    def label(self) -> str:
        return f"ch{self.channel} note {self.note}"


def pad_from_event(event: MidiEvent) -> PadTrigger | None:
    """A pad press (Note On with a velocity), or None for anything else."""
    if event.direction != "in" or event.event_type != "Note On":
        return None
    try:
        if int(event.data2) == 0:
            return None  # a Note On with velocity 0 is a release
    except (TypeError, ValueError):
        return None
    return PadTrigger(event.channel, event.data1)


class SignalBoard:
    """This computer's side of the signals: what to send, what to show."""

    def __init__(self, me: int) -> None:
        self.me = me
        self._serial = 0
        self._seen: deque[tuple[int, int]] = deque(maxlen=256)

    def send(self, key: str) -> dict:
        if key not in SIGNALS:
            raise ValueError(key)
        self._serial += 1
        return {"k": MESSAGE_KIND, "s": key, "from": self.me, "n": self._serial}

    def receive(self, message: dict) -> Signal | None:
        """Another DJ's signal, the first time it arrives; None for repeats and anything else."""
        if message.get("k") != MESSAGE_KIND:
            return None
        key, sender, serial = message.get("s"), message.get("from"), message.get("n")
        if key not in SIGNALS or not _is_int(sender) or not _is_int(serial) or sender == self.me:
            return None
        if (sender, serial) in self._seen:
            return None
        self._seen.append((sender, serial))
        return Signal(key, sender)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class SignalPads:
    """Which pad of the controller sends which signal."""

    def __init__(self, bindings: dict[str, PadTrigger] | None = None) -> None:
        self.bindings: dict[str, PadTrigger] = dict(bindings or {})

    def bind(self, key: str, trigger: PadTrigger) -> None:
        if key not in SIGNALS:
            raise ValueError(key)
        for other in [k for k, bound in self.bindings.items() if bound == trigger]:
            del self.bindings[other]
        self.bindings[key] = trigger

    def forget(self, key: str) -> None:
        self.bindings.pop(key, None)

    def fired(self, event: MidiEvent) -> str | None:
        trigger = pad_from_event(event)
        if trigger is None:
            return None
        return next((key for key, bound in self.bindings.items() if bound == trigger), None)

    def to_json(self) -> str:
        return json.dumps(
            {
                "format": FORMAT,
                "pads": {key: {"channel": t.channel, "note": t.note} for key, t in self.bindings.items()},
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> SignalPads:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ValueError("not a Mix Together signals file")
        pads = {}
        for key, raw in (data.get("pads") or {}).items():
            if key in SIGNALS and isinstance(raw, dict):
                pads[key] = PadTrigger(str(raw.get("channel", "")), str(raw.get("note", "")))
        return cls(pads)

    @classmethod
    def load(cls, path: Path) -> SignalPads:
        try:
            return cls.from_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            _LOGGER.warning("Mix Together signal pads not read from %s: %s", path, exc)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)
