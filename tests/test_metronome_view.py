from __future__ import annotations

from djmidi.catalog._registry import ControlInfo
from djmidi.gui.metronome_view import MetronomeView


def _entries() -> list[ControlInfo]:
    return [ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10")]


def _selected_entries() -> list[ControlInfo]:
    return [ControlInfo("MiniPad", "PAD", "B", "NOTE", ("2",), "11")]


def _view() -> MetronomeView:
    return MetronomeView(
        all_rows_provider=_entries,
        selected_rows_provider=_selected_entries,
        session_name_provider=lambda: "MiniPad",
    )


def test_refresh_session_summary_shows_current_session_info():
    view = _view()
    view.refresh_session_summary()
    text = view._session_summary.text()
    assert "MiniPad" in text
    assert "All rows: 1" in text
    assert "Selected rows" in text


def test_refresh_output_ports_populates_list(monkeypatch):
    import djmidi.gui.metronome_view as metronome_mod

    view = _view()
    monkeypatch.setattr(metronome_mod, "list_output_ports", lambda: ["Port A", "Port B"])
    view._refresh_output_ports()
    assert view._output_port_list.count() == 2
    assert view._output_port_list.item(0).text() == "Port A"


def test_play_selected_once_sends_messages(monkeypatch):
    import djmidi.gui.metronome_view as metronome_mod

    view = _view()
    monkeypatch.setattr(metronome_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(
        metronome_mod,
        "play_control_info_entries",
        lambda port, entries, value: type("Stats", (), {"sent_messages": 2, "skipped_entries": 0})(),
    )
    view._refresh_output_ports()
    view._on_play_selected_once_clicked()
    assert "Played selected rows once" in view._status.text()


def test_play_all_once_reports_errors(monkeypatch):
    import djmidi.gui.metronome_view as metronome_mod

    view = _view()
    errors = []
    monkeypatch.setattr(
        metronome_mod.QMessageBox,
        "critical",
        lambda _parent, title, message: errors.append((title, message)),
    )
    view._output_port_list.clear()

    view._on_play_all_once_clicked()

    assert errors == [("Failed to play rows", "No output port selected")]


def test_start_and_stop_loop(monkeypatch):
    import djmidi.gui.metronome_view as metronome_mod

    view = _view()
    monkeypatch.setattr(metronome_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(
        metronome_mod,
        "play_control_info_entries",
        lambda port, entries, value: type("Stats", (), {"sent_messages": 2, "skipped_entries": 0})(),
    )
    view._refresh_output_ports()
    view._hz_edit.setText("4")
    view._start_loop("selected")
    assert view._loop_timer.isActive()
    assert view._loop_timer.interval() == 250
    view._stop_loop()
    assert not view._loop_timer.isActive()


def test_start_loop_with_no_rows_shows_warning(monkeypatch):
    import djmidi.gui.metronome_view as metronome_mod

    warned = {}
    view = MetronomeView(
        all_rows_provider=list,
        selected_rows_provider=list,
        session_name_provider=lambda: "MiniPad",
    )
    monkeypatch.setattr(metronome_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(
        metronome_mod.QMessageBox,
        "warning",
        lambda *args: warned.setdefault("shown", True),
    )
    view._refresh_output_ports()
    view._start_loop("all")
    assert warned.get("shown") is True


def test_loop_tick_stops_and_reports_playback_errors(monkeypatch):
    import djmidi.gui.metronome_view as metronome_mod

    view = _view()
    errors = []
    monkeypatch.setattr(
        metronome_mod.QMessageBox,
        "critical",
        lambda _parent, title, message: errors.append((title, message)),
    )
    view._output_port_list.clear()
    view._loop_timer.start()

    view._on_loop_tick()

    assert not view._loop_timer.isActive()
    assert errors == [("Loop stopped", "No output port selected")]


def test_shutdown_stops_active_loop(monkeypatch):
    import djmidi.gui.metronome_view as metronome_mod

    view = _view()
    monkeypatch.setattr(metronome_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(
        metronome_mod,
        "play_control_info_entries",
        lambda port, entries, value: type("Stats", (), {"sent_messages": 2, "skipped_entries": 0})(),
    )
    view._refresh_output_ports()
    view._hz_edit.setText("2")
    view._start_loop("all")
    assert view._loop_timer.isActive()
    view.shutdown()
    assert not view._loop_timer.isActive()
