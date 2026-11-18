"""A controller's target LED state (Atelier, issue #413, step 4).

A sync set is a list of messages sent to a controller; for its LEDs, what
matters is the state they leave it in. `Scene` reads a sync set as that
state -- one LED value per feature (`atelier.features`) -- edits it, and
writes it back as messages. Messages that aren't an LED of this controller
are kept, in place: a scene never drops what it doesn't understand.

Reading collapses repeats: when a set lights the same LED twice, the scene
keeps the first message's position and the last one's value, which is the
state the controller ends up in.

A scene can also be played *to the DJ software* (`software_taps`): a lit LED
then stands for "this function on", sent as a tap of its button through a
virtual port the DJ software has learned, so the software changes state and
lights its own LEDs. Qt-free.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from djmidi.atelier.actions import (
    LED_OFF,
    LED_ON,
    LED_VALUE,
    TAP,
    TO_CONTROLLER,
    FeatureAction,
    compile_action,
    decompile,
)
from djmidi.atelier.features import NOTE, Feature, feature_by_id
from djmidi.controller_sync import ControllerSyncSet, SyncMessage, normalize_scene

_LED_VERBS = {LED_ON, LED_OFF, LED_VALUE}


@dataclass
class Scene:
    controller: str
    # In message order: a feature id (an LED this scene sets) or a raw
    # message kept as is.
    items: list[str | SyncMessage] = field(default_factory=list)
    values: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_messages(cls, controller: str, messages: Iterable[SyncMessage]) -> Scene:
        scene = cls(controller)
        messages = list(messages)
        # Towards the controller, decompile reads one item per message. Only LED
        # actions become scene lights; anything else (a Control Change that
        # matches one of the controller's knobs, say) stays the raw message.
        for item, message in zip(decompile(controller, messages, TO_CONTROLLER), messages, strict=True):
            if isinstance(item, FeatureAction) and item.verb in _LED_VERBS:
                scene.set_led(item.feature_id, _value(controller, item))
            else:
                scene.items.append(message)
        return scene

    @classmethod
    def from_sync_set(cls, sync_set: ControllerSyncSet | None, controller: str) -> Scene:
        return cls.from_messages(controller, sync_set.messages if sync_set is not None else ())

    def led_value(self, feature_id: str) -> int | None:
        """The value this scene gives that LED, None when it leaves it alone."""
        return self.values.get(feature_id)

    def set_led(self, feature_id: str, value: int | None) -> None:
        """Sets an LED (0 = off, the feature's on value = on, else a raw
        value such as a colour), or with None removes it from the scene."""
        if value is None:
            if self.values.pop(feature_id, None) is not None:
                self.items.remove(feature_id)
            return
        if not 0 <= value <= 127:
            raise ValueError(f"LED value {value} is outside 0-127")
        if feature_id not in self.values:
            self.items.append(feature_id)
        self.values[feature_id] = value

    def clear(self) -> None:
        """Forgets every LED; raw messages are kept."""
        self.items = [item for item in self.items if not isinstance(item, str)]
        self.values.clear()

    @property
    def lit(self) -> dict[str, int]:
        """Every LED this scene sets, in message order."""
        return {item: self.values[item] for item in self.items if isinstance(item, str)}

    @property
    def raw_messages(self) -> list[SyncMessage]:
        return [item for item in self.items if isinstance(item, SyncMessage)]

    def messages(self) -> tuple[SyncMessage, ...]:
        result: list[SyncMessage] = []
        for item in self.items:
            if isinstance(item, SyncMessage):
                result.append(item)
                continue
            feature = feature_by_id(self.controller, item)
            if feature is None:  # the controller's profile lost it: drop the stale entry
                continue
            result.extend(compile_action(self.controller, _action(feature, self.values[item])))
        return tuple(result)

    def software_taps(self) -> tuple[SyncMessage, ...]:
        """The scene as button taps for the DJ software: one tap (press then
        release) of each button whose LED the scene lights, in scene order.
        An LED set off, a knob or fader (CC), a feature the profile lost and
        the raw messages are left out. A tap toggles: the software must be in
        the state the scene starts from."""
        result: list[SyncMessage] = []
        for feature_id, value in self.lit.items():
            feature = feature_by_id(self.controller, feature_id)
            if feature is None or feature.input.kind != NOTE:
                continue
            off = feature.led.off_value if feature.led is not None else 0
            if value == off:
                continue
            result.extend(compile_action(self.controller, FeatureAction(feature_id, TAP)))
        return tuple(result)

    def software_sync_set(self, output_port: str, scene: str | None = None) -> ControllerSyncSet:
        """The taps as a set aimed at ``output_port`` (the DJ software's
        virtual port); never stored."""
        return ControllerSyncSet(
            self.controller, output_port=output_port, messages=self.software_taps(), scene=normalize_scene(scene)
        )

    def to_sync_set(self, existing: ControllerSyncSet | None, scene: str | None = None) -> ControllerSyncSet:
        """The sync set to store: ``existing``'s port and scene kept (a new
        set for this controller otherwise) with this scene's messages."""
        if existing is not None:
            return existing.with_messages(self.messages())
        return ControllerSyncSet(self.controller, messages=self.messages(), scene=normalize_scene(scene))


@dataclass(frozen=True)
class SceneCoverage:
    """One controller a sync scene covers (issue #427): it has a stored set
    for that scene, unsaved Atelier edits, or both."""

    controller: str
    saved: bool
    unsaved: bool


def scene_coverage(
    controllers: Iterable[str],
    scene: str,
    stored: Callable[[str, str], ControllerSyncSet | None],
    unsaved: Iterable[str] = (),
) -> list[SceneCoverage]:
    """The controllers ``scene`` covers, in ``controllers`` order."""
    pending = set(unsaved)
    result = []
    for controller in controllers:
        saved = stored(controller, scene) is not None
        if saved or controller in pending:
            result.append(SceneCoverage(controller, saved, controller in pending))
    return result


def _value(controller: str, action: FeatureAction) -> int:
    if action.verb == LED_VALUE and action.value is not None:
        return action.value
    feature = feature_by_id(controller, action.feature_id)
    led = feature.led if feature is not None else None
    if action.verb == LED_ON:
        return led.on_value if led is not None else 127
    return led.off_value if led is not None else 0


def _action(feature: Feature, value: int) -> FeatureAction:
    led = feature.led
    if led is not None and value == led.on_value:
        return FeatureAction(feature.id, LED_ON)
    if led is not None and value == led.off_value:
        return FeatureAction(feature.id, LED_OFF)
    return FeatureAction(feature.id, LED_VALUE, value)


__all__ = ["Scene", "SceneCoverage", "scene_coverage"]
