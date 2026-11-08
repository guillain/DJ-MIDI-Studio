"""Atelier step 3 (issue #413): simulation macros -- a controller's presses
sent towards the DJ software through a port that is no controller."""

import dataclasses

import pytest

from djmidi import catalog
from djmidi.atelier.actions import (
    AS_CONTROLLER,
    PRESS,
    RELEASE,
    TAP,
    TO_CONTROLLER,
    VALUE,
    FeatureAction,
    FeatureRef,
)
from djmidi.atelier.describe import macro_target
from djmidi.atelier.features import features_for
from djmidi.controller_sync import SyncMessage
from djmidi.gui.feature_step_dialog import FeatureStepDialog
from djmidi.gui.macro_editor import MacroManagerDialog
from djmidi.midi_macros import MacroStep, MidiMacro, annotate_with_features

IAC = "IAC Driver Bus 1"
SYNC_ID = "deck.beat-sync@1"  # DDJ-XP2 deck 1 BEAT SYNC: note 88, channel 1
SYNC_ON = SyncMessage("Note On", 1, 88, 127)
SYNC_OFF = SyncMessage("Note Off", 1, 88, 0)


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def _a_cc_feature():
    for controller in catalog.CONTROLLER_NAMES:
        for feature in features_for(controller):
            if feature.input.kind == "CC":
                return controller, feature
    pytest.skip("no registered controller has a CC entry")


def test_simulates_round_trips_and_is_only_written_when_set():
    plain = MidiMacro("m", IAC, (MacroStep(SYNC_ON),))
    assert "simulates" not in plain.to_dict()
    simulating = dataclasses.replace(plain, simulates="DDJ-XP2")
    assert simulating.to_dict()["simulates"] == "DDJ-XP2"
    assert MidiMacro.from_dict(simulating.to_dict()) == simulating
    unknown = MidiMacro.from_dict({**plain.to_dict(), "simulates": "Some Unknown Box"})
    assert unknown.simulates == "Some Unknown Box"  # kept as written


def test_the_direction_rule():
    assert macro_target("DDJ-XP2", simulates="XDJ-XZ") == ("DDJ-XP2", TO_CONTROLLER)  # the port wins
    assert macro_target(IAC, simulates="DDJ-XP2") == ("DDJ-XP2", AS_CONTROLLER)
    assert macro_target(IAC) is None
    assert macro_target(IAC, simulates="Some Unknown Box") is None


def test_simulation_steps_are_annotated_as_presses_and_values_and_cleared_otherwise():
    macro = MidiMacro("m", IAC, (MacroStep(SYNC_ON), MacroStep(SYNC_OFF)), simulates="DDJ-XP2")
    annotated = annotate_with_features(macro)
    assert [step.feature for step in annotated.steps] == [
        FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, PRESS)),
        FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, RELEASE)),
    ]
    assert MidiMacro.from_dict(annotated.to_dict()) == annotated
    plain = annotate_with_features(dataclasses.replace(annotated, simulates=""))
    assert all(step.feature is None for step in plain.steps)

    controller, cc = _a_cc_feature()
    message = SyncMessage("Control Change", cc.input.channel, cc.input.number, 64)
    valued = annotate_with_features(MidiMacro("cc", IAC, (MacroStep(message),), simulates=controller))
    assert valued.steps[0].feature == FeatureRef(controller, FeatureAction(cc.id, VALUE, 64))


def test_the_editor_reads_a_simulation_macro_as_presses():
    macro = MidiMacro("m", IAC, (MacroStep(SYNC_ON), MacroStep(SYNC_OFF)), simulates="DDJ-XP2")
    dialog = MacroManagerDialog([macro], [IAC, "DDJ-XP2"])
    assert dialog.simulates_combo.currentData() == "DDJ-XP2"
    assert not dialog.simulates_combo.isHidden()
    assert dialog.feature_text(0) == "BEAT SYNC: press"
    assert dialog.feature_text(1) == "BEAT SYNC: release"
    assert dialog.add_feature_button.isEnabled()
    edited = dialog._edited()
    assert edited.simulates == "DDJ-XP2"
    assert edited.steps[0].feature == FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, PRESS))
    dialog.simulates_combo.setCurrentIndex(0)  # none: plain MIDI
    assert dialog.feature_text(0) == ""
    assert not dialog.add_feature_button.isEnabled()
    dialog.port_combo.setCurrentText("DDJ-XP2")  # a controller port: the simulation row hides
    assert dialog.simulates_combo.isHidden()
    assert dialog.feature_text(0) == "BEAT SYNC: LED on"


def test_the_step_dialog_in_simulation_mode():
    dialog = FeatureStepDialog("DDJ-XP2", None, AS_CONTROLLER)
    assert dialog.select(SYNC_ID)
    verbs = [dialog.verb_combo.itemData(index) for index in range(dialog.verb_combo.count())]
    assert verbs == [TAP, PRESS, RELEASE]
    assert dialog.steps() == [MacroStep(SYNC_ON), MacroStep(SYNC_OFF)]  # a tap is two steps
    dialog.verb_combo.setCurrentIndex(dialog.verb_combo.findData(PRESS))
    assert dialog.steps() == [MacroStep(SYNC_ON)]

    controller, cc = _a_cc_feature()
    cc_dialog = FeatureStepDialog(controller, None, AS_CONTROLLER)
    cc_dialog.filter_edit.setText("")
    assert cc_dialog.select(cc.id)
    assert [cc_dialog.verb_combo.itemData(index) for index in range(cc_dialog.verb_combo.count())] == [VALUE]
    assert cc_dialog.value_spin.isEnabled()
    cc_dialog.value_spin.setValue(90)
    [step] = cc_dialog.steps()
    assert (step.message.event_type, step.message.data2) == ("Control Change", 90)


def test_the_led_mode_is_unchanged_by_default():
    dialog = FeatureStepDialog("DDJ-XP2")
    assert all(dialog.feature_list.item(row).toolTip() for row in range(min(5, dialog.feature_list.count())))
    verbs = [dialog.verb_combo.itemData(index) for index in range(dialog.verb_combo.count())]
    assert verbs == ["led_on", "led_off", "led_value"]
