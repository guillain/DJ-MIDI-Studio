"""Atelier: macros edited on the photo (issue #428)."""

import dataclasses

import pytest

from djmidi import catalog
from djmidi.atelier.actions import (
    AS_CONTROLLER,
    LED_ON,
    LED_VALUE,
    PRESS,
    TAP,
    TO_CONTROLLER,
    VALUE,
)
from djmidi.atelier.features import feature_by_id
from djmidi.atelier.macro_edit import (
    describe_step,
    move_step,
    remove_step,
    set_delay,
    steps_for,
    verbs_for,
)
from djmidi.controller_sync import SyncMessage
from djmidi.gui.atelier_view import AtelierView
from djmidi.midi_macros import MacroStep, MidiMacro

SYNC = "deck.beat-sync@1"
IAC = "IAC Driver Bus 1"
SYNC_ON = SyncMessage("Note On", 1, 88, 127)


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def _sync():
    return feature_by_id("DDJ-XP2", SYNC)


def test_verbs_follow_the_macro_direction():
    sync = _sync()
    assert verbs_for(sync, TO_CONTROLLER)[0] == LED_ON
    assert verbs_for(sync, AS_CONTROLLER)[0] == TAP
    cc = dataclasses.replace(sync, input=dataclasses.replace(sync.input, kind="CC"), led=None)
    assert verbs_for(cc, AS_CONTROLLER) == (VALUE,)
    assert verbs_for(cc, TO_CONTROLLER) == ()  # no LED on a CC control


def test_steps_for_a_tap_are_a_press_and_a_release():
    steps = steps_for("DDJ-XP2", _sync(), TAP)
    assert [s.message.data2 for s in steps] == [127, 0]
    [led] = steps_for("DDJ-XP2", _sync(), LED_VALUE, 42)
    assert led.message == SyncMessage("Note On", 1, 88, 42)


def test_step_edits_return_new_macros():
    macro = MidiMacro("m", "DDJ-XP2", (MacroStep(SYNC_ON), MacroStep(SyncMessage("Note On", 1, 1, 127))))
    moved, row = move_step(macro, 1, -1)
    assert row == 0 and moved.steps[0].message.data1 == 1 and macro.steps[0].message.data1 == 88
    assert move_step(macro, 1, 5)[1] == 1
    assert len(remove_step(macro, 0).steps) == 1
    assert set_delay(macro, 1, 250).steps[1].delay_ms == 250
    with pytest.raises(ValueError):
        set_delay(macro, 0, -1)


def test_describe_step_names_the_control_or_the_raw_message():
    led = MidiMacro("m", "DDJ-XP2", (MacroStep(SYNC_ON, 100),))
    assert describe_step(led, led.steps[0]) == "BEAT SYNC (deck 1): LED on · after 100 ms"
    sim = MidiMacro("m", IAC, (MacroStep(SYNC_ON),), simulates="DDJ-XP2")
    assert describe_step(sim, sim.steps[0]) == "BEAT SYNC (deck 1): press"
    plain = MidiMacro("m", IAC, (MacroStep(SYNC_ON),))
    assert describe_step(plain, plain.steps[0]) == "Note On · ch 1 · 88 = 127"
    wait = MidiMacro("m", "DDJ-XP2", (MacroStep(SYNC_ON, 0, wait=True),))
    assert describe_step(wait, wait.steps[0]).startswith("Wait for BEAT SYNC")


def _view(macros):
    view = AtelierView(sync_set_provider=lambda controller, scene: None)
    view.controller_combo.setCurrentText("XDJ-XZ")
    view.macro_panel.set_macros(macros)
    view.lower_tabs.setCurrentWidget(view.macro_panel)
    return view


def test_clicking_controls_appends_steps_and_saves():
    macros = [MidiMacro("Plain", IAC), MidiMacro("Lights", "DDJ-XP2")]
    view = _view(macros)
    panel = view.macro_panel
    panel.macro_combo.setCurrentText("Lights")
    assert view.controller == "DDJ-XP2"  # the photo follows the macro's controller
    assert "LED changes on the DDJ-XP2" in panel.target_label.text()
    feature = view.pick_key(("DDJ-XP2", "DECK", "BEAT SYNC"))
    assert feature is not None and feature.id == SYNC
    assert panel.macro.steps[0].message == SYNC_ON
    assert panel.macro.steps[0].feature is not None  # annotated
    assert panel.step_list.item(0).text() == "BEAT SYNC (deck 1): LED on"
    assert panel.is_dirty and panel.save_button.isEnabled()
    saved = []
    panel.macrosSaved.connect(saved.append)
    panel.save()
    assert [m.name for m in saved[0]] == ["Plain", "Lights"] and len(saved[0][1].steps) == 1
    assert not panel.is_dirty


def test_simulating_macro_adds_presses_and_pad_mode_clicks_add_nothing():
    view = _view([MidiMacro("Sim", IAC, simulates="DDJ-XP2")])
    panel = view.macro_panel
    assert view.controller == "DDJ-XP2"
    assert view.pick_key(("DDJ-XP2", "PAD MODE", "PAD MODE 1")) is None
    assert panel.macro.steps == ()
    panel.show_feature(_sync())
    panel.verb_combo.setCurrentIndex(panel.verb_combo.findData(PRESS))
    view.pick_key(("DDJ-XP2", "DECK", "BEAT SYNC"))
    assert [s.message.data2 for s in panel.macro.steps] == [127]


def test_reorder_delay_remove_and_revert():
    view = _view([MidiMacro("Lights", "DDJ-XP2")])
    panel = view.macro_panel
    view.pick_key(("DDJ-XP2", "DECK", "BEAT SYNC"))
    view.pick_key(("DDJ-XP2", "DECK", "QUANTIZE"))
    assert panel.step_list.currentRow() == 1
    panel.delay_spin.setValue(200)
    assert panel.macro.steps[1].delay_ms == 200
    panel.move_selected(-1)
    assert panel.step_list.currentRow() == 0 and panel.macro.steps[0].delay_ms == 200
    panel.remove_selected()
    assert len(panel.macro.steps) == 1
    panel.revert()
    assert panel.macro.steps == () and not panel.is_dirty


def test_plain_macro_and_wrong_controller_add_nothing():
    view = _view([MidiMacro("Plain", IAC), MidiMacro("Lights", "DDJ-XP2")])
    assert "plain MIDI" in view.macro_panel.target_label.text()
    assert view.pick_key(("XDJ-XZ", "DECK", "CUE")) is None
    assert "Pick a macro" in view.status_label.text()
    view.macro_panel.macro_combo.setCurrentText("Lights")
    view.controller_combo.setCurrentText("XDJ-XZ")
    assert view.pick_key(("XDJ-XZ", "DECK", "CUE")) is None
    assert "switch the controller" in view.status_label.text()


def test_scene_edits_are_untouched_outside_the_macros_tab():
    view = _view([MidiMacro("Lights", "DDJ-XP2")])
    view.lower_tabs.setCurrentIndex(0)
    view.pick_key(("DDJ-XP2", "DECK", "BEAT SYNC"))
    assert view.macro_panel.macro.steps == ()
    assert view.feature is not None and view.feature.id == SYNC


def test_main_window_saves_atelier_macros(monkeypatch):
    from djmidi.gui import main_window as mw

    window = mw.MainWindow()
    saved = []
    monkeypatch.setattr(mw.midi_macros, "save_macros", lambda directory, macros: saved.append(list(macros)))
    window.atelier_view.macro_panel.macrosSaved.emit([MidiMacro("New", "DDJ-XP2")])
    assert [m.name for m in window.macros] == ["New"] and saved
    assert any(action.text() == "New" for action in window._macro_menu.actions())


# --- toggle second list and wait steps (issue #435) ------------------------------


def test_edits_on_the_second_list_leave_the_main_steps_alone():
    from djmidi.atelier.macro_edit import append_steps, steps_of

    macro = MidiMacro("m", "DDJ-XP2", (MacroStep(SYNC_ON),))
    toggled = append_steps(macro, [MacroStep(SyncMessage("Note On", 1, 88, 0))], alternate=True)
    assert [s.message for s in toggled.steps] == [s.message for s in macro.steps] and toggled.is_toggle
    assert steps_of(toggled, alternate=True)[0].message.data2 == 0
    assert steps_of(toggled, alternate=True)[0].feature is not None  # annotated too
    moved, _row = move_step(toggled, 0, 1, alternate=True)
    assert moved.alternate_steps == toggled.alternate_steps
    assert set_delay(toggled, 0, 300, alternate=True).alternate_steps[0].delay_ms == 300
    assert remove_step(toggled, 0, alternate=True).alternate_steps == ()


def test_wait_step_for_a_control_and_its_wording():
    from djmidi.atelier.macro_edit import wait_step_for

    step = wait_step_for(_sync(), 500)
    assert step.wait and step.delay_ms == 500
    assert step.message == SyncMessage("Note On", 1, 88, 0)
    macro = MidiMacro("m", "DDJ-XP2", (step, MacroStep(SYNC_ON, 0, wait=True)))
    assert describe_step(macro, macro.steps[0]) == "Wait for BEAT SYNC (deck 1) (at most 500 ms)"
    assert describe_step(macro, macro.steps[1]) == "Wait for BEAT SYNC (deck 1)"


def test_panel_builds_a_toggle_with_a_wait_from_clicks():
    view = _view([MidiMacro("Lights", "DDJ-XP2")])
    panel = view.macro_panel
    view.pick_key(("DDJ-XP2", "DECK", "BEAT SYNC"))  # main: LED on
    panel.list_combo.setCurrentIndex(1)  # the toggle's second list
    assert panel.step_list.count() == 0
    panel.show_feature(_sync())
    panel.verb_combo.setCurrentIndex(panel.verb_combo.findData("wait"))
    view.pick_key(("DDJ-XP2", "DECK", "BEAT SYNC"))
    assert panel.delay_label.text() == "Wait at most"
    panel.delay_spin.setValue(2000)
    panel.verb_combo.setCurrentIndex(panel.verb_combo.findData("led_off"))
    view.pick_key(("DDJ-XP2", "DECK", "BEAT SYNC"))
    macro = panel.macro
    assert len(macro.steps) == 1 and [s.wait for s in macro.alternate_steps] == [True, False]
    assert macro.alternate_steps[0].delay_ms == 2000
    assert panel.step_list.item(0).text() == "Wait for BEAT SYNC (deck 1) (at most 2000 ms)"
    saved = []
    panel.macrosSaved.connect(saved.append)
    panel.save()
    stored = saved[0][0]
    assert MidiMacro.from_dict(stored.to_dict()).alternate_steps == stored.alternate_steps
    panel.list_combo.setCurrentIndex(0)
    assert panel.step_list.count() == 1 and panel.delay_label.text() in ("Delay", "Wait at most")


def test_a_cc_control_can_be_waited_for_even_without_an_led():
    import dataclasses

    sync = _sync()
    cc = dataclasses.replace(sync, input=dataclasses.replace(sync.input, kind="CC"), led=None)
    view = _view([MidiMacro("Lights", "DDJ-XP2")])
    assert "wait" in view.macro_panel._verbs(cc)
    assert view.macro_panel.add_feature("DDJ-XP2", cc, "wait")
    assert view.macro_panel.macro.steps[0].message.event_type == "Control Change"
