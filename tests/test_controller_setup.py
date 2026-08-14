import json
from pathlib import Path

from seratomidiconf import catalog
from seratomidiconf.catalog._registry import ControlInfo
from seratomidiconf.catalog.codegen import generate_module_source, merge_by_channel
from seratomidiconf.gui.controller_setup import ControllerSetupView, _slugify
from seratomidiconf.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def _view_with_name(name: str = "MiniPad") -> ControllerSetupView:
    view = ControllerSetupView()
    view._name_edit.setText(name)
    return view


def test_slugify_lowercases_and_underscores():
    assert _slugify("Behringer CMD LC-1") == "behringer_cmd_lc_1"
    assert _slugify("  ") == ""
    assert _slugify("2Pad") == "_2pad"


def test_new_session_resets_name_and_rows():
    view = _view_with_name()
    view._maybe_add_row("1", "NOTE", "0", "manual")
    assert view._rows
    view._reset(clear_name=True)
    assert view._rows == []
    assert view._controller_name == ""
    assert view._name_edit.text() == ""


def test_clear_captured_rows_keeps_controller_name():
    view = _view_with_name("MiniPad")
    view._maybe_add_row("1", "NOTE", "0", "manual")
    view._reset(clear_name=False)
    assert view._rows == []
    assert view._controller_name == "MiniPad"


def test_maybe_add_row_appends_new_row():
    view = _view_with_name()
    added = view._maybe_add_row("1", "NOTE", "10", "learned")
    assert added is True
    assert len(view._rows) == 1
    assert view._sources == ["learned"]
    assert view._devices == [""]
    assert view._table.rowCount() == 1


def test_maybe_add_row_records_device():
    view = _view_with_name()
    view._maybe_add_row("1", "NOTE", "10", "learned", "IAC Driver Bus 1")
    assert view._devices == ["IAC Driver Bus 1"]
    assert view._table.item(0, 6).text() == "IAC Driver Bus 1"


def test_maybe_add_row_dedups_repeated_learn_event():
    view = _view_with_name()
    view._maybe_add_row("1", "NOTE", "10", "learned")
    added_again = view._maybe_add_row("1", "NOTE", "10", "learned")
    assert added_again is False
    assert len(view._rows) == 1


def test_maybe_add_row_same_control_different_channel_not_deduped():
    view = _view_with_name()
    view._maybe_add_row("1", "NOTE", "10", "learned")
    view._maybe_add_row("2", "NOTE", "10", "learned")
    assert len(view._rows) == 2


def test_import_from_xml_seeds_unique_triples():
    view = _view_with_name()
    config = parse_file(FIXTURE)
    unique_triples = {(c.channel, c.event_type, c.control) for c in config.controls}

    added = view._import_config(config)
    assert added == len(unique_triples)
    assert len(view._rows) == len(unique_triples)

    added_again = view._import_config(config)
    assert added_again == 0
    assert len(view._rows) == len(unique_triples)


def test_import_from_xml_rows_have_empty_section_and_name():
    view = _view_with_name()
    config = parse_file(FIXTURE)
    view._import_config(config)
    assert view._rows
    assert all(row.section == "" and row.name == "" for row in view._rows)
    assert all(source == "xml-import" for source in view._sources)


def test_import_from_xml_records_source_file_as_device():
    view = _view_with_name()
    config = parse_file(FIXTURE)
    view._import_config(config, FIXTURE.name)
    assert view._rows
    assert all(device == FIXTURE.name for device in view._devices)


def test_session_save_and_load_roundtrip(tmp_path):
    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1", "2"), "0")]
    view._sources = ["manual"]
    view._devices = ["IAC Driver Bus 1"]

    session_path = tmp_path / "session.json"
    view._save_session(session_path)
    assert not view._dirty

    reloaded = ControllerSetupView()
    reloaded._load_session(session_path)
    assert reloaded._controller_name == "MiniPad"
    assert reloaded._name_edit.text() == "MiniPad"
    assert reloaded._rows == view._rows
    assert reloaded._sources == ["manual"]
    assert reloaded._devices == ["IAC Driver Bus 1"]
    assert not reloaded._dirty


def test_load_session_rejects_unknown_version(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"version": 2, "controller_name": "X", "rows": []}))
    view = ControllerSetupView()
    try:
        view._load_session(path)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_validate_reports_missing_name_and_section():
    view = _view_with_name()
    view._maybe_add_row("1", "NOTE", "0", "manual")
    errors = view._validate()
    assert any("Name" in e for e in errors)
    assert any("Section" in e for e in errors)


def test_validate_rejects_bad_data1():
    view = _view_with_name()
    view._maybe_add_row("1", "NOTE", "200", "manual")
    view._maybe_add_row("1", "NOTE", "abc", "manual")
    errors = view._validate()
    assert any("Data1" in e for e in errors)


def test_validate_reports_conflicting_hand_edited_trigger():
    view = _view_with_name("MiniPad")
    view._rows = [
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
        ControlInfo("MiniPad", "DECK", "CUE", "NOTE", ("1",), "0"),
    ]
    view._sources = ["manual", "manual"]
    view._devices = ["", ""]
    errors = view._validate()
    assert any("claimed by" in e for e in errors)


def test_check_for_conflicts_button_shows_no_conflicts_for_clean_draft(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]

    shown = {}

    def fake_information(parent, title, text):
        shown["title"] = title
        shown["text"] = text

    monkeypatch.setattr(controller_setup_mod.QMessageBox, "information", fake_information)
    view._on_check_conflicts_clicked()
    assert shown["title"] == "No conflicts"


def test_validate_passes_for_well_formed_rows():
    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    assert view._validate() == []


def test_export_writes_file_matching_codegen(tmp_path):
    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]

    out_path = tmp_path / "minipad.py"
    view._export_module(out_path)

    expected = generate_module_source("MiniPad", merge_by_channel(view._rows))
    assert out_path.read_text() == expected


def test_shutdown_when_never_started_does_not_raise():
    view = _view_with_name()
    view.shutdown()


def test_apply_registers_in_live_catalog_and_emits_signal():
    view = _view_with_name("__ApplySetupTest__")
    view._rows = [ControlInfo("__ApplySetupTest__", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]

    emitted = []
    view.controllerApplied.connect(emitted.append)
    try:
        view._apply()
        assert emitted == ["__ApplySetupTest__"]
        assert "__ApplySetupTest__" in catalog.CONTROLLER_NAMES
        hits = catalog.lookup("1", "Note On", "0")
        assert any(h.controller == "__ApplySetupTest__" and h.name == "PLAY" for h in hits)
    finally:
        catalog._registry._REGISTRY.pop("__ApplySetupTest__", None)


def test_apply_twice_replaces_previous_definition():
    view = _view_with_name("__ApplySetupTest2__")
    view._rows = [ControlInfo("__ApplySetupTest2__", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    try:
        view._apply()
        view._rows = [ControlInfo("__ApplySetupTest2__", "DECK", "CUE", "NOTE", ("1",), "1")]
        view._apply()
        hits = catalog.lookup("1", "Note On", "1")
        assert any(h.name == "CUE" for h in hits)
        stale_hits = catalog.lookup("1", "Note On", "0")
        assert not any(h.controller == "__ApplySetupTest2__" for h in stale_hits)
    finally:
        catalog._registry._REGISTRY.pop("__ApplySetupTest2__", None)


def test_on_apply_clicked_blocks_overwriting_a_controller_it_never_applied(monkeypatch):
    """The real bug: naming a draft "DDJ-XP2" and clicking Apply used to silently
    replace the real, hand-written ~45-entry DDJ-XP2 definition in memory with the
    tiny draft, breaking every other tab until restart. A draft may only replace a
    name *it* previously applied itself, never a pre-existing/other controller."""
    import seratomidiconf.gui.controller_setup as controller_setup_mod
    from seratomidiconf.catalog._registry import ControllerDefinition
    from seratomidiconf.catalog._registry import register as registry_register

    registry_register(ControllerDefinition(name="__PreExistingController__"))
    try:
        view = _view_with_name("__PreExistingController__")
        view._rows = [ControlInfo("__PreExistingController__", "DECK", "PLAY", "NOTE", ("1",), "0")]
        view._sources = ["manual"]
        view._devices = [""]

        shown = {}
        monkeypatch.setattr(
            controller_setup_mod.QMessageBox,
            "critical",
            lambda parent, title, text: shown.update(title=title, text=text),
        )
        view._on_apply_clicked()
        assert shown.get("title") == "Cannot apply"
        assert catalog.get_definition("__PreExistingController__").static_entries == []
    finally:
        catalog._registry._REGISTRY.pop("__PreExistingController__", None)


def test_apply_allows_reapplying_a_name_this_same_draft_already_applied(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    monkeypatch.setattr(controller_setup_mod.QMessageBox, "information", lambda *a: None)
    monkeypatch.setattr(controller_setup_mod.QMessageBox, "critical", lambda *a: None)

    view = _view_with_name("__ApplySetupTest5__")
    view._rows = [ControlInfo("__ApplySetupTest5__", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    try:
        view._apply()
        # Re-applying the same draft under the same name must not be blocked.
        view._rows = [ControlInfo("__ApplySetupTest5__", "DECK", "CUE", "NOTE", ("1",), "1")]
        view._on_apply_clicked()
        hits = catalog.lookup("1", "Note On", "1")
        assert any(h.name == "CUE" for h in hits)
    finally:
        catalog._registry._REGISTRY.pop("__ApplySetupTest5__", None)


def test_on_apply_clicked_blocks_on_validation_errors(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    view = _view_with_name("__ApplySetupTest3__")
    view._maybe_add_row("1", "NOTE", "0", "manual")  # missing name/section

    shown = {}
    monkeypatch.setattr(controller_setup_mod.QMessageBox, "warning", lambda *a: shown.setdefault("warned", True))
    view._on_apply_clicked()
    assert shown.get("warned") is True
    assert "__ApplySetupTest3__" not in catalog.CONTROLLER_NAMES


def test_on_apply_clicked_surfaces_unexpected_exception_instead_of_failing_silently(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    view = _view_with_name("__ApplySetupTest4__")
    view._rows = [ControlInfo("__ApplySetupTest4__", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]

    def boom() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(view, "_apply", boom)
    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "critical",
        lambda parent, title, text: shown.update(title=title, text=text),
    )
    view._on_apply_clicked()
    assert shown.get("title") == "Failed to apply"
    assert "boom" in shown.get("text", "")
    assert "__ApplySetupTest4__" not in catalog.CONTROLLER_NAMES


def test_refresh_output_ports_populates_list(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A", "Port B"])
    view._refresh_output_ports()
    assert view._output_port_list.count() == 2
    assert view._output_port_list.item(0).text() == "Port A"


def test_send_output_once_uses_selected_output_port_and_values(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(
        controller_setup_mod,
        "send_midi_message",
        lambda **kwargs: sent.append(kwargs),
    )
    view._refresh_output_ports()
    view._send_type_edit.setText("note_on")
    view._send_channel_edit.setText("1")
    view._send_data1_edit.setText("27")
    view._send_data2_edit.setText("127")
    view._on_send_output_once_clicked()
    assert len(sent) == 1
    assert sent[0]["output_port_name"] == "Port A"
    assert sent[0]["event_type"] == "note_on"


def test_send_output_double_click_sends_two_clicks(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(
        controller_setup_mod,
        "send_midi_message",
        lambda **kwargs: sent.append(kwargs),
    )

    # Execute delayed callback immediately in tests.
    monkeypatch.setattr(
        controller_setup_mod.QTimer,
        "singleShot",
        lambda _ms, callback: callback(),
    )

    view._refresh_output_ports()
    view._send_data1_edit.setText("27")
    view._send_data2_edit.setText("127")
    view._send_delay_ms_edit.setText("0")
    view._on_send_output_double_clicked()
    # 2 clicks = 4 messages (note_on + note_off, twice)
    assert len(sent) == 4
    assert sent[0]["event_type"] == "note_on"
    assert sent[1]["event_type"] == "note_off"


def test_ddj_xp2_pad_mode_5_uses_double_click_on_mode_1(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(
        controller_setup_mod,
        "send_midi_message",
        lambda **kwargs: sent.append(kwargs),
    )
    monkeypatch.setattr(
        controller_setup_mod.QTimer,
        "singleShot",
        lambda _ms, callback: callback(),
    )

    view._refresh_output_ports()
    view._send_data2_edit.setText("127")
    view._send_delay_ms_edit.setText("0")
    view._on_send_ddj_xp2_pad_mode(5)
    assert len(sent) == 4
    assert all(msg["data1"] == 27 for msg in sent)


def test_play_session_rows_once_sends_note_click_and_cc(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    view._rows = [
        ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10"),
        ControlInfo("MiniPad", "KNOB", "B", "CC", ("2",), "20"),
    ]
    view._sources = ["manual", "manual"]
    view._devices = ["", ""]
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(controller_setup_mod, "send_midi_message", lambda **kwargs: sent.append(kwargs))
    view._refresh_output_ports()
    sent_count, skipped = view._play_session_rows_once([0, 1])
    assert sent_count == 3
    assert skipped == 0
    assert sent[0]["event_type"] == "note_on"
    assert sent[1]["event_type"] == "note_off"
    assert sent[2]["event_type"] == "control_change"


def test_play_session_rows_once_skips_invalid_rows(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    view._rows = [ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "abc")]
    view._sources = ["manual"]
    view._devices = [""]
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(controller_setup_mod, "send_midi_message", lambda **kwargs: sent.append(kwargs))
    view._refresh_output_ports()
    sent_count, skipped = view._play_session_rows_once([0])
    assert sent_count == 0
    assert skipped == 1
    assert sent == []


def test_send_selected_rows_uses_table_selection(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    view._rows = [
        ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10"),
        ControlInfo("MiniPad", "PAD", "B", "NOTE", ("1",), "11"),
    ]
    view._sources = ["manual", "manual"]
    view._devices = ["", ""]
    view._rebuild_table()
    view._table.clearSelection()
    view._table.selectRow(0)
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(controller_setup_mod, "send_midi_message", lambda **kwargs: sent.append(kwargs))
    view._refresh_output_ports()
    view._on_send_selected_rows_clicked()
    assert len(sent) == 2
    assert all(msg["data1"] == 10 for msg in sent)


def test_rows_loop_start_and_stop(monkeypatch):
    import seratomidiconf.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    view._rows = [ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10")]
    view._sources = ["manual"]
    view._devices = [""]
    view._send_loop_hz_edit.setText("5")
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    monkeypatch.setattr(controller_setup_mod, "send_midi_message", lambda **kwargs: None)
    view._refresh_output_ports()
    view._on_start_rows_loop_clicked()
    assert view._send_loop_timer.isActive()
    assert view._send_loop_timer.interval() == 200
    view._on_stop_rows_loop_clicked()
    assert not view._send_loop_timer.isActive()


