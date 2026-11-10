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
    AS_CONTROLLER,
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
from djmidi.atelier.describe import describe_message, macro_target
from djmidi.atelier.features import Feature
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


def append_steps(macro: MidiMacro, steps: list[MacroStep]) -> MidiMacro:
    return annotate_with_features(replace(macro, steps=(*macro.steps, *steps)))


def remove_step(macro: MidiMacro, index: int) -> MidiMacro:
    steps = list(macro.steps)
    del steps[index]
    return replace(macro, steps=tuple(steps))


def move_step(macro: MidiMacro, index: int, offset: int) -> tuple[MidiMacro, int]:
    """The macro with step `index` moved by `offset` (clamped), and its new index."""
    steps = list(macro.steps)
    target = max(0, min(len(steps) - 1, index + offset))
    steps.insert(target, steps.pop(index))
    return replace(macro, steps=tuple(steps)), target


def set_delay(macro: MidiMacro, index: int, delay_ms: int) -> MidiMacro:
    if not 0 <= delay_ms <= MAX_DELAY_MS:
        raise ValueError(f"delay {delay_ms} ms is outside 0-{MAX_DELAY_MS}")
    steps = list(macro.steps)
    steps[index] = replace(steps[index], delay_ms=delay_ms)
    return replace(macro, steps=tuple(steps))


def describe_step(macro: MidiMacro, step: MacroStep, translate: Translate = untranslated) -> str:
    """One step in words: the control and what it does when the macro's
    target knows it, else the raw message; plus the delay before it."""
    message = step.message
    text = None
    target = macro_target(macro.output_port, macro.simulates)
    if target is not None:
        controller, direction = target
        text = describe_message(controller, message, AS_CONTROLLER if step.wait else direction, translate)
    if text is None:
        text = translate(_RAW).format(
            type=message.event_type, channel=message.channel, data1=message.data1, data2=message.data2
        )
    if step.wait:
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
    "verbs_for",
]
