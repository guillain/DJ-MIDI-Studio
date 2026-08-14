from pathlib import Path

from seratomidiconf.gui.live_monitor import LiveMonitorView
from seratomidiconf.midi_io import MidiEvent
from seratomidiconf.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def test_set_config_builds_function_lookup_from_real_file():
    view = LiveMonitorView()
    config = parse_file(FIXTURE)
    view.set_config(config)
    functions = view._function_lookup.get(("8", "Note On", "64"))
    assert functions is not None
    assert any("codfather_st" in f for f in functions)


def test_set_config_none_clears_function_lookup():
    view = LiveMonitorView()
    view.set_config(parse_file(FIXTURE))
    assert view._function_lookup
    view.set_config(None)
    assert view._function_lookup == {}


def test_append_event_populates_log_row_with_catalog_and_function_info():
    view = LiveMonitorView()
    view.set_config(parse_file(FIXTURE))
    event = MidiEvent(direction="in", channel="8", event_type="Note On", data1="64", data2="127", timestamp=0.0)
    view._append_event(event)
    assert view._log.rowCount() == 1
    assert view._log.item(0, 1).text() == "IN"
    assert view._log.item(0, 2).text() == "8"
    detail = view._log.item(0, 6).text()
    assert "DDJ-XP2" in detail
    assert "codfather_st" in detail


def test_append_event_unknown_control_shows_placeholder():
    view = LiveMonitorView()
    event = MidiEvent(direction="in", channel="99", event_type="Note On", data1="99", data2="1", timestamp=0.0)
    view._append_event(event)
    assert view._log.item(0, 6).text() == "(unknown)"


def test_log_is_capped_at_max_rows():
    from seratomidiconf.gui import live_monitor as live_monitor_mod

    original_max_rows = live_monitor_mod._MAX_ROWS
    live_monitor_mod._MAX_ROWS = 5
    try:
        view = LiveMonitorView()
        for i in range(10):
            event = MidiEvent(direction="in", channel="1", event_type="Note On", data1=str(i), data2="1", timestamp=0.0)
            view._append_event(event)
        assert view._log.rowCount() == 5
    finally:
        live_monitor_mod._MAX_ROWS = original_max_rows


def test_clear_log_empties_table_and_event_history():
    view = LiveMonitorView()
    event = MidiEvent(direction="in", channel="1", event_type="Note On", data1="1", data2="1", timestamp=0.0)
    view._events.append(event)
    view._append_event(event)
    view._clear_log()
    assert view._log.rowCount() == 0
    assert view._events == []


def test_save_log_writes_csv_with_event_fields(tmp_path, monkeypatch):
    import seratomidiconf.gui.live_monitor as live_monitor_mod

    view = LiveMonitorView()
    view._events = [MidiEvent("out", "2", "Control Change", "10", "64", 12.5, "MIDI Out")]
    path = tmp_path / "monitor.csv"
    monkeypatch.setattr(
        live_monitor_mod.QFileDialog,
        "getSaveFileName",
        lambda *args: (str(path), "CSV files (*.csv)"),
    )

    view._save_log()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Timestamp,Direction,Port,Channel,Type,Data1,Data2"
    assert "12.5,out,MIDI Out,2,Control Change,10,64" in lines[1]
    assert "Saved 1 MIDI event(s)" in view._status_label.text()


def test_shutdown_when_never_started_does_not_raise():
    view = LiveMonitorView()
    view.shutdown()  # should be a no-op, not raise
