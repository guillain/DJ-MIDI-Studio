from djmidi.gui.midi_routing_view import MidiRoutingView
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
    view._serato_virtual_checkbox.setChecked(False)
    assert view._clock_source.findText(SERATO_CLOCK_INPUT_NAME) < 0
