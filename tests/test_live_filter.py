"""Live Monitor log filters (issue #447): display only."""

import pytest

from djmidi import catalog
from djmidi.gui.jog import jog_cell_keys_for_event
from djmidi.gui.live_monitor import LiveMonitorView
from djmidi.live_filter import BEND, CC, NOTES, LogFilter, kind_of
from djmidi.midi_io import PITCH_BEND, MidiEvent


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def _event(event_type="Note On", data1="64", port="DDJ-XP2", direction="in", channel="8"):
    return MidiEvent(direction, channel, event_type, data1, "127", 0.0, port)


# An XDJ-XZ platter tick (gui/jog.py: CC 0x22 on a deck channel).
JOG = _event("Control Change", "34", "XDJ-XZ", channel="1")


def test_kinds_and_the_default_filter():
    assert kind_of(_event()) == NOTES and kind_of(_event("Control Change")) == CC
    assert kind_of(_event(PITCH_BEND, "0")) == BEND
    assert LogFilter().is_default and LogFilter().accepts(_event())


def test_filter_by_port_direction_kind_and_jogs():
    assert not LogFilter(port="XDJ-XZ").accepts(_event())
    assert LogFilter(directions=frozenset({"out"})).accepts(_event(direction="out"))
    assert not LogFilter(directions=frozenset({"out"})).accepts(_event())
    assert not LogFilter(kinds=frozenset({CC})).accepts(_event())
    assert not LogFilter(hide_jogs=True).accepts(JOG, is_jog=True)
    assert LogFilter(hide_jogs=True).accepts(JOG, is_jog=False)


def test_the_jog_sample_is_a_jog():
    assert jog_cell_keys_for_event(JOG.channel, JOG.event_type, JOG.data1)


def _view():
    view = LiveMonitorView()
    for event in (
        _event(),
        _event("Control Change", "20"),
        _event(PITCH_BEND, "0", "CMD Studio 4a", channel="1"),
        _event(direction="out"),
        JOG,
    ):
        view._append_event(event)
    return view


def _hidden(view):
    return [view._log.isRowHidden(row) for row in range(view._log.rowCount())]


def test_filters_hide_rows_without_removing_them():
    view = _view()
    assert view.visible_rows() == 5
    view.filter_kinds[NOTES].setChecked(False)
    assert _hidden(view) == [True, False, False, True, False]
    view.filter_kinds[NOTES].setChecked(True)
    view.filter_direction.setCurrentIndex(view.filter_direction.findText("In only"))
    assert _hidden(view) == [False, False, False, True, False]
    view.filter_hide_jogs.setChecked(True)
    assert _hidden(view)[-1] is True
    assert view._log.rowCount() == 5
    assert view.filter_count.text() == "2 of 5 hidden"


def test_port_list_grows_with_the_ports_seen_and_filters_by_port():
    view = _view()
    ports = [view.filter_port.itemData(i) for i in range(view.filter_port.count())]
    assert ports == ["", "DDJ-XP2", "CMD Studio 4a", "XDJ-XZ"]
    view.filter_port.setCurrentIndex(view.filter_port.findData("CMD Studio 4a"))
    assert view.visible_rows() == 1


def test_new_rows_follow_the_current_filter_and_events_are_still_emitted():
    view = _view()
    seen = []
    view.eventReceived.connect(seen.append)
    view.filter_kinds[BEND].setChecked(False)
    view._monitor.poll = lambda: [_event(PITCH_BEND, "0", "CMD Studio 4a", channel="2")]
    view._poll()
    assert view._log.isRowHidden(view._log.rowCount() - 1)
    assert len(seen) == 1  # the layouts, captures and macros still get it


def test_save_log_keeps_every_message(tmp_path):
    view = _view()
    view._events = [_event(), _event(PITCH_BEND, "0")]
    view.filter_kinds[NOTES].setChecked(False)
    out = tmp_path / "log.csv"
    assert view.save_log(out)
    assert out.read_text(encoding="utf-8").count("\n") >= 3  # header + both events


def test_clear_log_resets_the_count():
    view = _view()
    view.filter_kinds[NOTES].setChecked(False)
    view._clear_log()
    assert view.filter_count.text() == "" and view._log.rowCount() == 0
