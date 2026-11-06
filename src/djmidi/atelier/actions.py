"""Feature actions <-> MIDI messages.

An action names a feature (by its stable id) and a verb, so a macro or a
scene can say "tap Deck 1 PLAY" or "light Pad 3" instead of
``Note On ch 1 note 11 velocity 127``. Two directions, because the same
note means different things depending on who sends it:

- AS_CONTROLLER: what the controller itself would send (simulating it
  towards the DJ software): TAP (press then release), PRESS, RELEASE, and
  VALUE for a CC (a knob, a fader).
- TO_CONTROLLER: what lights it (driving it from a macro or a sync set):
  LED_ON, LED_OFF, LED_VALUE (a velocity, e.g. a pad colour).

`compile_action` turns an action into `controller_sync.SyncMessage`s, the
type macros and sync sets already store and play; `decompile` reads a list
of messages back into actions where a message matches a feature, keeping
any other message as is -- so old macros and sync sets show "in clear"
without being rewritten.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from djmidi.atelier.features import CC, NOTE, Feature, feature_by_id, features_for
from djmidi.controller_sync import SyncMessage
from djmidi.i18n import QT_TRANSLATE_NOOP

AS_CONTROLLER = "as_controller"
TO_CONTROLLER = "to_controller"

TAP = "tap"
PRESS = "press"
RELEASE = "release"
VALUE = "value"
LED_ON = "led_on"
LED_OFF = "led_off"
LED_VALUE = "led_value"

# Readable verb words (the GUI translates them in the "FeatureActions" context).
VERB_LABELS = {
    TAP: QT_TRANSLATE_NOOP("FeatureActions", "tap"),
    PRESS: QT_TRANSLATE_NOOP("FeatureActions", "press"),
    RELEASE: QT_TRANSLATE_NOOP("FeatureActions", "release"),
    VALUE: QT_TRANSLATE_NOOP("FeatureActions", "value"),
    LED_ON: QT_TRANSLATE_NOOP("FeatureActions", "LED on"),
    LED_OFF: QT_TRANSLATE_NOOP("FeatureActions", "LED off"),
    LED_VALUE: QT_TRANSLATE_NOOP("FeatureActions", "LED value"),
}

NOTE_VERBS = (TAP, PRESS, RELEASE, LED_ON, LED_OFF, LED_VALUE)
CC_VERBS = (VALUE,)
_NEEDS_VALUE = {VALUE, LED_VALUE}
_PRESS_VELOCITY = 127


class ActionError(ValueError):
    """An action that doesn't fit its feature (unknown id, a LED verb on a
    CC, a value out of 0-127...)."""


@dataclass(frozen=True)
class FeatureAction:
    feature_id: str
    verb: str
    value: int | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"feature": self.feature_id, "verb": self.verb}
        if self.value is not None:
            data["value"] = self.value
        return data

    @classmethod
    def from_dict(cls, raw: dict) -> FeatureAction:
        value = raw.get("value")
        return cls(str(raw["feature"]), str(raw["verb"]), int(value) if value is not None else None)


def verbs_for(feature: Feature) -> tuple[str, ...]:
    """The verbs that make sense for `feature`: a note can be tapped,
    pressed, released and lit; a CC only takes a value."""
    return NOTE_VERBS if feature.input.kind == NOTE else CC_VERBS


def _check_value(value: int | None, verb: str) -> int:
    if value is None:
        raise ActionError(f"{verb} needs a value (0-127)")
    if not 0 <= value <= 127:
        raise ActionError(f"value {value} is outside 0-127")
    return value


def compile_action(controller: str, action: FeatureAction) -> list[SyncMessage]:
    feature = feature_by_id(controller, action.feature_id)
    if feature is None:
        raise ActionError(f"{controller} has no feature {action.feature_id!r}")
    if action.verb not in verbs_for(feature):
        raise ActionError(f"{action.verb} doesn't apply to {feature.label} ({feature.input.kind})")
    source = feature.input
    if action.verb == VALUE:
        return [SyncMessage("Control Change", source.channel, source.number, _check_value(action.value, VALUE))]
    if action.verb in (TAP, PRESS, RELEASE):
        on = SyncMessage("Note On", source.channel, source.number, _PRESS_VELOCITY)
        off = SyncMessage("Note Off", source.channel, source.number, 0)
        return {TAP: [on, off], PRESS: [on], RELEASE: [off]}[action.verb]
    led = feature.led
    if led is None:
        raise ActionError(f"{feature.label} has no LED")
    velocity = {LED_ON: led.on_value, LED_OFF: led.off_value}.get(action.verb)
    if velocity is None:
        velocity = _check_value(action.value, LED_VALUE)
    return [SyncMessage("Note On", led.channel, led.note, velocity)]


def compile_actions(controller: str, actions: Iterable[FeatureAction]) -> list[SyncMessage]:
    return [message for action in actions for message in compile_action(controller, action)]


def decompile(
    controller: str, messages: Sequence[SyncMessage], direction: str = AS_CONTROLLER
) -> list[FeatureAction | SyncMessage]:
    """`messages` read back as actions wherever one matches a feature of
    `controller`; anything else stays the raw message, in order. A Note On
    immediately followed by its Note Off reads as one TAP."""
    if direction not in (AS_CONTROLLER, TO_CONTROLLER):
        raise ActionError(f"unknown direction {direction!r}")
    by_note: dict[tuple[int, int], Feature] = {}
    by_cc: dict[tuple[int, int], Feature] = {}
    by_led: dict[tuple[int, int], Feature] = {}
    for feature in features_for(controller):
        key = (feature.input.channel, feature.input.number)
        (by_note if feature.input.kind == NOTE else by_cc).setdefault(key, feature)
        if feature.led is not None:
            by_led.setdefault((feature.led.channel, feature.led.note), feature)

    result: list[FeatureAction | SyncMessage] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        key = (message.channel, message.data1)
        action: FeatureAction | None = None
        consumed = 1
        if message.event_type == "Control Change" and key in by_cc:
            action = FeatureAction(by_cc[key].id, VALUE, message.data2)
        elif direction == AS_CONTROLLER and key in by_note:
            feature = by_note[key]
            pressed = message.event_type == "Note On" and message.data2 > 0
            following = messages[index + 1] if index + 1 < len(messages) else None
            if pressed and following is not None and _is_release(following, key):
                action, consumed = FeatureAction(feature.id, TAP), 2
            else:
                action = FeatureAction(feature.id, PRESS if pressed else RELEASE)
        elif direction == TO_CONTROLLER and key in by_led and message.event_type in ("Note On", "Note Off"):
            feature = by_led[key]
            led = feature.led
            velocity = 0 if message.event_type == "Note Off" else message.data2
            if velocity == led.on_value:
                action = FeatureAction(feature.id, LED_ON)
            elif velocity == led.off_value:
                action = FeatureAction(feature.id, LED_OFF)
            else:
                action = FeatureAction(feature.id, LED_VALUE, velocity)
        result.append(action if action is not None else message)
        index += consumed
    return result


def _is_release(message: SyncMessage, key: tuple[int, int]) -> bool:
    if (message.channel, message.data1) != key:
        return False
    return message.event_type == "Note Off" or (message.event_type == "Note On" and message.data2 == 0)


__all__ = [
    "AS_CONTROLLER",
    "CC",
    "CC_VERBS",
    "LED_OFF",
    "LED_ON",
    "LED_VALUE",
    "NOTE_VERBS",
    "PRESS",
    "RELEASE",
    "TAP",
    "TO_CONTROLLER",
    "VALUE",
    "VERB_LABELS",
    "ActionError",
    "FeatureAction",
    "compile_action",
    "compile_actions",
    "decompile",
    "verbs_for",
]
