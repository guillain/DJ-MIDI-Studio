from pathlib import Path

from djmidi.gui.live_monitor import LiveMonitorView
from djmidi.midi_io import MidiEvent
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


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
    event = MidiEvent(
        direction="in",
        channel="8",
        event_type="Note On",
        data1="64",
        data2="127",
        timestamp=0.0,
        port="DDJ-XP2",
    )
    view._append_event(event)
    assert view._log.rowCount() == 1
    assert view._log.item(0, 1).text() == "IN"
    assert view._log.item(0, 2).text() == "DDJ-XP2"
    assert view._log.item(0, 3).text() == "8"
    detail = view._log.item(0, 7).text()
    assert "PAD" in detail
    assert "DDJ-1000" not in detail
    assert "codfather_st" in detail


def test_append_event_unknown_control_shows_placeholder():
    view = LiveMonitorView()
    event = MidiEvent(direction="in", channel="99", event_type="Note On", data1="99", data2="1", timestamp=0.0)
    view._append_event(event)
    assert view._log.item(0, 7).text() == "(unknown)"


def test_log_is_capped_at_max_rows():
    from djmidi.gui import live_monitor as live_monitor_mod

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
    import djmidi.gui.live_monitor as live_monitor_mod

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


def test_ensure_monitoring_started_opens_every_available_port(monkeypatch):
    import djmidi.gui.live_monitor as live_monitor_mod

    view = LiveMonitorView()
    monkeypatch.setattr(live_monitor_mod, "list_input_ports", lambda: ["Port A", "Port B"])
    opened = []
    monkeypatch.setattr(view._monitor, "open_input", lambda name: opened.append(name))

    view.ensure_monitoring_started()

    assert opened == ["Port A", "Port B"]
    assert view._running is True
    assert "auto-started" in view._status_label.text()


def test_ensure_monitoring_started_is_a_noop_when_already_running(monkeypatch):
    import djmidi.gui.live_monitor as live_monitor_mod

    view = LiveMonitorView()
    monkeypatch.setattr(live_monitor_mod, "list_input_ports", lambda: ["Port A"])
    opened = []
    monkeypatch.setattr(view._monitor, "open_input", lambda name: opened.append(name))
    view._running = True  # simulate an already-running, user-picked session

    view.ensure_monitoring_started()

    assert opened == []  # never touched the user's existing selection


def test_ensure_monitoring_started_skips_a_port_that_fails_to_open(monkeypatch):
    """One busy/unavailable port must not block monitoring on the rest, and
    must not raise or pop a dialog -- this runs silently on mapping load."""
    import djmidi.gui.live_monitor as live_monitor_mod

    view = LiveMonitorView()
    monkeypatch.setattr(live_monitor_mod, "list_input_ports", lambda: ["Bad Port", "Good Port"])

    opened = []

    def fake_open(name):
        if name == "Bad Port":
            raise RuntimeError("device busy")
        opened.append(name)

    monkeypatch.setattr(view._monitor, "open_input", fake_open)

    view.ensure_monitoring_started()

    assert opened == ["Good Port"]
    assert view._running is True


def test_ensure_monitoring_started_stays_stopped_when_every_port_fails(monkeypatch):
    import djmidi.gui.live_monitor as live_monitor_mod

    view = LiveMonitorView()
    monkeypatch.setattr(live_monitor_mod, "list_input_ports", lambda: ["Bad Port"])

    def fake_open(name):
        raise RuntimeError("device busy")

    monkeypatch.setattr(view._monitor, "open_input", fake_open)

    view.ensure_monitoring_started()  # must not raise

    assert view._running is False


def test_ensure_monitoring_started_with_no_available_ports_stays_stopped(monkeypatch):
    import djmidi.gui.live_monitor as live_monitor_mod

    view = LiveMonitorView()
    monkeypatch.setattr(live_monitor_mod, "list_input_ports", list)

    view.ensure_monitoring_started()

    assert view._running is False


def test_shutdown_when_never_started_does_not_raise():
    view = LiveMonitorView()
    view.shutdown()  # should be a no-op, not raise
