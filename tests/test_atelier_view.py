"""Atelier step 4 (issue #413): the Atelier tab, a scene designer."""

import pytest

from djmidi import catalog
from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.gui.atelier_view import AtelierView

SYNC = "deck.beat-sync@1"
SYNC_ON = SyncMessage("Note On", 1, 88, 127)
STRANGER = SyncMessage("Control Change", 16, 120, 5)
CLUB = ControllerSyncSet("DDJ-XP2", "DDJ-XP2", (SYNC_ON, STRANGER), scene="Club")


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def _view(stored=None) -> AtelierView:
    sets = {("DDJ-XP2", "Club"): CLUB} if stored is None else stored
    view = AtelierView(
        sync_set_provider=lambda controller, scene: sets.get((controller, scene)),
        scene_names_provider=lambda: ["Default", "Club"],
        active_scene_provider=lambda: "Club",
    )
    view.controller_combo.setCurrentText("DDJ-XP2")
    return view


def test_a_stored_sync_set_shows_as_the_scene_state():
    view = _view()
    assert view.scene_combo.currentText() == "Club"
    lines = [view.state_list.item(row).text() for row in range(view.state_list.count())]
    assert lines[0] == "BEAT SYNC (deck 1): LED on"
    assert "kept as is" in lines[1]
    assert ("DDJ-XP2", "DECK", "BEAT SYNC") in view.photo._led_keys
    assert not view.is_dirty


def test_each_deck_lights_its_own_side_of_the_photo():
    both = ControllerSyncSet("DDJ-XP2", messages=(SYNC_ON, SyncMessage("Note On", 2, 88, 127)), scene="Club")
    view = _view({("DDJ-XP2", "Club"): both})
    assert view.photo._led_keys == {("DDJ-XP2", "DECK", "BEAT SYNC"), ("DDJ-XP2", "DECK", "BEAT SYNC (R)")}


def test_clicking_a_control_and_choosing_its_led_edits_the_scene():
    view = _view()
    feature = view.pick_key(("DDJ-XP2", "PAD", "Pad 3"))
    assert feature is not None and feature.deck == 1
    assert view.feature_card.feature == feature
    view.set_led_choice(2)  # on
    assert view.scene.led_value(feature.id) == 127 and view.is_dirty
    view.set_led_choice(3, 42)  # a value
    assert view.scene.led_value(feature.id) == 42
    view.set_led_choice(0)  # not set
    assert view.scene.led_value(feature.id) is None


def test_saving_emits_the_sync_set_and_keeps_unknown_messages():
    view = _view()
    saved = []
    view.saveRequested.connect(saved.append)
    view.select_feature(SYNC)
    view.set_led_choice(1)  # off
    result = view.save()
    assert saved == [result]
    assert result.scene == "Club" and result.output_port == "DDJ-XP2"
    assert result.messages == (SyncMessage("Note On", 1, 88, 0), STRANGER)
    assert not view.is_dirty


def test_send_emits_the_unsaved_scene():
    view = _view()
    sent = []
    view.sendRequested.connect(sent.append)
    view.send_button.click()
    assert sent and sent[0].messages == (SYNC_ON, STRANGER)


def test_switching_scene_reloads_and_clear_keeps_raw_messages():
    view = _view()
    view.scene_combo.setCurrentText("Default")
    assert view.scene.messages() == ()
    view.scene_combo.setCurrentText("Club")
    view.clear_leds()
    assert view.scene.messages() == (STRANGER,)


def test_the_main_window_stores_a_saved_scene_in_the_preferences():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    view = window.atelier_view
    view.controller_combo.setCurrentText("DDJ-XP2")
    view.select_feature(SYNC)
    view.set_led_choice(2)
    view.save()
    stored = window.preferences.sync_set_for("DDJ-XP2", window.preferences.active_sync_scene)
    assert stored is not None and SYNC_ON in stored.messages
    window.close()
