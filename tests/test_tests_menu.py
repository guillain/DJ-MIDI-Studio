"""The Tests menu: hardware scenarios, Serato MIDI Learn and the test tools."""

from types import SimpleNamespace

import djmidi.gui.main_window as main_window_mod
from djmidi.gui.main_window import MainWindow
from djmidi.gui.serato_learn_dialog import SeratoLearnDialog
from djmidi.hardware_session import CHECKS, TOOL_ATELIER, TOOL_RECORD_SET, TOOLS
from djmidi.serato_learn import STEPS, default_port, is_echo


def _event(channel, note, port="IAC Driver Bus 1", velocity="127", direction="in"):
    return SimpleNamespace(direction=direction, event_type="Note On", channel=str(channel), data1=str(note),
                           data2=velocity, port=port)


def test_the_tests_menu_sits_between_macros_and_help():
    window = MainWindow()
    titles = [action.text() for action in window.menuBar().actions()]
    assert titles.index("&Tests") == titles.index("&Macros") + 1
    assert titles.index("&Help") == titles.index("&Tests") + 1
    texts = [action.text() for action in window._tests_menu.actions()]
    assert "&Hardware Scenarios..." in texts and "&Serato MIDI Learn..." in texts
    assert "MIDI Latency Test…" in texts
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Help")
    assert window._hardware_session_action not in help_menu.actions()


def test_every_check_tool_is_known_and_has_a_button_text():
    assert {check.tool for check in CHECKS if check.tool} <= set(TOOLS)
    assert len({check.id for check in CHECKS}) == len(CHECKS)


def test_a_scenario_opens_its_tool(monkeypatch):
    window = MainWindow()
    dialog = window.open_hardware_session()
    opened = []
    monkeypatch.setattr(window, "open_test_tool", lambda tool, controller="": opened.append((tool, controller)))
    dialog.toolRequested.disconnect()
    dialog.toolRequested.connect(window.open_test_tool)
    dialog.select_check("xp2-lights-tab")
    assert dialog.tool_button.isVisibleTo(dialog)
    dialog.open_tool()
    assert opened == [("profile-check", "DDJ-XP2")]
    dialog.select_check("cmd-micro-jog")
    assert not dialog.tool_button.isVisibleTo(dialog)


def test_open_test_tool_records_a_set_and_shows_the_atelier(monkeypatch):
    window = MainWindow()
    started = []
    monkeypatch.setattr(window.live_monitor_view, "start_recording", lambda: started.append(True))
    window.open_test_tool(TOOL_RECORD_SET)
    assert started == [True]
    window.open_test_tool(TOOL_ATELIER)
    assert window.left_tabs.currentIndex() == window._tab_indexes["atelier"]


def test_serato_learn_steps_are_distinct_and_find_the_iac_bus():
    assert len({(s.channel, s.note) for s in STEPS}) == len(STEPS)
    assert STEPS[0].label() == "Deck 1 · PLAY" and STEPS[-1].label() == "Deck 1 · HOT CUE 8"
    assert default_port(["DDJ-XP2", "IAC Driver Bus 1"]) == "IAC Driver Bus 1"
    assert default_port(["DDJ-XP2"]) == ""
    assert is_echo(STEPS[1], _event(1, 1), "IAC Driver Bus 1")
    assert not is_echo(STEPS[1], _event(1, 1, velocity="0"), "IAC Driver Bus 1")
    assert not is_echo(STEPS[1], _event(1, 1, port="DDJ-XP2"), "IAC Driver Bus 1")
    assert not is_echo(STEPS[1], _event(1, 1, direction="out"), "IAC Driver Bus 1")


def test_serato_learn_sends_then_moves_on_when_the_note_comes_back():
    sent = []
    dialog = SeratoLearnDialog(["IAC Driver Bus 1"], send=lambda **kw: sent.append(kw))
    assert dialog.port_combo.currentText() == "IAC Driver Bus 1"
    assert not dialog.feed_event(_event(1, 0))  # nothing sent yet: not consumed
    assert dialog.send_now()
    assert sent[0] == {"output_port_name": "IAC Driver Bus 1", "event_type": "Note On", "channel_1_based": 1,
                       "data1": 0, "data2": 127}
    assert dialog.feed_event(_event(1, 0))
    assert dialog.index == 1 and 0 in dialog.heard
    assert dialog.step_list.item(0).text().startswith("✓")


def test_serato_learn_says_when_the_bus_refuses_or_stays_silent():
    def refuse(**_kw):
        raise OSError("port gone")

    dialog = SeratoLearnDialog(["IAC Driver Bus 1"], send=refuse)
    assert not dialog.send_now()
    assert "port gone" in dialog.status.text()
    dialog = SeratoLearnDialog(["IAC Driver Bus 1"], send=lambda **_kw: None)
    dialog.send_now()
    dialog._echo_missed()
    assert "not seen" in dialog.status.text() and dialog.send_button.isEnabled()
    empty = SeratoLearnDialog([])
    assert not empty.send_button.isEnabled() and "IAC" in empty.status.text()


def test_main_window_routes_the_echo_to_serato_learn(monkeypatch):
    monkeypatch.setattr(main_window_mod, "list_output_ports", lambda: ["IAC Driver Bus 1"])
    window = MainWindow()
    monkeypatch.setattr(window, "_ensure_learn_listening", lambda: True)
    played = []
    monkeypatch.setattr(window, "_play_triggered_macros", lambda event: played.append(event))
    dialog = window.open_serato_learn()
    assert window.open_serato_learn() is dialog
    dialog._send = lambda **_kw: None
    dialog.send_now()
    window._on_live_midi_event(main_window_mod.MidiEvent("in", "1", "Note On", "0", "127", 0.0, "IAC Driver Bus 1"))
    assert 0 in dialog.heard and played == []
