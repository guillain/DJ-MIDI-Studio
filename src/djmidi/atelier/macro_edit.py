"""Editing a macro's steps from a controller's photo (Atelier, issue #428).

The Atelier's Macros tab clicks controls instead of typing messages. Which
controller and which direction a macro is about is `describe.macro_target`'s
rule (a controller output port drives its LEDs; else `MidiMacro.simulates`
imitates its presses); this module turns a clicked feature and a verb into
steps, edits the step list (reorder, remove, delay) and words each step.
Qt-free: every function returns a new macro, never mutates one.
"""

from __future__ import annotations

from dataclasses import replace

from djmidi.atelier.actions import (
    LED_OFF,
    LED_ON,
    LED_VALUE,
    NOTE,
    PRESS,
    RELEASE,
    TAP,
    TO_CONTROLLER,
    VALUE,
    FeatureAction,
    compile_action,
)
from djmidi.atelier.describe import describe_message, feature_name, macro_target
from djmidi.atelier.features import Feature, feature_for_message
from djmidi.controller_sync import SyncMessage
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.midi_macros import (
    MAX_DELAY_MS,
    MacroStep,
    MidiMacro,
    annotate_with_features,
)

LED_VERBS = (LED_ON, LED_OFF, LED_VALUE)
PRESS_VERBS = (TAP, PRESS, RELEASE)
VALUE_VERBS = (VALUE,)
VALUED_VERBS = frozenset({LED_VALUE, VALUE})

_RAW = QT_TRANSLATE_NOOP("MacroEdit", "{type} · ch {channel} · {data1} = {data2}")
_WAIT = QT_TRANSLATE_NOOP("MacroEdit", "Wait for {step}")
_DELAY = QT_TRANSLATE_NOOP("MacroEdit", "after {delay} ms")
_WAIT_UP_TO = QT_TRANSLATE_NOOP("MacroEdit", "Wait for {step} (at most {delay} ms)")


def verbs_for(feature: Feature, direction: str) -> tuple[str, ...]:
    """What a click on `feature` can add: LED verbs when the macro drives
    the controller (none for a control without LED), presses or a value
    when it imitates the controller."""
    if direction == TO_CONTROLLER:
        return LED_VERBS if feature.led is not None else ()
    return PRESS_VERBS if feature.input.kind == NOTE else VALUE_VERBS


def steps_for(controller: str, feature: Feature, verb: str, value: int | None = None) -> list[MacroStep]:
    """The steps a click adds (a tap is two: press then release)."""
    action = FeatureAction(feature.id, verb, value if verb in VALUED_VERBS else None)
    return [MacroStep(message) for message in compile_action(controller, action)]


def steps_of(macro: MidiMacro, alternate: bool = False) -> tuple[MacroStep, ...]:
    """The main steps, or a toggle's second list (issue #435)."""
    return macro.alternate_steps if alternate else macro.steps


def _with(macro: MidiMacro, steps: list[MacroStep], alternate: bool) -> MidiMacro:
    return replace(macro, alternate_steps=tuple(steps)) if alternate else replace(macro, steps=tuple(steps))


def wait_step_for(feature: Feature, timeout_ms: int = 0) -> MacroStep:
    """A wait for a press of `feature` (issue #435): the macro pauses until
    that note or CC arrives on any input, at most `timeout_ms` (0 = the
    longest wait). Same shape as the macro editor's wait rows (value 0)."""
    event_type = "Note On" if feature.input.kind == NOTE else "Control Change"
    message = SyncMessage(event_type, feature.input.channel, feature.input.number, 0)
    return MacroStep(message, timeout_ms, wait=True)


def append_steps(macro: MidiMacro, steps: list[MacroStep], alternate: bool = False) -> MidiMacro:
    return annotate_with_features(_with(macro, [*steps_of(macro, alternate), *steps], alternate))


def remove_step(macro: MidiMacro, index: int, alternate: bool = False) -> MidiMacro:
    steps = list(steps_of(macro, alternate))
    del steps[index]
    return _with(macro, steps, alternate)


def move_step(macro: MidiMacro, index: int, offset: int, alternate: bool = False) -> tuple[MidiMacro, int]:
    """The macro with step `index` moved by `offset` (clamped), and its new index."""
    steps = list(steps_of(macro, alternate))
    target = max(0, min(len(steps) - 1, index + offset))
    steps.insert(target, steps.pop(index))
    return _with(macro, steps, alternate), target


def set_delay(macro: MidiMacro, index: int, delay_ms: int, alternate: bool = False) -> MidiMacro:
    """The delay before a step -- for a wait step, its timeout (0 = longest)."""
    if not 0 <= delay_ms <= MAX_DELAY_MS:
        raise ValueError(f"delay {delay_ms} ms is outside 0-{MAX_DELAY_MS}")
    steps = list(steps_of(macro, alternate))
    steps[index] = replace(steps[index], delay_ms=delay_ms)
    return _with(macro, steps, alternate)


def describe_step(macro: MidiMacro, step: MacroStep, translate: Translate = untranslated) -> str:
    """One step in words: the control and what it does when the macro's
    target knows it, else the raw message; plus the delay before it."""
    message = step.message
    text = None
    target = macro_target(macro.output_port, macro.simulates)
    if target is not None and step.wait:
        # A wait is for a press of a control, whatever value it is stored with.
        feature = feature_for_message(target[0], message.event_type, message.channel, message.data1)
        text = feature_name(feature, translate) if feature is not None else None
    elif target is not None:
        text = describe_message(target[0], message, target[1], translate)
    if text is None:
        text = translate(_RAW).format(
            type=message.event_type, channel=message.channel, data1=message.data1, data2=message.data2
        )
    if step.wait:
        if step.delay_ms:
            return translate(_WAIT_UP_TO).format(step=text, delay=step.delay_ms)
        return translate(_WAIT).format(step=text)
    if step.delay_ms:
        return f"{text} · {translate(_DELAY).format(delay=step.delay_ms)}"
    return text


__all__ = [
    "LED_VERBS",
    "PRESS_VERBS",
    "VALUED_VERBS",
    "VALUE_VERBS",
    "append_steps",
    "describe_step",
    "move_step",
    "remove_step",
    "set_delay",
    "steps_for",
    "steps_of",
    "verbs_for",
    "wait_step_for",
]
