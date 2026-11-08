"""A controller's target LED state (Atelier, issue #413, step 4).

A sync set is a list of messages sent to a controller; for its LEDs, what
matters is the state they leave it in. `Scene` reads a sync set as that
state -- one LED value per feature (`atelier.features`) -- edits it, and
writes it back as messages. Messages that aren't an LED of this controller
are kept, in place: a scene never drops what it doesn't understand.

Reading collapses repeats: when a set lights the same LED twice, the scene
keeps the first message's position and the last one's value, which is the
state the controller ends up in. Qt-free.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from djmidi.atelier.actions import (
    LED_OFF,
    LED_ON,
    LED_VALUE,
    TO_CONTROLLER,
    FeatureAction,
    compile_action,
    decompile,
)
from djmidi.atelier.features import Feature, feature_by_id
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
        for item in decompile(controller, list(messages), TO_CONTROLLER):
            if isinstance(item, FeatureAction) and item.verb in _LED_VERBS:
                scene.set_led(item.feature_id, _value(controller, item))
            else:
                scene.items.append(item)
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

    def to_sync_set(self, existing: ControllerSyncSet | None, scene: str | None = None) -> ControllerSyncSet:
        """The sync set to store: ``existing``'s port and scene kept (a new
        set for this controller otherwise) with this scene's messages."""
        if existing is not None:
            return existing.with_messages(self.messages())
        return ControllerSyncSet(self.controller, messages=self.messages(), scene=normalize_scene(scene))


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


__all__ = ["Scene"]
