"""The startup check: connected devices vs what the app knows, each gap
with the action that closes it (golden rule: features become obvious)."""

from types import SimpleNamespace

from djmidi import startup_check as sc
from djmidi.gui.startup_check_dialog import StartupCheckDialog


def _macro(name, port):
    return SimpleNamespace(name=name, output_port=port)


def test_a_known_controller_lists_each_missing_step():
    report = sc.check_startup(["DDJ-XP2"], ["DDJ-XP2"])
    assert report.devices == ["DDJ-XP2"]
    assert [(i.action, i.status) for i in report.items] == [
        (sc.CHECK, sc.TODO),
        (sc.LEDS, sc.TODO),
        (sc.SCENE, sc.TODO),
    ]


def test_a_finished_controller_is_ready_and_needs_nothing():
    report = sc.check_startup(
        ["DDJ-XP2"], [], sync_controllers={"DDJ-XP2"}, has_captures=lambda c: True, has_leds=lambda c: True
    )
    assert [i.status for i in report.items] == [sc.OK] and not report.needing_attention()


def test_two_ports_of_one_controller_make_one_card_and_own_ports_are_skipped():
    report = sc.check_startup(["XDJ-XZ (1)", "XDJ-XZ (2)", "IAC Driver Bus 1", "DJMidiStudio Monitor"], [])
    assert report.devices == ["XDJ-XZ"]


def test_an_unknown_device_is_offered_learning():
    item = sc.check_startup(["MIDI4x4 Midi In 1"], []).items[0]
    assert (item.device, item.action, item.id) == ("MIDI4x4 Midi In 1", sc.LEARN, "unknown:MIDI4x4 Midi In 1")


def test_an_offline_iac_bus_blocks_the_macros_that_use_it_first():
    macros = [_macro("CUE → PLAY deck 1", "IAC Driver Bus 1"), _macro("Pad", "IAC Driver Bus 1")]
    report = sc.check_startup(["DDJ-XP2"], ["DDJ-XP2"], macros)
    first = report.items[0]
    assert (first.status, first.action) == (sc.BLOCKING, sc.IAC)
    assert "2 macro(s)" in first.text() and "CUE → PLAY deck 1" in first.text()


def test_a_macro_on_an_unplugged_controller_only_asks_to_plug_it_in():
    report = sc.check_startup([], [], [_macro("Deck 3", "DDJ-XP2")])
    statuses = {(i.id, i.status, i.action) for i in report.items}
    assert ("unplugged:DDJ-XP2", sc.TODO, None) in statuses
    assert ("nothing-plugged", sc.TODO, None) in statuses


def test_a_macro_on_a_missing_unknown_port_blocks():
    item = sc.check_startup([], [], [_macro("X", "Some Synth")]).items[0]
    assert (item.status, item.action) == (sc.BLOCKING, sc.MACROS)


def test_dismissed_items_need_no_attention():
    report = sc.check_startup(["DDJ-XP2"], [])
    assert report.needing_attention({i.id for i in report.items}) == []


def test_the_window_groups_by_device_and_emits_actions_and_dismissals():
    report = sc.check_startup(["DDJ-XP2", "MIDI4x4 Midi In 1"], [], [_macro("M", "IAC Driver Bus 1")])
    dialog = StartupCheckDialog(report)
    assert dialog.card_titles() == ["IAC Driver Bus 1", "DDJ-XP2", "MIDI4x4 Midi In 1"]
    assert "won't work" in dialog.headline.text()
    actions, hidden = [], []
    dialog.actionRequested.connect(actions.append)
    dialog.dismissed.connect(hidden.append)
    buttons = [b for b in dialog.findChildren(type(dialog.recheck_button)) if b.text() == "Teach it"]
    buttons[0].click()
    assert actions[0].action == sc.LEARN
    dialog.dismiss("iac:IAC Driver Bus 1")
    assert hidden == ["iac:IAC Driver Bus 1"] and "IAC Driver Bus 1" not in dialog.card_titles()
    assert "Almost ready" in dialog.headline.text()


def test_everything_ready_says_so():
    report = sc.check_startup(["DDJ-XP2"], [], sync_controllers={"DDJ-XP2"}, has_captures=bool, has_leds=bool)
    assert "All set" in StartupCheckDialog(report).headline.text()


def test_main_window_routes_actions_to_the_tools(monkeypatch):
    from djmidi.gui import main_window as mw

    monkeypatch.setattr(mw, "list_input_ports", lambda: ["DDJ-XP2"])
    monkeypatch.setattr(mw, "list_output_ports", list)
    window = mw.MainWindow()
    dialog = window.open_startup_check()
    assert dialog.card_titles() == ["DDJ-XP2"]
    scene = next(i for i in dialog.report.items if i.action == sc.SCENE)
    dialog.actionRequested.emit(scene)
    assert window.left_tabs.currentIndex() == window._tab_indexes["atelier"]
    assert window.atelier_view.controller_combo.currentText() == "DDJ-XP2"
    learn = sc.StartupItem("unknown:X", "X", sc.TODO, "unknown", sc.LEARN)
    dialog.actionRequested.emit(learn)
    assert window.left_tabs.currentIndex() == window._tab_indexes["setup"]
    dialog.dismiss(scene.id)
    assert scene.id in window._startup_check_dismissed()
    assert window.open_startup_check() is dialog
