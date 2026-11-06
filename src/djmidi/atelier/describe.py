"""Readable names for raw MIDI steps (issue #413, step 3, first slice).

A macro or sync set stores raw messages; when they go to a controller this
module names them by the controller's own features -- "BEAT SYNC: LED on"
-- so existing files read "in clear" without being rewritten. Qt-free; the
GUI passes a `translate` for the verb words.
"""

from __future__ import annotations

from djmidi import catalog
from djmidi.atelier.actions import (
    AS_CONTROLLER,
    TO_CONTROLLER,
    VERB_LABELS,
    FeatureAction,
    decompile,
)
from djmidi.atelier.features import feature_by_id
from djmidi.controller_sync import SyncMessage
from djmidi.i18n import Translate, untranslated

_EXACT_PORT_SCORE = 100


def controller_for_port(port: str) -> str | None:
    """The one controller a MIDI port name names exactly (its name or one of
    its port names), else None -- a loopback bus or an unknown device names
    no controller, and two exact matches are left undecided."""
    if not port.strip():
        return None
    exact = [match for match in catalog.detect_controller(port, include_disabled=True) if match.score >= _EXACT_PORT_SCORE]
    return exact[0].controller.name if len(exact) == 1 else None


def macro_target(output_port: str, simulates: str = "") -> tuple[str, str] | None:
    """Which controller a macro's steps are about, and in which direction --
    the one rule the editor, the step dialog and the stored step features
    all follow:

    - the output port is a known controller: the macro drives it
      (``TO_CONTROLLER``: its LEDs);
    - else `simulates` names a registered controller: the macro imitates
      that controller's presses towards the DJ software through a virtual
      port (``AS_CONTROLLER``);
    - else None: the steps are plain MIDI.
    """
    controller = controller_for_port(output_port)
    if controller is not None:
        return controller, TO_CONTROLLER
    if simulates and simulates in {definition.name for definition in catalog.all_controller_definitions()}:
        return simulates, AS_CONTROLLER
    return None


def describe_action(controller: str, action: FeatureAction, translate: Translate = untranslated) -> str | None:
    feature = feature_by_id(controller, action.feature_id)
    if feature is None:
        return None
    verb = translate(VERB_LABELS.get(action.verb, action.verb))
    if action.value is not None:
        verb = f"{verb} {action.value}"
    return f"{feature.label}: {verb}"


def describe_message(
    controller: str, message: SyncMessage, direction: str = TO_CONTROLLER, translate: Translate = untranslated
) -> str | None:
    """`message` named by `controller`'s feature, or None when it matches none."""
    [item] = decompile(controller, [message], direction)
    if not isinstance(item, FeatureAction):
        return None
    return describe_action(controller, item, translate)


__all__ = ["controller_for_port", "describe_action", "describe_message", "macro_target"]
