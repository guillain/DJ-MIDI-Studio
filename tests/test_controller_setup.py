import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from djmidi import catalog
from djmidi.catalog._registry import ControlInfo
from djmidi.catalog.codegen import generate_module_source, merge_by_channel
from djmidi.gui.controller_setup import ControllerSetupView, _slugify
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


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


def test_import_xml_click_offers_to_open_as_mapping_and_emits_on_yes(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(
        controller_setup_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (str(FIXTURE), "")
    )
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "question",
        lambda *a, **k: controller_setup_mod.QMessageBox.StandardButton.Yes,
    )
    emitted = []
    view.openMappingRequested.connect(emitted.append)
    view._on_import_xml_clicked()
    assert emitted == [str(FIXTURE)]


def test_import_xml_click_does_not_emit_on_no(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(
        controller_setup_mod.QFileDialog, "getOpenFileName", lambda *a, **k: (str(FIXTURE), "")
    )
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "question",
        lambda *a, **k: controller_setup_mod.QMessageBox.StandardButton.No,
    )
    emitted = []
    view.openMappingRequested.connect(emitted.append)
    view._on_import_xml_clicked()
    assert emitted == []


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
    import djmidi.gui.controller_setup as controller_setup_mod

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
    import djmidi.gui.controller_setup as controller_setup_mod
    from djmidi.catalog._registry import ControllerDefinition
    from djmidi.catalog._registry import register as registry_register

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
    import djmidi.gui.controller_setup as controller_setup_mod

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


def test_new_session_forgets_names_this_draft_previously_applied(monkeypatch):
    """A stale self._applied_names must not survive "New session": otherwise a
    later, unrelated draft that happens to reuse an earlier draft's name would
    sail past the hard-block and silently replace it in the live registry —
    exactly the bug _applied_names exists to prevent, just reached via a
    different path (New session) than test_on_apply_clicked_blocks_overwriting_
    a_controller_it_never_applied covers."""
    import djmidi.gui.controller_setup as controller_setup_mod

    monkeypatch.setattr(controller_setup_mod.QMessageBox, "information", lambda *a: None)
    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "critical",
        lambda parent, title, text: shown.update(title=title, text=text),
    )

    view = _view_with_name("__StaleAppliedNamesTest__")
    view._rows = [ControlInfo("__StaleAppliedNamesTest__", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    try:
        view._apply()
        assert "__StaleAppliedNamesTest__" in view._applied_names

        # Simulate clicking "New session": the old draft is gone, so its
        # applied-name permission must go with it.
        view._reset(clear_name=True)
        assert view._applied_names == set()

        # A brand-new, unrelated draft happens to reuse the same name.
        view._name_edit.setText("__StaleAppliedNamesTest__")
        view._rows = [
            ControlInfo("__StaleAppliedNamesTest__", "DECK", "TOTALLY_DIFFERENT", "NOTE", ("5",), "99")
        ]
        view._sources = ["manual"]
        view._devices = [""]
        view._on_apply_clicked()

        assert shown.get("title") == "Cannot apply"
        hits = catalog.lookup("1", "Note On", "0")
        assert any(h.name == "PLAY" for h in hits), "original draft's definition must survive"
    finally:
        catalog._registry._REGISTRY.pop("__StaleAppliedNamesTest__", None)


def test_load_session_forgets_names_this_draft_previously_applied(monkeypatch, tmp_path):
    """Same hazard as above, reached via "Load session…" instead of "New
    session": the loaded draft has never itself applied anything in this
    process, even if its name collides with one this widget applied earlier."""
    import djmidi.gui.controller_setup as controller_setup_mod

    monkeypatch.setattr(controller_setup_mod.QMessageBox, "information", lambda *a: None)
    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "critical",
        lambda parent, title, text: shown.update(title=title, text=text),
    )

    view = _view_with_name("__StaleAppliedNamesTest2__")
    view._rows = [ControlInfo("__StaleAppliedNamesTest2__", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    try:
        view._apply()
        assert "__StaleAppliedNamesTest2__" in view._applied_names

        other_session = tmp_path / "other.json"
        other_session.write_text(
            json.dumps(
                {
                    "version": 1,
                    "controller_name": "__StaleAppliedNamesTest2__",
                    "rows": [
                        {
                            "section": "DECK",
                            "name": "TOTALLY_DIFFERENT",
                            "note_or_cc": "NOTE",
                            "channels": ["5"],
                            "data1": "99",
                            "source": "manual",
                            "device": "",
                        }
                    ],
                }
            )
        )
        view._load_session(other_session)
        assert view._applied_names == set()

        view._on_apply_clicked()
        assert shown.get("title") == "Cannot apply"
        hits = catalog.lookup("1", "Note On", "0")
        assert any(h.name == "PLAY" for h in hits), "original draft's definition must survive"
    finally:
        catalog._registry._REGISTRY.pop("__StaleAppliedNamesTest2__", None)


def test_on_apply_clicked_blocks_on_validation_errors(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("__ApplySetupTest3__")
    view._maybe_add_row("1", "NOTE", "0", "manual")  # missing name/section

    shown = {}
    monkeypatch.setattr(controller_setup_mod.QMessageBox, "warning", lambda *a: shown.setdefault("warned", True))
    view._on_apply_clicked()
    assert shown.get("warned") is True
    assert "__ApplySetupTest3__" not in catalog.CONTROLLER_NAMES


def test_on_apply_clicked_surfaces_unexpected_exception_instead_of_failing_silently(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

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
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A", "Port B"])
    view._refresh_output_ports()
    assert view._output_port_list.count() == 2
    assert view._output_port_list.item(0).text() == "Port A"


def test_refresh_output_ports_auto_checks_first_port_when_none_checked(monkeypatch):
    """Preserves the old single-output convenience default now that the list
    is checkbox-based (multi-select) rather than single-selection."""
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A", "Port B"])
    view._refresh_output_ports()
    assert view._selected_output_ports() == ["Port A"]


def test_refresh_output_ports_preserves_multiple_checked_ports_by_name(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A", "Port B", "Port C"])
    view._refresh_output_ports()
    view._output_port_list.item(1).setCheckState(Qt.CheckState.Checked)  # Port B, in addition to auto-checked A
    view._refresh_output_ports()
    assert set(view._selected_output_ports()) == {"Port A", "Port B"}


def test_refresh_output_ports_restores_default_after_selection_emptied(monkeypatch):
    """"Refresh output ports" always leaves at least one port checked when
    ports are available -- restoring a sane default rather than leaving
    every send/replay action unusable, even if the user had emptied the
    selection since the last refresh."""
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    view._refresh_output_ports()
    view._output_port_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    view._refresh_output_ports()
    assert view._output_port_list.item(0).checkState() == Qt.CheckState.Checked


def test_selected_output_ports_raises_when_none_checked(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    view._refresh_output_ports()
    view._output_port_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    with pytest.raises(ValueError, match="No output port selected"):
        view._selected_output_ports()


def test_send_output_once_sends_to_every_checked_port(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A", "Port B", "Port C"])
    monkeypatch.setattr(
        controller_setup_mod,
        "send_midi_message",
        lambda **kwargs: sent.append(kwargs),
    )
    view._refresh_output_ports()
    view._output_port_list.item(2).setCheckState(Qt.CheckState.Checked)  # Port A (auto) + Port C
    view._send_type_edit.setText("note_on")
    view._send_channel_edit.setText("1")
    view._send_data1_edit.setText("27")
    view._send_data2_edit.setText("127")
    view._on_send_output_once_clicked()
    assert {kwargs["output_port_name"] for kwargs in sent} == {"Port A", "Port C"}
    assert "2 outputs" in view._send_status.text()


def test_send_output_once_uses_selected_output_port_and_values(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

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
    import djmidi.gui.controller_setup as controller_setup_mod

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


def test_send_output_double_click_reports_invalid_data1_instead_of_raising(monkeypatch):
    """Every sibling send/apply/export handler in this file wraps its work in
    try/except so a bad user input surfaces as a QMessageBox instead of an
    uncaught exception escaping the Qt slot; double-click must behave the same
    way for an invalid Data1 field."""
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name()
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A"])
    view._refresh_output_ports()
    view._send_data1_edit.setText("not-a-number")

    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "critical",
        lambda parent, title, text: shown.update(title=title, text=text),
    )
    view._on_send_output_double_clicked()  # must not raise
    assert shown.get("title") == "Failed to send MIDI"


def test_ddj_xp2_pad_mode_5_uses_double_click_on_mode_1(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

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
    import djmidi.gui.controller_setup as controller_setup_mod

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


def test_play_session_rows_once_sends_to_every_checked_port(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    sent = []
    view = _view_with_name()
    view._rows = [ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10")]
    view._sources = ["manual"]
    view._devices = [""]
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Port A", "Port B"])
    monkeypatch.setattr(controller_setup_mod, "send_midi_message", lambda **kwargs: sent.append(kwargs))
    view._refresh_output_ports()
    view._output_port_list.item(1).setCheckState(Qt.CheckState.Checked)
    sent_count, skipped = view._play_session_rows_once([0])
    assert sent_count == 4  # note_on + note_off, once per port
    assert skipped == 0
    assert {kwargs["output_port_name"] for kwargs in sent} == {"Port A", "Port B"}


def test_play_session_rows_once_skips_invalid_rows(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

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
    import djmidi.gui.controller_setup as controller_setup_mod

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


def _three_pad_rows(view: ControllerSetupView) -> None:
    view._rows = [
        ControlInfo("MiniPad", "", "", "NOTE", ("1",), "10"),
        ControlInfo("MiniPad", "", "", "NOTE", ("1",), "11"),
        ControlInfo("MiniPad", "", "", "NOTE", ("1",), "12"),
    ]
    view._sources = ["learned", "learned", "learned"]
    view._devices = ["", "", ""]
    view._rebuild_table()


def _select_table_rows(view: ControllerSetupView, rows: list[int]) -> None:
    """QTableWidget.selectRow() replaces the selection each call under
    ExtendedSelection, so accumulate through the selection model instead."""
    from PySide6.QtCore import QItemSelectionModel

    model = view._table.selectionModel()
    model.clearSelection()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for row in rows:
        model.select(view._table.model().index(row, 0), flags)


def test_bulk_set_section_applies_only_to_selected_rows(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    _three_pad_rows(view)
    _select_table_rows(view, [0, 2])

    monkeypatch.setattr(controller_setup_mod.QInputDialog, "getText", lambda *a, **k: ("PADS", True))
    view._on_bulk_set_section_clicked()

    assert [row.section for row in view._rows] == ["PADS", "", "PADS"]
    assert view._table.item(0, 0).text() == "PADS"
    assert view._dirty is True


def test_bulk_set_section_noop_without_selection(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    _three_pad_rows(view)
    view._table.clearSelection()
    view._dirty = False

    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "information",
        lambda parent, title, text: shown.update(title=title),
    )
    monkeypatch.setattr(
        controller_setup_mod.QInputDialog,
        "getText",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("prompt must not open without a selection")),
    )
    view._on_bulk_set_section_clicked()
    assert shown.get("title") == "No rows selected"
    assert view._dirty is False


def test_bulk_set_section_cancelled_prompt_changes_nothing(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    _three_pad_rows(view)
    _select_table_rows(view, [0])
    view._dirty = False

    monkeypatch.setattr(controller_setup_mod.QInputDialog, "getText", lambda *a, **k: ("PADS", False))
    view._on_bulk_set_section_clicked()
    assert [row.section for row in view._rows] == ["", "", ""]
    assert view._dirty is False


def test_bulk_set_name_without_auto_number(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    _three_pad_rows(view)
    _select_table_rows(view, [0, 1, 2])

    monkeypatch.setattr(controller_setup_mod.QInputDialog, "getText", lambda *a, **k: ("HOTCUE", True))
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "question",
        lambda *a, **k: controller_setup_mod.QMessageBox.StandardButton.No,
    )
    view._on_bulk_set_name_clicked()
    assert [row.name for row in view._rows] == ["HOTCUE", "HOTCUE", "HOTCUE"]


def test_bulk_set_name_with_auto_number(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    _three_pad_rows(view)
    _select_table_rows(view, [0, 1, 2])

    monkeypatch.setattr(controller_setup_mod.QInputDialog, "getText", lambda *a, **k: ("PAD", True))
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "question",
        lambda *a, **k: controller_setup_mod.QMessageBox.StandardButton.Yes,
    )
    view._on_bulk_set_name_clicked()
    assert [row.name for row in view._rows] == ["PAD 1", "PAD 2", "PAD 3"]


def test_bulk_edit_warns_when_it_creates_a_conflict(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    # Same trigger (1, NOTE, 10) on two rows: harmless while their (section,
    # name) agree (empty), but assigning different names to only one collides.
    view._rows = [
        ControlInfo("MiniPad", "PADS", "KEEP", "NOTE", ("1",), "10"),
        ControlInfo("MiniPad", "", "", "NOTE", ("1",), "10"),
    ]
    view._sources = ["manual", "manual"]
    view._devices = ["", ""]
    view._rebuild_table()
    _select_table_rows(view, [1])

    monkeypatch.setattr(controller_setup_mod.QInputDialog, "getText", lambda *a, **k: ("OTHER", True))
    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox,
        "warning",
        lambda parent, title, text: shown.update(title=title),
    )
    view._on_bulk_set_name_clicked()
    assert shown.get("title") == "Bulk edit created conflicts"


def test_set_reference_image_updates_label_and_marks_dirty():
    view = _view_with_name("MiniPad")
    view._dirty = False
    view.set_reference_image("/tmp/minipad-front.png")
    assert view._reference_image == "/tmp/minipad-front.png"
    assert "minipad-front.png" in view._image_label.text()
    assert view._dirty is True

    view.set_reference_image("")
    assert view._reference_image == ""
    assert view._image_label.text() == "No reference image"


def test_reference_image_round_trips_through_session(tmp_path):
    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    view.set_reference_image("/tmp/minipad.png")

    session_path = tmp_path / "session.json"
    view._save_session(session_path)
    assert json.loads(session_path.read_text())["reference_image"] == "/tmp/minipad.png"

    reloaded = ControllerSetupView()
    reloaded._load_session(session_path)
    assert reloaded._reference_image == "/tmp/minipad.png"
    assert "minipad.png" in reloaded._image_label.text()


def test_new_session_clears_reference_image():
    view = _view_with_name("MiniPad")
    view.set_reference_image("/tmp/x.png")
    view._reset(clear_name=True)
    assert view._reference_image == ""
    assert view._image_label.text() == "No reference image"


def test_apply_registers_definition_with_reference_image():
    view = _view_with_name("__ApplyImageTest__")
    view._rows = [ControlInfo("__ApplyImageTest__", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    view.set_reference_image("/tmp/apply-image-test.png")
    try:
        view._apply()
        assert catalog.get_definition("__ApplyImageTest__").reference_image == "/tmp/apply-image-test.png"
    finally:
        catalog._registry._REGISTRY.pop("__ApplyImageTest__", None)


def test_export_module_emits_reference_image_basename(tmp_path):
    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0")]
    view._sources = ["manual"]
    view._devices = [""]
    view.set_reference_image(str(tmp_path / "some" / "dir" / "minipad.png"))

    out_path = tmp_path / "minipad.py"
    view._export_module(out_path)
    text = out_path.read_text()
    assert "reference_image='minipad.png'," in text


def _accept_submission_dialog(monkeypatch, metadata=None):
    from PySide6.QtWidgets import QDialog

    import djmidi.gui.controller_setup as controller_setup_mod
    from djmidi.catalog.community import SubmissionMetadata

    class _FakeDialog:
        def __init__(self, *_a, **_k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def metadata(self):
            return metadata or SubmissionMetadata(contributor="dj_test", source="learned")

    monkeypatch.setattr(controller_setup_mod, "ControllerSubmissionDialog", _FakeDialog)


def test_submit_blocked_on_validation_errors(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    view._maybe_add_row("1", "NOTE", "0", "manual")  # missing section/name

    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox, "warning", lambda parent, title, text: shown.update(title=title)
    )
    opened = []
    monkeypatch.setattr(controller_setup_mod.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    view._on_submit_clicked()
    assert shown.get("title") == "Cannot submit yet"
    assert opened == []


def test_submit_copies_json_to_clipboard_and_opens_github(monkeypatch):
    from PySide6.QtWidgets import QApplication

    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "PADS", "PAD 1", "NOTE", ("1",), "36")]
    view._sources = ["learned"]
    view._devices = [""]

    _accept_submission_dialog(monkeypatch)
    opened = []
    monkeypatch.setattr(
        controller_setup_mod.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True
    )
    info = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox, "information", lambda parent, title, text: info.update(title=title)
    )

    view._on_submit_clicked()

    assert len(opened) == 1
    assert opened[0].startswith("https://github.com/")
    assert "issues/new" in opened[0]
    assert info.get("title") == "Submission opened"
    clip = QApplication.clipboard().text()
    assert '"controller_name": "MiniPad"' in clip
    assert '"schema": "controller-submission/1"' in clip


def test_submit_dialog_cancelled_does_nothing(monkeypatch):
    from PySide6.QtWidgets import QDialog

    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "PADS", "PAD 1", "NOTE", ("1",), "36")]
    view._sources = ["learned"]
    view._devices = [""]

    class _RejectDialog:
        def __init__(self, *_a, **_k):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

        def metadata(self):
            raise AssertionError("metadata() must not be read when the dialog is cancelled")

    monkeypatch.setattr(controller_setup_mod, "ControllerSubmissionDialog", _RejectDialog)
    opened = []
    monkeypatch.setattr(controller_setup_mod.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    view._on_submit_clicked()
    assert opened == []


def test_submit_warns_when_browser_cannot_open(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod

    view = _view_with_name("MiniPad")
    view._rows = [ControlInfo("MiniPad", "PADS", "PAD 1", "NOTE", ("1",), "36")]
    view._sources = ["learned"]
    view._devices = [""]

    _accept_submission_dialog(monkeypatch)
    monkeypatch.setattr(controller_setup_mod.QDesktopServices, "openUrl", lambda url: False)
    shown = {}
    monkeypatch.setattr(
        controller_setup_mod.QMessageBox, "warning", lambda parent, title, text: shown.update(title=title)
    )
    view._on_submit_clicked()
    assert shown.get("title") == "Couldn't open the browser"


def test_session_rows_returns_copy_of_current_rows():
    view = _view_with_name()
    view._rows = [ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10")]
    rows = view.session_rows()
    assert rows == view._rows
    assert rows is not view._rows


def test_selected_session_rows_defaults_to_all_when_nothing_selected():
    view = _view_with_name()
    view._rows = [
        ControlInfo("MiniPad", "PAD", "A", "NOTE", ("1",), "10"),
        ControlInfo("MiniPad", "PAD", "B", "NOTE", ("1",), "11"),
    ]
    view._sources = ["manual", "manual"]
    view._devices = ["", ""]
    view._rebuild_table()
    view._table.clearSelection()
    assert view.selected_session_rows() == view._rows


def test_poll_records_every_midi_event_for_exact_session_replay(monkeypatch):
    from djmidi.midi_io import MidiEvent

    view = _view_with_name()
    events = [
        MidiEvent("in", "1", "Note On", "10", "100", 5.0, "Controller A"),
        MidiEvent("in", "1", "Note Off", "10", "0", 5.25, "Controller A"),
    ]
    monkeypatch.setattr(view._monitor, "poll", lambda: events)

    view._poll()

    assert view.recorded_session_events() == events
    assert len(view._rows) == 1


def test_replay_recorded_session_uses_selected_output_and_recorded_timing(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod
    from djmidi.midi_io import MidiEvent

    view = _view_with_name()
    view._recorded_events = [
        MidiEvent("in", "1", "Note On", "10", "100", 5.0, "Controller A"),
        MidiEvent("in", "1", "Note Off", "10", "0", 5.25, "Controller A"),
    ]
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Setup MIDI Out"])
    view._refresh_output_ports()
    scheduled = []
    replayed = []
    monkeypatch.setattr(controller_setup_mod.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    monkeypatch.setattr(
        controller_setup_mod,
        "replay_midi_events",
        lambda port, events, sender=None: replayed.append((port, events[0])),
    )

    view._on_replay_recorded_session_clicked()
    assert scheduled[0][0] == 0
    scheduled.pop(0)[1]()
    assert scheduled[0][0] == 250
    scheduled.pop(0)[1]()

    assert [port for port, _event in replayed] == ["Setup MIDI Out", "Setup MIDI Out"]
    assert [event.event_type for _port, event in replayed] == ["Note On", "Note Off"]
    assert "Recorded session replayed" in view._send_status.text()


def test_replay_recorded_session_sends_each_event_to_every_checked_port(monkeypatch):
    import djmidi.gui.controller_setup as controller_setup_mod
    from djmidi.midi_io import MidiEvent

    view = _view_with_name()
    view._recorded_events = [MidiEvent("in", "1", "Note On", "10", "100", 5.0, "Controller A")]
    monkeypatch.setattr(controller_setup_mod, "list_output_ports", lambda: ["Out A", "Out B"])
    view._refresh_output_ports()
    view._output_port_list.item(1).setCheckState(Qt.CheckState.Checked)
    scheduled = []
    replayed = []
    monkeypatch.setattr(controller_setup_mod.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    monkeypatch.setattr(
        controller_setup_mod,
        "replay_midi_events",
        lambda port, events, sender=None: replayed.append(port),
    )

    view._on_replay_recorded_session_clicked()
    scheduled.pop(0)[1]()

    assert set(replayed) == {"Out A", "Out B"}


def test_session_save_and_load_preserves_recorded_events(tmp_path):
    from djmidi.midi_io import MidiEvent

    view = _view_with_name("MiniPad")
    view._recorded_events = [MidiEvent("in", "4", "Control Change", "12", "77", 9.5, "Controller A")]
    session_path = tmp_path / "recorded-session.json"

    view._save_session(session_path)
    reloaded = ControllerSetupView()
    reloaded._load_session(session_path)

    assert reloaded.recorded_session_events() == view._recorded_events



def test_icon_button_grid_places_buttons_in_two_columns():
    from PySide6.QtWidgets import QPushButton

    buttons = [QPushButton() for _ in range(5)]
    grid = ControllerSetupView._icon_button_grid(buttons)
    assert grid.count() == 5
    positions = {(grid.getItemPosition(i)[0], grid.getItemPosition(i)[1]) for i in range(5)}
    assert positions == {(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)}
    for b in buttons:
        assert b.size().width() == 28 and b.size().height() == 28


def test_toolbar_row_labels_groups_and_spreads_them():
    from PySide6.QtWidgets import QLabel, QPushButton

    groups = [
        ("Session", [QPushButton(), QPushButton()]),
        ("Import", [QPushButton()]),
        ("Apply / Export", [QPushButton(), QPushButton()]),
    ]
    row = ControllerSetupView._toolbar_row(groups)
    items = [row.itemAt(i) for i in range(row.count())]
    labels = [it.widget().text() for it in items if isinstance(it.widget(), QLabel)]
    buttons = [it.widget() for it in items if isinstance(it.widget(), QPushButton)]
    stretches = [it for it in items if it.spacerItem() is not None and it.spacerItem().expandingDirections()]

    assert labels == ["Session", "Import", "Apply / Export"]  # caption before each group
    assert len(buttons) == 5
    assert len(stretches) == 2  # between the 3 groups -> spread across the width
    for b in buttons:
        assert b.size().width() == 28 and b.size().height() == 28


def test_setup_has_one_draft_panel_and_renamed_midi_input():
    from PySide6.QtWidgets import QLabel

    view = _view_with_name()
    titles = {lbl.text() for lbl in view.findChildren(QLabel)}
    assert "Draft" in titles           # the merged panel
    assert "MIDI input" in titles      # renamed from "Capture (learn from controller)"
    assert "Session" in titles         # now a toolbar group caption, not a panel
    assert "Capture (learn from controller)" not in titles


def test_midi_input_and_output_row_is_wrapped_in_a_scroll_area():
    """Issue #19: at the app's minimum/small window size, the "MIDI input" +
    "MIDI Output" row's three columns (Send message / Playback / Pad modes)
    need more width than is guaranteed, and used to overlap instead of
    shrinking. A QScrollArea around that row enforces its real minimum size
    and shows a scrollbar instead."""
    from PySide6.QtWidgets import QGroupBox, QLabel, QScrollArea

    view = _view_with_name()
    scroll_areas = view.findChildren(QScrollArea)
    assert len(scroll_areas) == 1
    scroll_area = scroll_areas[0]
    assert scroll_area.widgetResizable() is True
    labels = {lbl.text() for lbl in scroll_area.findChildren(QLabel)}
    assert "MIDI input" in labels
    group_titles = {box.title() for box in scroll_area.findChildren(QGroupBox)}
    assert "MIDI Output" in group_titles
