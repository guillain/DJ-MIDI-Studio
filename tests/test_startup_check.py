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
        ["DDJ-XP2"],
        [],
        sync_controllers={"DDJ-XP2"},
        has_captures=lambda c: True,
        has_leds=lambda c: True,
    )
    assert [i.status for i in report.items] == [
        sc.OK
    ] and not report.needing_attention()


def test_two_ports_of_one_controller_make_one_card_and_own_ports_are_skipped():
    report = sc.check_startup(
        ["XDJ-XZ (1)", "XDJ-XZ (2)", "IAC Driver Bus 1", "DJMidiStudio Monitor"], []
    )
    assert report.devices == ["XDJ-XZ"]


def test_an_unknown_device_is_offered_learning():
    item = sc.check_startup(["MIDI4x4 Midi In 1"], []).items[0]
    assert (item.device, item.action, item.id) == (
        "MIDI4x4 Midi In 1",
        sc.LEARN,
        "unknown:MIDI4x4 Midi In 1",
    )


def test_an_offline_iac_bus_blocks_the_macros_that_use_it_first():
    macros = [
        _macro("CUE → PLAY deck 1", "IAC Driver Bus 1"),
        _macro("Pad", "IAC Driver Bus 1"),
    ]
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
    report = sc.check_startup(
        ["DDJ-XP2", "MIDI4x4 Midi In 1"], [], [_macro("M", "IAC Driver Bus 1")]
    )
    dialog = StartupCheckDialog(report)
    assert dialog.card_titles() == ["IAC Driver Bus 1", "DDJ-XP2", "MIDI4x4 Midi In 1"]
    assert "won't work" in dialog.headline.text()
    actions, hidden = [], []
    dialog.actionRequested.connect(actions.append)
    dialog.dismissed.connect(hidden.append)
    buttons = [
        b
        for b in dialog.findChildren(type(dialog.recheck_button))
        if b.text() == "Teach it"
    ]
    buttons[0].click()
    assert actions[0].action == sc.LEARN
    dialog.dismiss("iac:IAC Driver Bus 1")
    assert (
        hidden == ["iac:IAC Driver Bus 1"]
        and "IAC Driver Bus 1" not in dialog.card_titles()
    )
    assert "Almost ready" in dialog.headline.text()


def test_everything_ready_says_so():
    report = sc.check_startup(
        ["DDJ-XP2"], [], sync_controllers={"DDJ-XP2"}, has_captures=bool, has_leds=bool
    )
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


# -- step 2: macro triggers that the DJ's Serato mapping uses too ---------------

_SERATO = """<midi app=" 4.0.9.3040">
    <control channel="8" event_type="Note On" control="{note}">
        <userio event="click">
            <codfather_st deck_set="Default" deck_id="0" slot_id="0">
                <translation action_on="press" behaviour="toggle"/>
            </codfather_st>
        </userio>
    </control>
</midi>
"""


def _serato(tmp_path, name, note):
    path = tmp_path / name
    path.write_text(_SERATO.format(note=note))
    return path


def _trigger_macro(name, channel, note, port="DDJ-XP2"):
    from djmidi.midi_macros import MacroTrigger

    return SimpleNamespace(
        name=name,
        output_port="",
        triggers=(MacroTrigger.create("Note On", channel, note, port),),
    )


def test_a_trigger_serato_uses_is_offered_the_first_free_pad_of_its_mode(tmp_path):
    files = [_serato(tmp_path, "ddj-xp2-custom.xml", 80)]
    macros = [
        _trigger_macro("CUE → PLAY deck 1", 8, 80),
        _trigger_macro("Other", 8, 81),
    ]
    item = next(
        i
        for i in sc.check_startup(["DDJ-XP2"], [], macros, serato_files=files).items
        if i.id.startswith("serato")
    )
    params = dict(item.params)
    assert (item.status, item.action, item.device) == (
        sc.BLOCKING,
        sc.MOVE_TRIGGER,
        "DDJ-XP2",
    )
    assert (
        params["trigger"] == "Deck 1 Pad 1 (PAD MODE 6)"
        and params["file"] == "ddj-xp2-custom.xml"
    )
    # pad 2 (note 81) is another macro's trigger: the next free pad is pad 3
    assert (params["pad"], params["note"]) == ("Deck 1 Pad 3 (PAD MODE 6)", "82")


def test_another_devices_serato_file_is_ignored(tmp_path):
    files = [_serato(tmp_path, "CMD-LC1.xml", 80)]
    report = sc.check_startup(
        ["DDJ-XP2"], [], [_trigger_macro("M", 8, 80)], serato_files=files
    )
    assert not [i for i in report.items if i.id.startswith("serato")]


def test_no_free_pad_points_to_the_macros(tmp_path):
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"
    copy = tmp_path / "xdj-xz ddj-xp2.xml"
    copy.write_bytes(fixture.read_bytes())  # binds every PAD MODE 5 pad of deck 1
    report = sc.check_startup(
        ["DDJ-XP2"], [], [_trigger_macro("M", 8, 64)], serato_files=[copy]
    )
    item = next(i for i in report.items if i.id.startswith("serato"))
    assert (item.text_key, item.action) == ("trigger_in_serato_no_free", sc.MACROS)


def test_the_window_offers_the_move_and_main_window_applies_it(monkeypatch, tmp_path):
    from djmidi import midi_macros
    from djmidi.gui import main_window as mw

    monkeypatch.setattr(mw, "list_input_ports", lambda: ["DDJ-XP2"])
    monkeypatch.setattr(mw, "list_output_ports", list)
    files = [_serato(tmp_path, "ddj-xp2-custom.xml", 80)]
    window = mw.MainWindow()
    monkeypatch.setattr(window, "_serato_mapping_files", lambda: files)
    window.macros = [
        midi_macros.MidiMacro(
            "CUE", "", (), triggers=_trigger_macro("CUE", 8, 80).triggers
        )
    ]
    dialog = window.open_startup_check()
    move = [
        b
        for b in dialog.findChildren(type(dialog.recheck_button))
        if b.text().startswith("Move to")
    ]
    assert [b.text() for b in move] == ["Move to Deck 1 Pad 2 (PAD MODE 6)"]
    move[0].click()
    assert [(t.channel, t.data1, t.port) for t in window.macros[0].triggers] == [
        (8, 81, "DDJ-XP2")
    ]
    assert [m.name for m in midi_macros.load_macros(mw.user_paths.macros_dir())] == [
        "CUE"
    ]
    assert not [i for i in dialog.report.items if i.id.startswith("serato")]


# -- step 3: a device plugged in later -----------------------------------------


def test_a_device_plugged_in_later_opens_the_check_once(monkeypatch):
    from djmidi.gui import main_window as mw

    ports = []
    monkeypatch.setattr(mw, "list_input_ports", lambda: list(ports))
    monkeypatch.setattr(mw, "list_output_ports", list)
    window = mw.MainWindow()
    assert window.watch_plugged_devices() is None  # learns the current ports
    ports.append("DDJ-XP2")
    dialog = window.watch_plugged_devices()
    assert dialog is not None and dialog.card_titles() == ["DDJ-XP2"]
    dialog.close()
    _process_events()
    ports.remove("DDJ-XP2")
    assert window.watch_plugged_devices() is None  # unplugged: nothing
    ports.append("DDJ-XP2")
    assert window.watch_plugged_devices() is None  # same items, already shown


def _process_events():
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
