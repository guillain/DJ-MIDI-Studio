"""Atelier step 1 (issue #413): the feature model and feature actions."""

import dataclasses

import pytest

from djmidi import catalog
from djmidi.atelier import (
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
    feature_by_id,
    feature_for_message,
    features_for,
)
from djmidi.atelier.actions import ActionError, verbs_for
from djmidi.catalog import _registry
from djmidi.controller_sync import SyncMessage

# The maintainer's own controllers (decision 5 of issue #413).
OWN = ["XDJ-XZ", "DDJ-XP2", "Behringer CMD LC-1", "Behringer CMD Micro", "Behringer CMD Studio 4a", "Korg nanoPAD2"]


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


@pytest.mark.parametrize("controller", OWN)
def test_every_own_controller_has_features_with_unique_readable_ids(controller):
    features = features_for(controller)
    assert features
    ids = [feature.id for feature in features]
    assert len(ids) == len(set(ids))
    for feature in features:
        assert feature.id == feature.id.strip() and " " not in feature.id
        assert "@" in feature.id and feature.id.endswith(f"@{feature.input.channel}") or "#" in feature.id
        assert feature.kind in {"button", "pad", "knob", "fader", "jog"}


@pytest.mark.parametrize("controller", OWN)
def test_every_feature_is_found_back_from_its_own_message(controller):
    for feature in features_for(controller):
        event = "Control Change" if feature.input.kind == "CC" else "Note On"
        found = feature_for_message(controller, event, feature.input.channel, feature.input.number)
        assert found == feature


def test_symbol_names_get_readable_ids():
    ids = {feature.name: feature.id for feature in features_for("Behringer CMD Studio 4a")}
    assert ids["<"] == "browse.lt@1"
    assert ids[">"] == "browse.gt@1"


def test_decks_layers_and_pad_banks():
    xp2 = features_for("DDJ-XP2")
    pad = next(f for f in xp2 if f.name == "Deck 1 Pad 3 (PAD MODE 2)")
    assert (pad.kind, pad.deck, pad.bank, pad.shift) == ("pad", 1, "PAD MODE 2", False)
    shifted = next(f for f in xp2 if f.name == "Deck 1 Pad 3 (PAD MODE 2) +SHIFT")
    assert shifted.shift is True
    micro = {f.name: f for f in features_for("Behringer CMD Micro")}
    assert micro["Deck A SYNC"].deck == 1
    beat_loop = [f for f in xp2 if f.name == "4 BEAT LOOP"]
    assert sorted(f.deck for f in beat_loop) == [1, 2, 3, 4]


def test_a_note_feature_has_an_assumed_unverified_led_a_cc_none():
    feature = features_for("XDJ-XZ")[0]
    assert feature.input.kind == "NOTE"
    assert (feature.led.channel, feature.led.note) == (feature.input.channel, feature.input.number)
    assert feature.led.verified is False and "assumed" in feature.led.source
    cc = _any_cc_feature()
    if cc is not None:
        assert cc[1].led is None


def _any_cc_feature():
    for controller in catalog.CONTROLLER_NAMES:
        for feature in features_for(controller):
            if feature.input.kind == "CC":
                return controller, feature
    return None


# --- actions --------------------------------------------------------------


def _sync(controller):
    return next(f for f in features_for(controller) if "SYNC" in f.name and not f.shift)


def test_tap_press_release_compile_to_note_on_and_off():
    feature = _sync("DDJ-XP2")
    channel, note = feature.input.channel, feature.input.number
    on = SyncMessage("Note On", channel, note, 127)
    off = SyncMessage("Note Off", channel, note, 0)
    assert compile_action("DDJ-XP2", FeatureAction(feature.id, TAP)) == [on, off]
    assert compile_action("DDJ-XP2", FeatureAction(feature.id, PRESS)) == [on]
    assert compile_action("DDJ-XP2", FeatureAction(feature.id, RELEASE)) == [off]


def test_led_actions_compile_to_note_on_velocities():
    feature = _sync("XDJ-XZ")
    led = feature.led
    assert compile_action("XDJ-XZ", FeatureAction(feature.id, LED_ON)) == [
        SyncMessage("Note On", led.channel, led.note, 127)
    ]
    assert compile_action("XDJ-XZ", FeatureAction(feature.id, LED_OFF)) == [
        SyncMessage("Note On", led.channel, led.note, 0)
    ]
    assert compile_action("XDJ-XZ", FeatureAction(feature.id, LED_VALUE, 42)) == [
        SyncMessage("Note On", led.channel, led.note, 42)
    ]


def test_actions_round_trip_through_messages_in_both_directions():
    feature = _sync("DDJ-XP2")
    simulated = [FeatureAction(feature.id, PRESS), FeatureAction(feature.id, TAP)]
    assert decompile("DDJ-XP2", compile_actions("DDJ-XP2", simulated), AS_CONTROLLER) == simulated
    release = [FeatureAction(feature.id, RELEASE)]
    assert decompile("DDJ-XP2", compile_actions("DDJ-XP2", release), AS_CONTROLLER) == release
    # A press right before its release is the same two messages as a tap.
    pair = [FeatureAction(feature.id, PRESS), FeatureAction(feature.id, RELEASE)]
    assert decompile("DDJ-XP2", compile_actions("DDJ-XP2", pair)) == [FeatureAction(feature.id, TAP)]
    lights = [
        FeatureAction(feature.id, LED_ON),
        FeatureAction(feature.id, LED_VALUE, 42),
        FeatureAction(feature.id, LED_OFF),
    ]
    assert decompile("DDJ-XP2", compile_actions("DDJ-XP2", lights), TO_CONTROLLER) == lights


def test_a_cc_feature_takes_a_value_only():
    found = _any_cc_feature()
    if found is None:
        pytest.skip("no registered controller has a CC entry")
    controller, feature = found
    assert verbs_for(feature) == (VALUE,)
    [message] = compile_action(controller, FeatureAction(feature.id, VALUE, 64))
    assert (message.event_type, message.data2) == ("Control Change", 64)
    assert decompile(controller, [message]) == [FeatureAction(feature.id, VALUE, 64)]
    with pytest.raises(ActionError):
        compile_action(controller, FeatureAction(feature.id, LED_ON))


def test_unknown_messages_are_kept_and_a_zero_velocity_note_on_is_a_release():
    feature = _sync("DDJ-XP2")
    stranger = SyncMessage("Note On", 16, 127, 1)
    zero = SyncMessage("Note On", feature.input.channel, feature.input.number, 0)
    assert decompile("DDJ-XP2", [stranger, zero]) == [stranger, FeatureAction(feature.id, RELEASE)]


def test_bad_actions_are_refused():
    feature = _sync("DDJ-XP2")
    with pytest.raises(ActionError):
        compile_action("DDJ-XP2", FeatureAction("deck.no-such-control@1", TAP))
    with pytest.raises(ActionError):
        compile_action("DDJ-XP2", FeatureAction(feature.id, VALUE, 10))
    with pytest.raises(ActionError):
        compile_action("DDJ-XP2", FeatureAction(feature.id, LED_VALUE, 200))
    with pytest.raises(ActionError):
        compile_action("DDJ-XP2", FeatureAction(feature.id, LED_VALUE))


def test_actions_serialize_to_plain_dicts():
    action = FeatureAction("deck.beat-sync@1", LED_VALUE, 42)
    assert action.to_dict() == {"feature": "deck.beat-sync@1", "verb": "led_value", "value": 42}
    assert FeatureAction.from_dict(action.to_dict()) == action
    assert FeatureAction.from_dict({"feature": "x@1", "verb": "tap"}).value is None


def test_a_re_registered_controller_is_rebuilt_not_served_stale():
    original = catalog.get_definition("Behringer CMD LC-1")
    before = features_for("Behringer CMD LC-1")
    trimmed = dataclasses.replace(original, static_entries=original.static_entries[:3])
    _registry.register(trimmed, replace=True)
    try:
        assert len(features_for("Behringer CMD LC-1")) == 3
    finally:
        _registry.register(original, replace=True)
    assert features_for("Behringer CMD LC-1") == before
    assert feature_by_id("Behringer CMD LC-1", before[0].id) == before[0]
