"""Atelier step 3 (issue #413): picking a macro step's control on the photo."""

import pytest

from djmidi import catalog
from djmidi.gui.feature_step_dialog import FeatureStepDialog


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def _dialog() -> FeatureStepDialog:
    return FeatureStepDialog("DDJ-XP2")


def test_the_photo_is_the_first_tab():
    dialog = _dialog()
    assert dialog.tabs.currentIndex() == 0
    assert dialog.tabs.widget(0).findChild(type(dialog.photo)) is dialog.photo


def test_clicking_the_left_and_right_pads_selects_each_side_s_deck():
    dialog = _dialog()
    dialog.photo.controlPressed.emit(("DDJ-XP2", "PAD", "Pad 3"))
    left = dialog.selected_feature()
    assert left is not None and left.deck == 1 and left.kind == "pad"
    assert left.id == "pad.deck-1-pad-3-pad-mode-1@8"
    dialog.photo.controlPressed.emit(("DDJ-XP2", "PAD", "Pad 3 (R)"))
    right = dialog.selected_feature()
    assert right.deck == 2 and right.input.channel == 10
    assert "Selected:" in dialog.status_label.text()


def test_a_pad_mode_button_then_a_pad_picks_that_bank():
    dialog = _dialog()
    assert dialog.pick_key(("DDJ-XP2", "PAD MODE", "PAD MODE 3")) is None
    assert "PAD MODE 3" in dialog.status_label.text()
    feature = dialog.pick_key(("DDJ-XP2", "PAD", "Pad 3"))
    assert feature.bank == "PAD MODE 3"
    assert dialog.selected_feature() == feature


def test_shift_then_a_pad_picks_the_shift_variant():
    dialog = _dialog()
    dialog.pick_key(("DDJ-XP2", "OTHER", "SHIFT"))
    assert "SHIFT held" in dialog.status_label.text()
    feature = dialog.pick_key(("DDJ-XP2", "PAD", "Pad 3"))
    assert feature.shift is True
    dialog.pick_key(("DDJ-XP2", "OTHER", "SHIFT"))
    assert dialog.pick_key(("DDJ-XP2", "PAD", "Pad 3")).shift is False


def test_a_feature_hidden_by_the_filter_is_selected_after_clearing_it():
    dialog = _dialog()
    dialog.tabs.setCurrentIndex(1)
    dialog.filter_edit.setText("beat sync")
    feature = dialog.pick_key(("DDJ-XP2", "PAD", "Pad 3"))
    assert feature is not None
    assert dialog.filter_edit.text() == ""
    assert dialog.selected_feature() == feature
    assert dialog.steps()  # the OK path builds the step


def test_a_control_with_no_feature_says_so():
    dialog = _dialog()
    assert dialog.pick_key(("DDJ-XP2", "MIXER", "No such control")) is None
    assert "no MIDI message" in dialog.status_label.text()
    assert dialog.selected_feature() is None


def test_simulating_accepts_a_control_without_led_too():
    from djmidi import catalog
    from djmidi.atelier import AS_CONTROLLER, features_for
    from djmidi.gui.feature_step_dialog import FeatureStepDialog

    catalog.set_enabled_plugin_ids(None)
    cc = next(
        (name, f) for name in catalog.CONTROLLER_NAMES for f in features_for(name) if f.led is None
    )
    dialog = FeatureStepDialog(cc[0], direction=AS_CONTROLLER)
    assert dialog.select(cc[1].id)
    assert dialog.verb_combo.currentData() == "value"
