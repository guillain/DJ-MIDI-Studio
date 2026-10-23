"""MIDI Learn for the mapping editor (issue #220), Qt-free.

The editor's Learn button listens for the next control pressed on a real
controller and reassigns the selected trigger to it. Everything here is pure
model logic, so the GUI layer (`gui/edit_panel.py`) only has to wire a button,
a timeout and a confirmation dialog around it:

- `trigger_from_event` turns a live `MidiEvent` into the trigger it would bind
  (only a press counts: a Note On with velocity > 0, or a Control Change —
  never a release, a velocity-0 Note On, or output-direction LED feedback);
- `find_trigger_conflicts` lists the other `<control>` elements already using
  that trigger, so the editor can warn before creating a clash;
- `describe_conflicts` renders them as short, readable lines;
- `find_parent_control` resolves the `<control>` that owns a selected
  function, since the trigger lives on the control, not on the function.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.model import Control, MappingElement, MidiConfig

#: Words around the function tags in a conflict listing (issue #318).
CONFLICT_DECK = QT_TRANSLATE_NOOP("EditPanel", "deck {deck}")
CONFLICT_MORE = QT_TRANSLATE_NOOP("EditPanel", "… and {count} more")

if TYPE_CHECKING:
    from djmidi.midi_io import MidiEvent

LEARN_TIMEOUT_MS = 10_000
_MAX_CONFLICT_LINES = 8


@dataclass(frozen=True)
class LearnedTrigger:
    channel: str
    event_type: str
    control: str

    def label(self) -> str:
        return f"ch{self.channel} {self.event_type} #{self.control}"


def trigger_of(control: Control) -> LearnedTrigger:
    return LearnedTrigger(control.channel, control.event_type, control.control)


def trigger_from_event(event: MidiEvent) -> LearnedTrigger | None:
    """The trigger a live event would bind, or None when it isn't a press.

    A Note Off (or a Note On with velocity 0, which many controllers send
    instead) is the release of a press already learned, so it is ignored
    rather than learned as a second trigger."""
    if event.direction != "in":
        return None
    if event.event_type == "Note On":
        try:
            if int(event.data2) <= 0:
                return None
        except (TypeError, ValueError):
            return None
    elif event.event_type != "Control Change":
        return None
    return LearnedTrigger(event.channel, event.event_type, event.data1)


def unique_controls(controls: Iterable[Control]) -> list[Control]:
    """Controls deduplicated by identity, keeping order (a MappingGroup can
    list the same `<control>` twice when it holds two matching mappings)."""
    seen: set[int] = set()
    result: list[Control] = []
    for control in controls:
        if id(control) not in seen:
            seen.add(id(control))
            result.append(control)
    return result


def find_trigger_conflicts(
    config: MidiConfig | None, trigger: LearnedTrigger, exclude: Iterable[Control] = ()
) -> list[Control]:
    """Every `<control>` of `config` already on `trigger`, except `exclude`
    (the controls being reassigned — they can't conflict with themselves)."""
    if config is None:
        return []
    excluded = {id(control) for control in exclude}
    return [
        control
        for control in config.controls
        if id(control) not in excluded and trigger_of(control) == trigger
    ]


def describe_conflicts(conflicts: Iterable[Control], translate: Translate = untranslated) -> list[str]:
    """Readable lines naming the functions bound to the conflicting controls,
    deduplicated (Serato repeats each one ~10 times) and capped. The GUI
    passes a `translate` for the words around the Serato function tags."""
    lines: list[str] = []
    for control in conflicts:
        for userio in control.userios:
            for mapping in userio.mappings:
                deck = " " + translate(CONFLICT_DECK).format(deck=mapping.deck_id) if mapping.deck_id else ""
                line = f"{mapping.tag}{deck} [{userio.event}]"
                if line not in lines:
                    lines.append(line)
    if len(lines) > _MAX_CONFLICT_LINES:
        hidden = len(lines) - _MAX_CONFLICT_LINES
        lines = [*lines[:_MAX_CONFLICT_LINES], translate(CONFLICT_MORE).format(count=hidden)]
    return lines


def find_parent_control(config: MidiConfig | None, mapping: MappingElement) -> Control | None:
    if config is None:
        return None
    for control in config.controls:
        for userio in control.userios:
            if any(candidate is mapping for candidate in userio.mappings):
                return control
    return None
