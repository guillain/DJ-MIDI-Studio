"""Atelier step 2 (issue #413): the Controller Emulator's feature card."""

import pytest

from djmidi import catalog
from djmidi.atelier import features_for
from djmidi.gui.controller_emulator import ControllerEmulatorView
from djmidi.gui.feature_card import FeatureCard


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def test_the_card_asks_for_a_click_until_it_has_a_feature():
    card = FeatureCard()
    assert card.feature is None
    assert "Click a control" in card._prompt.text()
    feature = next(f for f in features_for("DDJ-XP2") if f.name == "BEAT SYNC")
    card.set_feature(feature)
    assert card.id_label.text() == feature.id
    assert card.kind_label.text() == "Button, deck 1"
    assert card.layer_label.text() == "plain"
    assert card.sends_label.text() == f"Note On / Off · ch 1 · note {feature.input.number}"
    assert "assumed" in card.led_label.text() and "not verified" in card.led_label.text()
    assert card.actions_label.text() == "tap, press, release, LED on, LED off, LED value"


def test_an_unresolved_control_says_so():
    card = FeatureCard()
    card.set_feature(None, unresolved="MIXER CROSSFADER")
    assert card._prompt.text().startswith("MIXER CROSSFADER: no feature")


def _emulator() -> ControllerEmulatorView:
    view = ControllerEmulatorView(config_provider=lambda: None)
    view._combo.setCurrentText("DDJ-XP2")
    return view


def test_clicking_a_pad_shows_its_feature_for_its_own_side():
    view = _emulator()
    view._on_control_pressed(("DDJ-XP2", "PAD", "Pad 3"))
    left = view.feature_card.feature
    assert left is not None and left.deck == 1 and left.kind == "pad"
    assert left.id == "pad.deck-1-pad-3-pad-mode-1@8"
    view._on_control_pressed(("DDJ-XP2", "PAD", "Pad 3 (R)"))
    right = view.feature_card.feature
    assert right.deck == 2 and right.input.channel == 10


def test_the_card_follows_the_latched_pad_mode_and_shift():
    view = _emulator()
    view._on_control_pressed(("DDJ-XP2", "PAD MODE", "PAD MODE 3"))
    view._on_control_pressed(("DDJ-XP2", "PAD", "Pad 3"))
    assert view.feature_card.feature.bank == "PAD MODE 3"
    view._on_control_pressed(("DDJ-XP2", "OTHER", "SHIFT"))
    view._on_control_pressed(("DDJ-XP2", "PAD", "Pad 3"))
    assert view.feature_card.feature.shift is True
    assert view.feature_card.layer_label.text() == "SHIFT, pad mode PAD MODE 3"


def test_switching_controller_clears_the_card():
    view = _emulator()
    view._on_control_pressed(("DDJ-XP2", "PAD", "Pad 3"))
    assert view.feature_card.feature is not None
    view._combo.setCurrentText("XDJ-XZ")
    assert view.feature_card.feature is None
