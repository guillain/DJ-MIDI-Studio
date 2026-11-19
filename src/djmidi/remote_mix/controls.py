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
FX_DELAY, FX_REVERB = "fx_delay", "fx_reverb"  # the console's effects (how much)
EQ_TARGETS = tuple(f"{side}_{knob}" for side in SIDES for knob in (GAIN, *KNOBS))  # "me_gain", "me_low", ...
# Console buttons a pad can press (Note On): each strip's cue, mute (the host's) and crossfader side,
# and the delay's time. A press toggles or steps them, as on a club mixer.
BUTTON_TARGETS = (
    *(f"{side}_cue" for side in SIDES),
    *(f"{side}_mute" for side in SIDES),
    *(f"{side}_xf" for side in SIDES),
    "fx_beats",
)
TARGETS = (*SIDES, CROSSFADER, MASTER, FX_DELAY, FX_REVERB, *EQ_TARGETS, *BUTTON_TARGETS)
FILE_NAME = "mix-together-controls.json"
FORMAT = "djmidi-mix-controls/1"
_PITCH_MAX = 16383


NOTE_ON = "Note On"


@dataclass(frozen=True)
class MixerTrigger:
    channel: str
    event_type: str
    control: str
    port: str = ""  # the controller it came from; "" (older files) = any controller

    def fits(self, other: MixerTrigger) -> bool:
        """The same control: same message, and the same controller when both know theirs
        (an XDJ-XZ and a DDJ-XP2 plugged together can send the same CC)."""
        same = (self.channel, self.event_type, self.control) == (other.channel, other.event_type, other.control)
        return same and (not self.port or not other.port or self.port == other.port)

    def label(self) -> str:
        if self.event_type == PITCH_BEND:
            text = f"ch{self.channel} pitch bend"
        elif self.event_type == NOTE_ON:
            text = f"ch{self.channel} note {self.control}"
        else:
            text = f"ch{self.channel} CC {self.control}"
        return f"{self.port} · {text}" if self.port else text


def trigger_from_event(event: MidiEvent) -> MixerTrigger | None:
    """The trigger a moved fader or knob would bind, or None for anything else."""
    if event.direction != "in" or event.event_type not in ("Control Change", PITCH_BEND):
        return None
    return MixerTrigger(event.channel, event.event_type, event.data1, event.port or "")


def button_from_event(event: MidiEvent) -> MixerTrigger | None:
    """The trigger a pressed pad or button would bind (a Note On with a velocity), else None."""
    if event.direction != "in" or event.event_type != NOTE_ON:
        return None
    try:
        if int(event.data2) == 0:
            return None  # a release
    except (TypeError, ValueError):
        return None
    return MixerTrigger(event.channel, NOTE_ON, event.data1, event.port or "")


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
        for other in [key for key, value in self.bindings.items() if value.fits(trigger)]:
            del self.bindings[other]
        self.bindings[target] = trigger

    def forget(self, target: str) -> None:
        self.bindings.pop(target, None)

    def moves(self, event: MidiEvent) -> list[tuple[str, float]]:
        """The mixer controls this event moves, with their new position."""
        trigger = trigger_from_event(event)
        if trigger is None:
            return []
        targets = [target for target, bound in self.bindings.items() if bound.fits(trigger)]
        value = value_of(event) if targets else None
        return [] if value is None else [(target, value) for target in targets]

    def presses(self, event: MidiEvent) -> list[str]:
        """The console buttons this pad press presses."""
        trigger = button_from_event(event)
        if trigger is None:
            return []
        return [target for target, bound in self.bindings.items() if target in BUTTON_TARGETS and bound.fits(trigger)]

    def to_json(self) -> str:
        return json.dumps(
            {
                "format": FORMAT,
                "bindings": {
                    target: {"channel": t.channel, "event_type": t.event_type, "control": t.control, "port": t.port}
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
                    str(raw.get("channel", "")),
                    str(raw.get("event_type", "")),
                    str(raw.get("control", "")),
                    str(raw.get("port", "") or ""),
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
