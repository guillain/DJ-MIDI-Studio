"""Atelier step 3, first slice (issue #413): raw steps read as features."""

import pytest

from djmidi import catalog
from djmidi.atelier.describe import controller_for_port, describe_message
from djmidi.controller_sync import SyncMessage
from djmidi.gui.macro_editor import MacroManagerDialog
from djmidi.midi_macros import MacroStep, MidiMacro

SYNC_LED = SyncMessage("Note On", 1, 88, 127)  # DDJ-XP2 deck 1 BEAT SYNC (official list: note 88)


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def test_a_port_names_a_controller_only_when_it_is_unambiguous():
    assert controller_for_port("DDJ-XP2") == "DDJ-XP2"
    assert controller_for_port("IAC Driver Bus 1") is None
    assert controller_for_port("") is None


def test_a_message_to_a_controller_reads_as_its_feature():
    assert describe_message("DDJ-XP2", SYNC_LED) == "BEAT SYNC: LED on"
    assert describe_message("DDJ-XP2", SyncMessage("Note On", 1, 88, 0)) == "BEAT SYNC: LED off"
    assert describe_message("DDJ-XP2", SyncMessage("Note On", 1, 88, 42)) == "BEAT SYNC: LED value 42"
    assert describe_message("DDJ-XP2", SyncMessage("Note On", 16, 127, 1)) is None


def _dialog(port: str, *steps: MacroStep) -> MacroManagerDialog:
    return MacroManagerDialog([MidiMacro("Lights", port, tuple(steps))], [port])


def test_the_macro_editor_names_each_step_sent_to_a_controller():
    wait = MacroStep(SyncMessage("Note On", 1, 88, 127), 0, wait=True)
    dialog = _dialog("DDJ-XP2", MacroStep(SYNC_LED), wait)
    assert dialog.feature_text(0) == "BEAT SYNC: LED on"
    assert dialog.feature_text(1) == ""  # a wait step listens, it doesn't drive the controller
    dialog.table.item(0, 3).setText("50")
    assert dialog.feature_text(0) == "BEAT SYNC: LED value 50"
    dialog.port_combo.setCurrentText("IAC Driver Bus 1")
    assert dialog.feature_text(0) == ""
    assert "Pick a controller" in dialog.table.item(0, 5).toolTip()


def test_the_feature_column_is_not_part_of_the_saved_steps():
    dialog = _dialog("DDJ-XP2", MacroStep(SYNC_LED, 120))
    [row] = dialog._rows()
    assert row == ("Note On", "1", "88", "127", "120")
    assert not dialog.table.item(0, 5).flags() & dialog.table.item(0, 5).flags().ItemIsEditable
