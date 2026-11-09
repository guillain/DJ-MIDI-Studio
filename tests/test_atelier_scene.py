"""Atelier step 4 (issue #413): a controller's target LED state."""

import pytest

from djmidi import catalog
from djmidi.atelier.scene import Scene
from djmidi.controller_sync import ControllerSyncSet, SyncMessage

SYNC = "deck.beat-sync@1"  # DDJ-XP2 deck 1 BEAT SYNC: ch 1 note 88
SYNC_ON = SyncMessage("Note On", 1, 88, 127)
STRANGER = SyncMessage("Control Change", 16, 120, 5)


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def test_a_sync_set_reads_as_led_values_and_keeps_raw_messages_in_place():
    pad = SyncMessage("Note On", 8, 0, 42)
    scene = Scene.from_messages("DDJ-XP2", [STRANGER, SYNC_ON, pad])
    assert scene.lit == {SYNC: 127, "pad.deck-1-pad-1-pad-mode-1@8": 42}
    assert scene.raw_messages == [STRANGER]
    assert scene.messages() == (STRANGER, SYNC_ON, pad)  # same messages, same order


def test_repeats_keep_the_first_position_and_the_last_value():
    off = SyncMessage("Note On", 1, 88, 0)
    scene = Scene.from_messages("DDJ-XP2", [SYNC_ON, STRANGER, off])
    assert scene.lit == {SYNC: 0}
    assert scene.messages() == (off, STRANGER)


def test_editing_leds():
    scene = Scene("DDJ-XP2")
    scene.set_led(SYNC, 127)
    scene.set_led(SYNC, 30)  # same entry, new value
    assert scene.messages() == (SyncMessage("Note On", 1, 88, 30),)
    scene.set_led(SYNC, None)
    assert scene.messages() == () and scene.led_value(SYNC) is None
    with pytest.raises(ValueError):
        scene.set_led(SYNC, 128)


def test_clear_forgets_leds_but_keeps_raw_messages():
    scene = Scene.from_messages("DDJ-XP2", [SYNC_ON, STRANGER])
    scene.clear()
    assert scene.messages() == (STRANGER,)


def test_writing_back_keeps_the_existing_set_port_and_scene():
    existing = ControllerSyncSet("DDJ-XP2", "DDJ-XP2 MIDI 1", (STRANGER,), scene="Club")
    scene = Scene.from_sync_set(existing, "DDJ-XP2")
    scene.set_led(SYNC, 127)
    stored = scene.to_sync_set(existing)
    assert (stored.controller, stored.output_port, stored.scene) == ("DDJ-XP2", "DDJ-XP2 MIDI 1", "Club")
    assert stored.messages == (STRANGER, SYNC_ON)
    fresh = Scene("DDJ-XP2")
    fresh.set_led(SYNC, 0)
    new = fresh.to_sync_set(None, "Club")
    assert (new.controller, new.scene, new.messages) == ("DDJ-XP2", "Club", (SyncMessage("Note On", 1, 88, 0),))


def test_no_sync_set_is_an_empty_scene():
    assert Scene.from_sync_set(None, "DDJ-XP2").messages() == ()
