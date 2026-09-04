import json
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QLabel

from djmidi.ableton_link import ABLETON_LINK_CLOCK_SOURCE_NAME, LinkBackendUnavailable
from djmidi.gui.midi_routing_view import (
    MidiRoutingView,
    _load_json_list,
    _route_from_dict,
    _route_to_dict,
    _transform_from_dict,
    _transform_to_dict,
)
from djmidi.midi_clock import MidiClockMirror
from djmidi.midi_router import MidiRoute, MidiValueTransform
from djmidi.midi_routing_session import SERATO_CLOCK_INPUT_NAME


def _ini_settings(tmp_path):
    """A throwaway file-backed QSettings, isolated from the user's real one."""
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_routing_view_configures_one_way_route_without_hardware():
    view = MidiRoutingView()
    view._source_combo.addItem("in")
    view._destination_combo.addItem("out")
    view._source_combo.setCurrentText("in")
    view._destination_combo.setCurrentText("out")
    view._add_route()
    assert len(view.router.routes) == 1
    assert view._routes_table.item(0, 0).text() == "in"


def test_routing_view_exposes_clock_panel_for_independent_dock():
    view = MidiRoutingView()
    panel = view.take_clock_panel()
    assert panel.title() == "MIDI Clock"
    assert panel.parent() is None
    assert view.layout().indexOf(panel) == -1


def test_refresh_ports_separates_midi_inputs_and_outputs():
    view = MidiRoutingView()
    with (
        patch("djmidi.gui.midi_routing_view.list_input_ports", return_value=["MIDI4x4 Midi In 1"]),
        patch("djmidi.gui.midi_routing_view.list_output_ports", return_value=["MIDI4x4 Midi Out 1"]),
    ):
        view.refresh_ports()
    assert view._source_combo.itemText(0) == "MIDI4x4 Midi In 1"
    assert view._destination_combo.itemText(0) == "MIDI4x4 Midi Out 1"
    assert view._clock_source.itemText(0) == "MIDI4x4 Midi In 1"
    assert view._clock_destination.itemText(0) == "MIDI4x4 Midi Out 1"
    assert view._destination_combo.findText("MIDI4x4 Midi In 1") < 0


def test_routing_and_clock_ports_are_loaded_when_view_opens():
    with (
        patch("djmidi.gui.midi_routing_view.list_input_ports", return_value=["Input at startup"]),
        patch("djmidi.gui.midi_routing_view.list_output_ports", return_value=["Output at startup"]),
    ):
        view = MidiRoutingView()
    assert view._source_combo.currentText() == "Input at startup"
    assert view._destination_combo.currentText() == "Output at startup"
    assert view._clock_source.currentText() == "Input at startup"
    assert view._clock_destination.currentText() == "Output at startup"
    assert view._routing_refresh_button.text() == "Refresh MIDI ports"
    assert view._clock_refresh_button.text() == "Refresh MIDI ports"


def test_clock_start_stop_controls_share_routing_session_state():
    view = MidiRoutingView()
    view.set_routing_enabled(True)
    assert view._routing_button.isEnabled()
    assert view._clock_routing_button.isEnabled()
    assert view._clock_routing_button.text() == "Start routing"
    view._routing_session.running = True
    view._stop_routing()
    assert view._routing_button.text() == "Start routing"
    assert view._clock_routing_button.text() == "Start routing"


def test_routing_view_rejects_same_clock_source_and_destination():
    view = MidiRoutingView()
    view._clock_source.addItem("same")
    view._clock_destination.addItem("same")
    view._clock_source.setCurrentText("same")
    view._clock_destination.setCurrentText("same")
    view._clock_enabled.setChecked(True)
    assert view.clock_mirror is None
    assert "different" in view._clock_status.text()


def test_routing_view_supports_multiple_clock_lines():
    view = MidiRoutingView()
    view._clock_source.addItems(["clock-in", "other-in"])
    view._clock_destination.addItems(["clock-out", "other-out"])
    view._clock_source.setCurrentText("clock-in")
    view._clock_destination.setCurrentText("clock-out")
    view._clock_enabled.setChecked(True)
    assert len(view._clocks) == 1
    view._clock_source.setCurrentText("other-in")
    view._clock_destination.setCurrentText("other-out")
    view._add_clock_route()
    assert len(view._clocks) == 2
    assert view._clock_table.rowCount() == 2


def test_routing_view_exposes_virtual_serato_clock_source():
    view = MidiRoutingView()
    view._serato_virtual_checkbox.setChecked(True)
    assert view._clock_source.currentText() == SERATO_CLOCK_INPUT_NAME
    assert view._routing_session._virtual_input_ids == frozenset({SERATO_CLOCK_INPUT_NAME})
    assert any("does not emit standard MIDI Clock" in label.text() for label in view.findChildren(QLabel))
    view._serato_virtual_checkbox.setChecked(False)
    assert view._clock_source.findText(SERATO_CLOCK_INPUT_NAME) < 0


def test_routing_view_exposes_clock_waiting_indicator_when_not_started():
    view = MidiRoutingView()
    view._clock_source.addItem(SERATO_CLOCK_INPUT_NAME)
    view._clock_destination.addItem("MIDI4x4 Midi Out 1")
    view._clock_source.setCurrentText(SERATO_CLOCK_INPUT_NAME)
    view._clock_destination.setCurrentText("MIDI4x4 Midi Out 1")
    view._clock_enabled.setChecked(True)
    view._refresh_clock_status()
    assert "disabled in Preferences" in view._clock_status.text()


def test_routing_view_reports_clock_inactive_after_session_starts_without_ticks():
    view = MidiRoutingView()
    view._clock_source.addItem("clock-in")
    view._clock_destination.addItem("clock-out")
    view._clock_source.setCurrentText("clock-in")
    view._clock_destination.setCurrentText("clock-out")
    view._clock_enabled.setChecked(True)
    view.set_routing_enabled(True)
    view._routing_session.running = True
    view._refresh_clock_status()
    assert "CLOCK INACTIVE" in view._clock_status.text()


def test_routing_view_reports_link_clock_configuration_when_link_is_selected():
    class FakeLinkFollower:
        source_port_id = ABLETON_LINK_CLOCK_SOURCE_NAME
        destination_port_ids = ("MIDI4x4 Midi Out 1",)

        def clock_active(self, _now):
            return False

    view = MidiRoutingView()
    view._clock_enabled.blockSignals(True)
    view._clock_enabled.setChecked(True)
    view._clock_enabled.blockSignals(False)
    view.set_routing_enabled(True)
    view._link_followers = [FakeLinkFollower()]
    view._routing_session.running = True
    view._refresh_clock_status()
    assert "CLOCK INACTIVE" in view._clock_status.text()
    assert ABLETON_LINK_CLOCK_SOURCE_NAME in view._clock_status.text()
    assert "source port not open" not in view._clock_status.text()
    assert "start playback" in view._clock_status.toolTip()


def test_routing_view_diagnoses_serato_and_link_routes_independently():
    """A Link follower being configured must not swallow an unrelated, genuine
    problem with a separately-configured Serato Clock route (regression for a
    real hardware session where the combined status only ever said "no Link
    beats", hiding that Serato's virtual Clock port was never opened)."""

    class FakeLinkFollower:
        source_port_id = ABLETON_LINK_CLOCK_SOURCE_NAME
        destination_port_ids = ("MIDI4x4 Midi Out 1",)

        def clock_active(self, _now):
            return False

    view = MidiRoutingView()
    view._clock_enabled.blockSignals(True)
    view._clock_enabled.setChecked(True)
    view._clock_enabled.blockSignals(False)
    view.set_routing_enabled(True)
    view._clocks = [MidiClockMirror(SERATO_CLOCK_INPUT_NAME, ["MIDI4x4 Midi Out 2"])]
    view._link_followers = [FakeLinkFollower()]
    view._routing_session.running = True
    view._refresh_clock_status()
    text = view._clock_status.text()
    assert "CLOCK INACTIVE" in text
    assert SERATO_CLOCK_INPUT_NAME in text
    assert "source port not open" in text  # the Serato route's own diagnosis
    assert ABLETON_LINK_CLOCK_SOURCE_NAME in text
    assert "no Link beats received" in text
    assert "Serato diagnostic" in view._clock_status.toolTip()
    assert "press Play in Serato" in view._clock_status.toolTip()


def _view_with_one_route():
    view = MidiRoutingView()
    view._source_combo.addItem("in")
    view._destination_combo.addItem("out")
    view._source_combo.setCurrentText("in")
    view._destination_combo.setCurrentText("out")
    view._add_route()
    return view


def test_edit_transform_button_disabled_without_selection():
    view = _view_with_one_route()
    assert not view._edit_transform_button.isEnabled()
    view._routes_table.setCurrentCell(0, 0)
    assert view._edit_transform_button.isEnabled()


class _FakeTransformDialog:
    """Plain stand-in for MidiRouteTransformDialog — avoids MagicMock's
    auto-generated attribute graph, which was observed to outlive the test
    and crash native Qt cleanup when combined with many later widget
    creations (e.g. the full test_main_window.py suite)."""

    def __init__(self, exec_result, transform=None):
        self._exec_result = exec_result
        self._transform = transform

    def __call__(self, _current_transform, _parent=None):
        return self

    def exec(self):
        return self._exec_result

    def result_transform(self):
        return self._transform


def test_edit_transform_updates_route_and_table():
    view = _view_with_one_route()
    view._routes_table.setCurrentCell(0, 0)
    transform = MidiValueTransform(channel_override=3, invert_data2=True)
    fake_dialog = _FakeTransformDialog(QDialog.DialogCode.Accepted, transform)
    with patch("djmidi.gui.midi_routing_view.MidiRouteTransformDialog", fake_dialog):
        view._edit_selected_transform()
    assert view.router.routes[0].transform == transform
    assert view._routes_table.item(0, 2).text() == "Ch 3, invert"
    assert view._edit_transform_button.isEnabled()


def test_edit_transform_cancelled_leaves_route_unchanged():
    view = _view_with_one_route()
    view._routes_table.setCurrentCell(0, 0)
    fake_dialog = _FakeTransformDialog(QDialog.DialogCode.Rejected)
    with patch("djmidi.gui.midi_routing_view.MidiRouteTransformDialog", fake_dialog):
        view._edit_selected_transform()
    assert view.router.routes[0].transform is None
    assert view._routes_table.item(0, 2).text() == "—"


def test_route_dict_round_trips_with_and_without_transform():
    plain = MidiRoute("in", "out")
    assert _route_from_dict(_route_to_dict(plain)) == plain
    transformed = MidiRoute(
        "in", "out", transform=MidiValueTransform(channel_override=2, data1_offset=-3, invert_data2=True)
    )
    assert _route_from_dict(_route_to_dict(transformed)) == transformed


def test_load_json_list_tolerates_missing_or_malformed_values():
    assert _load_json_list("") == []
    assert _load_json_list(None) == []
    assert _load_json_list("not json") == []
    assert _load_json_list(json.dumps({"a": 1})) == []
    assert _load_json_list(json.dumps([1, 2])) == [1, 2]


def test_transform_dict_helpers_reject_non_dict_and_none():
    assert _transform_from_dict(None) is None
    assert _transform_from_dict("nope") is None
    assert _transform_to_dict(None) is None


def test_save_state_and_restore_state_round_trip_routes_and_ports(tmp_path):
    settings = _ini_settings(tmp_path)
    view = MidiRoutingView()
    view._source_combo.addItem("in")
    view._destination_combo.addItem("out")
    view._source_combo.setCurrentText("in")
    view._destination_combo.setCurrentText("out")
    transform = MidiValueTransform(channel_override=4)
    view._router.add_route(MidiRoute("in", "out", transform=transform))
    view._refresh_routes_table()
    view.save_state(settings)

    restored = MidiRoutingView()
    restored._source_combo.addItem("in")
    restored._destination_combo.addItem("out")
    restored.restore_state(settings)

    assert restored._source_combo.currentText() == "in"
    assert restored._destination_combo.currentText() == "out"
    assert restored.router.routes == (MidiRoute("in", "out", transform=transform),)
    assert restored._routes_table.rowCount() == 1


def test_save_state_and_restore_state_round_trip_clock_configuration(tmp_path):
    settings = _ini_settings(tmp_path)
    view = MidiRoutingView()
    view._clock_source.addItem("clock-in")
    view._clock_destination.addItem("clock-out")
    view._clock_source.setCurrentText("clock-in")
    view._clock_destination.setCurrentText("clock-out")
    view._clock_enabled.setChecked(True)
    assert len(view._clocks) == 1
    view.save_state(settings)

    restored = MidiRoutingView()
    restored._clock_source.addItem("clock-in")
    restored._clock_destination.addItem("clock-out")
    restored.restore_state(settings)

    assert restored._clock_enabled.isChecked() is True
    assert [(c.source_port_id, c.destination_port_ids) for c in restored._clocks] == [
        ("clock-in", ("clock-out",))
    ]
    assert restored._clock_source.currentText() == "clock-in"
    assert restored._clock_destination.currentText() == "clock-out"
    assert restored._clock_table.rowCount() == 1


def test_save_state_and_restore_state_round_trip_serato_virtual_input(tmp_path):
    settings = _ini_settings(tmp_path)
    view = MidiRoutingView()
    view._serato_virtual_checkbox.setChecked(True)
    view.save_state(settings)

    restored = MidiRoutingView()
    restored.restore_state(settings)
    assert restored._serato_virtual_checkbox.isChecked() is True
    assert restored._clock_source.currentText() == SERATO_CLOCK_INPUT_NAME


def test_save_state_and_restore_state_round_trip_link_followers(tmp_path):
    settings = _ini_settings(tmp_path)
    view = MidiRoutingView()
    view._clock_enabled.blockSignals(True)
    view._clock_enabled.setChecked(True)
    view._clock_enabled.blockSignals(False)
    view._link_followers = [SimpleNamespace(destination_port_ids=("out-a", "out-b"))]
    view.save_state(settings)

    class FakeFollower:
        def __init__(self, destinations, _provider):
            self.destination_port_ids = tuple(destinations)
            self.source_port_id = ABLETON_LINK_CLOCK_SOURCE_NAME

    with (
        patch("djmidi.gui.midi_routing_view.LinkClockFollower", FakeFollower),
        patch("djmidi.gui.midi_routing_view.AalinkStateProvider"),
    ):
        restored = MidiRoutingView()
        restored.restore_state(settings)
    assert len(restored._link_followers) == 1
    assert restored._link_followers[0].destination_port_ids == ("out-a", "out-b")


def test_restore_state_skips_link_follower_when_backend_unavailable(tmp_path):
    settings = _ini_settings(tmp_path)
    view = MidiRoutingView()
    view._clock_enabled.blockSignals(True)
    view._clock_enabled.setChecked(True)
    view._clock_enabled.blockSignals(False)
    view._link_followers = [SimpleNamespace(destination_port_ids=("out-a",))]
    view.save_state(settings)

    with patch(
        "djmidi.gui.midi_routing_view.AalinkStateProvider",
        side_effect=LinkBackendUnavailable("nope"),
    ):
        restored = MidiRoutingView()
        restored.restore_state(settings)
    assert restored._link_followers == []


def test_restore_state_skips_invalid_saved_route_and_clock_entries(tmp_path):
    settings = _ini_settings(tmp_path)
    settings.beginGroup("midiRouting")
    settings.setValue("routes", json.dumps([{"source": "in"}]))
    settings.setValue("clocks", json.dumps([{"source": "same", "destinations": ["same"]}]))
    settings.endGroup()

    view = MidiRoutingView()
    view.restore_state(settings)
    assert view.router.routes == ()
    assert view._clocks == []
