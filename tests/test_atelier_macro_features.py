"""Atelier step 3, second slice (issue #413): macro steps built from and
stored with controller features."""

import dataclasses

import pytest
from PySide6.QtWidgets import QDialog

from djmidi import catalog
from djmidi.atelier.actions import LED_ON, LED_VALUE, FeatureAction, FeatureRef
from djmidi.catalog import _registry
from djmidi.controller_sync import SyncMessage
from djmidi.gui.feature_step_dialog import FeatureStepDialog
from djmidi.gui.macro_editor import MacroManagerDialog
from djmidi.midi_macros import MacroStep, MidiMacro, annotate_with_features

SYNC_ID = "deck.beat-sync@1"  # DDJ-XP2 deck 1 BEAT SYNC, note 88 on channel 1
SYNC_LED = SyncMessage("Note On", 1, 88, 127)


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def test_a_feature_ref_round_trips_and_resolves_to_one_message():
    ref = FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, LED_ON))
    assert ref.to_dict() == {"controller": "DDJ-XP2", "feature": SYNC_ID, "verb": "led_on"}
    assert FeatureRef.from_dict(ref.to_dict()) == ref
    assert ref.resolve() == SYNC_LED
    assert FeatureRef("Nope", FeatureAction(SYNC_ID, LED_ON)).resolve() is None
    assert FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, "tap")).resolve() is None  # two messages
    with pytest.raises(ValueError):
        FeatureRef.from_dict({"controller": "DDJ-XP2"})


def test_annotation_follows_the_output_port():
    wait = MacroStep(SYNC_LED, 0, wait=True)
    stranger = MacroStep(SyncMessage("Control Change", 16, 120, 5))
    macro = annotate_with_features(MidiMacro("m", "DDJ-XP2", (MacroStep(SYNC_LED), wait, stranger)))
    assert [step.feature for step in macro.steps] == [
        FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, LED_ON)),
        None,
        None,
    ]
    moved = annotate_with_features(dataclasses.replace(macro, output_port="IAC Driver Bus 1"))
    assert all(step.feature is None for step in moved.steps)  # a stale reference never survives


def test_old_files_load_unchanged_and_only_annotated_steps_write_a_feature():
    plain = MidiMacro.from_dict({"name": "old", "output_port": "DDJ-XP2", "steps": [SYNC_LED.to_dict()]})
    assert plain.steps[0].feature is None
    assert "feature" not in plain.steps[0].to_dict()
    annotated = annotate_with_features(plain)
    raw = annotated.to_dict()
    assert raw["steps"][0]["feature"] == {"controller": "DDJ-XP2", "feature": SYNC_ID, "verb": "led_on"}
    assert MidiMacro.from_dict(raw) == annotated


def test_a_stored_feature_recompiles_its_message_after_a_catalog_fix():
    stored = {**SyncMessage("Note On", 1, 99, 127).to_dict(), "delay_ms": 0}  # an old, wrong note
    stored["feature"] = {"controller": "DDJ-XP2", "feature": SYNC_ID, "verb": "led_on"}
    step = MacroStep.from_dict(stored)
    assert step.message == SYNC_LED  # the catalog's current note wins


def test_a_feature_that_no_longer_exists_keeps_the_stored_message():
    stored = {**SYNC_LED.to_dict(), "delay_ms": 0}
    stored["feature"] = {"controller": "DDJ-XP2", "feature": "deck.gone@1", "verb": "led_on"}
    step = MacroStep.from_dict(stored)
    assert step.message == SYNC_LED
    assert step.feature.action.feature_id == "deck.gone@1"  # kept, not silently dropped


def test_the_step_dialog_builds_steps_from_a_picked_control():
    dialog = FeatureStepDialog("DDJ-XP2")
    assert not dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()
    dialog.filter_edit.setText("beat sync")
    assert dialog.select(SYNC_ID)
    assert dialog.steps() == [MacroStep(SYNC_LED)]
    dialog.verb_combo.setCurrentIndex(dialog.verb_combo.findData(LED_VALUE))
    dialog.value_spin.setValue(42)
    assert dialog.steps() == [MacroStep(SyncMessage("Note On", 1, 88, 42))]
    dialog.filter_edit.setText("")
    listed = [dialog.feature_list.item(row) for row in range(dialog.feature_list.count())]
    assert listed and all(dialog.select(item.toolTip()) and dialog.selected_feature().led for item in listed[:20])


class _PickBeatSync:
    def __init__(self, controller, parent, direction=None):
        self.controller = controller

    def exec(self):
        return QDialog.DialogCode.Accepted

    def steps(self):
        return [MacroStep(SyncMessage("Note On", 1, 88, 127))]


def test_the_editor_adds_feature_steps_and_saves_them_annotated():
    dialog = MacroManagerDialog([MidiMacro("Lights", "IAC Driver Bus 1")], ["IAC Driver Bus 1", "DDJ-XP2"])
    assert not dialog.add_feature_button.isEnabled()
    dialog.port_combo.setCurrentText("DDJ-XP2")
    assert dialog.add_feature_button.isEnabled()
    dialog.feature_step_dialog_factory = _PickBeatSync
    dialog._add_feature_steps()
    assert dialog.feature_text(0) == "BEAT SYNC (deck 1): LED on"
    edited = dialog._edited()
    assert edited.steps[0].feature == FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, LED_ON))


def test_a_re_registered_controller_still_resolves_saved_features():
    original = catalog.get_definition("DDJ-XP2")
    _registry.register(dataclasses.replace(original), replace=True)
    try:
        assert FeatureRef("DDJ-XP2", FeatureAction(SYNC_ID, LED_ON)).resolve() == SYNC_LED
    finally:
        _registry.register(original, replace=True)
