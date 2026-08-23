from unittest.mock import patch

from PySide6.QtWidgets import QDialog, QLabel

from djmidi.ableton_link import ABLETON_LINK_CLOCK_SOURCE_NAME
from djmidi.gui.midi_routing_view import MidiRoutingView
from djmidi.midi_router import MidiValueTransform
from djmidi.midi_routing_session import SERATO_CLOCK_INPUT_NAME


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
