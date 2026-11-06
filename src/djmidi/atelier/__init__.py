"""The Atelier (issue #413): work on a controller's own features -- Deck 1
PLAY, Pad 3 in HOT CUE mode, its LED -- instead of raw note / channel / data
numbers. Qt-free: `features` models each control, `actions` turns feature
actions into MIDI messages and back. The GUI comes in later steps.
"""

from djmidi.atelier.actions import (
    AS_CONTROLLER,
    LED_OFF,
    LED_ON,
    LED_VALUE,
    PRESS,
    RELEASE,
    TAP,
    TO_CONTROLLER,
    VALUE,
    FeatureAction,
    compile_action,
    compile_actions,
    decompile,
)
from djmidi.atelier.features import (
    Feature,
    FeatureInput,
    LedOutput,
    feature_by_id,
    feature_for_message,
    features_for,
)

__all__ = [
    "AS_CONTROLLER",
    "LED_OFF",
    "LED_ON",
    "LED_VALUE",
    "PRESS",
    "RELEASE",
    "TAP",
    "TO_CONTROLLER",
    "VALUE",
    "Feature",
    "FeatureAction",
    "FeatureInput",
    "LedOutput",
    "compile_action",
    "compile_actions",
    "decompile",
    "feature_by_id",
    "feature_for_message",
    "features_for",
]
