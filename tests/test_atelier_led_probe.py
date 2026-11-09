"""Atelier step 5 (issue #413): verified LED data and the LED probe."""

import json

import pytest
from PySide6.QtWidgets import QDialog

from djmidi import catalog, user_paths
from djmidi.atelier import FeatureAction, compile_action, feature_by_id
from djmidi.atelier.led_data import LedRecord, led_file, load_led_data, save_led_record
from djmidi.controller_sync import SyncMessage
from djmidi.gui.led_probe_dialog import LedProbeDialog

SYNC = "deck.beat-sync@1"  # DDJ-XP2 deck 1 BEAT SYNC, input ch 1 note 88


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def test_records_round_trip_and_bad_values_are_refused():
    record = LedRecord(SYNC, 1, 89, 100, 1, {5: "red", 9: "blue"}, "LED probe 2026-11-08")
    assert LedRecord.from_dict(record.to_dict()) == record
    with pytest.raises(ValueError):
        LedRecord.from_dict({"feature": SYNC, "channel": 17, "note": 1})
    with pytest.raises(ValueError):
        LedRecord.from_dict({"feature": SYNC, "channel": 1, "note": 1, "colours": {"200": "x"}})


def test_saving_adds_or_replaces_one_record_per_feature():
    save_led_record("DDJ-XP2", LedRecord(SYNC, 1, 88))
    save_led_record("DDJ-XP2", LedRecord(SYNC, 1, 89, colours={5: "red"}))
    assert load_led_data("DDJ-XP2") == {SYNC: LedRecord(SYNC, 1, 89, colours={5: "red"})}
    stored = json.loads(led_file("DDJ-XP2").read_text())
    assert stored["controller"] == "DDJ-XP2" and len(stored["leds"]) == 1
    assert led_file("DDJ-XP2").parent == user_paths.controllers_dir()


def test_an_unreadable_file_is_ignored():
    path = led_file("DDJ-XP2")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert load_led_data("DDJ-XP2") == {}


def test_features_use_verified_led_data_as_soon_as_it_is_saved():
    assert feature_by_id("DDJ-XP2", SYNC).led.verified is False
    save_led_record("DDJ-XP2", LedRecord(SYNC, 1, 89, 100, 1, {5: "red"}, "LED probe 2026-11-08"))
    led = feature_by_id("DDJ-XP2", SYNC).led
    assert (led.channel, led.note, led.on_value, led.off_value, led.verified) == (1, 89, 100, 1, True)
    assert led.colours == ((5, "red"),) and led.source == "LED probe 2026-11-08"
    # Compiled LED messages go to the verified address and values.
    assert compile_action("DDJ-XP2", FeatureAction(SYNC, "led_on")) == [SyncMessage("Note On", 1, 89, 100)]


def _probe(sender=None):
    return LedProbeDialog(feature_by_id("DDJ-XP2", SYNC), ["IAC Driver Bus 1", "DDJ-XP2"], sender=sender)


def test_the_probe_sends_to_the_controller_port_and_records_what_was_seen():
    sent = []
    dialog = _probe(lambda **kwargs: sent.append(kwargs))
    assert dialog.port_combo.currentText() == "DDJ-XP2"  # the controller's own port is guessed
    dialog.note_spin.setValue(89)
    dialog.value_spin.setValue(5)
    assert dialog.send(5)
    assert sent == [
        {"output_port_name": "DDJ-XP2", "event_type": "Note On", "channel_1_based": 1, "data1": 89, "data2": 5}
    ]
    dialog.colour_edit.setText("red")
    dialog.name_button.click()
    dialog.on_spin.setValue(100)
    record = dialog.record()
    assert (record.channel, record.note, record.on_value, record.colours) == (1, 89, 100, {5: "red"})
    assert record.source.startswith("LED probe ")


def test_a_failing_send_is_reported_not_raised():
    def broken(**_kwargs):
        raise OSError("port busy")

    dialog = _probe(broken)
    assert not dialog.send(127)
    assert "port busy" in dialog.status_label.text()


class _Probed:
    def __init__(self, feature, ports, parent=None):
        self.feature = feature

    def exec(self):
        return QDialog.DialogCode.Accepted

    def record(self):
        return LedRecord(self.feature.id, 1, 89, colours={5: "red"}, source="LED probe 2026-11-08")


def test_the_atelier_records_a_probe_and_shows_the_led_verified():
    from djmidi.gui.atelier_view import AtelierView

    view = AtelierView()
    view.controller_combo.setCurrentText("DDJ-XP2")
    view.led_probe_dialog_factory = _Probed
    view.ports_provider = lambda: ["DDJ-XP2"]
    view.select_feature(SYNC)
    assert view.probe_button.isEnabled()
    view.set_led_choice(2)  # an edit in progress survives the reload
    record = view.probe_led()
    assert record is not None and load_led_data("DDJ-XP2")[SYNC] == record
    assert view.feature.led.verified and "verified" in view.feature_card.led_label.text()
    assert view.scene.led_value(SYNC) == 127 and view.is_dirty
