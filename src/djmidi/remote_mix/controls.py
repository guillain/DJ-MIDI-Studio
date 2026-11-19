"""Your controller on the Mix Together mixer (remote mix, phase 3), Qt-free.

The two volumes, the crossfader and each DJ's EQ and filter knobs (phase 5)
can follow faders or knobs of a real controller: press Learn, move the control, done. Only
continuous controls are learned (a Control Change, or a pitch bend for a
controller whose faders send one); a pad press is ignored, so a stray hit
while learning can't bind a button to a fader.

The assignments live in the workspace (``mix-together-controls.json``), one
trigger per mixer control. Reading the controller never stops it reaching the
DJ software: the mixer only listens.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from djmidi.midi_io import PITCH_BEND

if TYPE_CHECKING:
    from djmidi.midi_io import MidiEvent

_LOGGER = logging.getLogger(__name__)

ME = "me"
THEM = "them"
CROSSFADER = "crossfader"
KNOBS = ("low", "mid", "high", "filter")
# Mixer strips: yours, the first other DJ's, and two more when more DJs join (phase 9).
SIDES = (ME, THEM, "x1", "x2")
GAIN = "gain"  # each strip's trim, above its EQ (the console)
MASTER = "master"  # the program mix's level
EQ_TARGETS = tuple(f"{side}_{knob}" for side in SIDES for knob in (GAIN, *KNOBS))  # "me_gain", "me_low", ...
TARGETS = (*SIDES, CROSSFADER, MASTER, *EQ_TARGETS)
FILE_NAME = "mix-together-controls.json"
FORMAT = "djmidi-mix-controls/1"
_PITCH_MAX = 16383


@dataclass(frozen=True)
class MixerTrigger:
    channel: str
    event_type: str
    control: str

    def label(self) -> str:
        if self.event_type == PITCH_BEND:
            return f"ch{self.channel} pitch bend"
        return f"ch{self.channel} CC {self.control}"


def trigger_from_event(event: MidiEvent) -> MixerTrigger | None:
    """The trigger a moved fader or knob would bind, or None for anything else."""
    if event.direction != "in" or event.event_type not in ("Control Change", PITCH_BEND):
        return None
    return MixerTrigger(event.channel, event.event_type, event.data1)


def value_of(event: MidiEvent) -> float | None:
    """The control's position, 0 (bottom / left) to 1 (top / right)."""
    try:
        raw = int(event.data2)
    except (TypeError, ValueError):
        return None
    top = _PITCH_MAX if event.event_type == PITCH_BEND else 127
    return min(1.0, max(0.0, raw / top))


class MixerControls:
    """Which controller control moves which mixer control."""

    def __init__(self, bindings: dict[str, MixerTrigger] | None = None) -> None:
        self.bindings: dict[str, MixerTrigger] = dict(bindings or {})

    def bind(self, target: str, trigger: MixerTrigger) -> None:
        if target not in TARGETS:
            raise ValueError(target)
        # One control drives one mixer control: learning it elsewhere moves it.
        for other in [key for key, value in self.bindings.items() if value == trigger]:
            del self.bindings[other]
        self.bindings[target] = trigger

    def forget(self, target: str) -> None:
        self.bindings.pop(target, None)

    def moves(self, event: MidiEvent) -> list[tuple[str, float]]:
        """The mixer controls this event moves, with their new position."""
        trigger = trigger_from_event(event)
        if trigger is None:
            return []
        targets = [target for target, bound in self.bindings.items() if bound == trigger]
        value = value_of(event) if targets else None
        return [] if value is None else [(target, value) for target in targets]

    def to_json(self) -> str:
        return json.dumps(
            {
                "format": FORMAT,
                "bindings": {
                    target: {"channel": t.channel, "event_type": t.event_type, "control": t.control}
                    for target, t in self.bindings.items()
                },
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> MixerControls:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ValueError("not a Mix Together controls file")
        bindings = {}
        for target, raw in (data.get("bindings") or {}).items():
            if target in TARGETS and isinstance(raw, dict):
                bindings[target] = MixerTrigger(
                    str(raw.get("channel", "")), str(raw.get("event_type", "")), str(raw.get("control", ""))
                )
        return cls(bindings)

    @classmethod
    def load(cls, path: Path) -> MixerControls:
        try:
            return cls.from_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            _LOGGER.warning("Mix Together controls not read from %s: %s", path, exc)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)
