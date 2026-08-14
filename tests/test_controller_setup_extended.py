"""Extra coverage for ControllerSetupView's session/table/learn workflows."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from seratomidiconf.catalog._registry import ControlInfo
from seratomidiconf.gui.controller_setup import ControllerSetupView
from seratomidiconf.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def _view(name: str = "TestCtrl") -> ControllerSetupView:
    view = ControllerSetupView()
    view._name_edit.setText(name)
    return view


# ─── table / row manipulation ─────────────────────────────────────────────────

def test_add_row_button_creates_empty_row():
    view = _view()
    initial = len(view._rows)
    view._on_add_row_clicked()
    assert len(view._rows) == initial + 1
    assert view._table.rowCount() == initial + 1


def test_delete_selected_removes_row():
    view = _view()
    view._maybe_add_row("1", "NOTE", "60", "manual")
    view._table.selectAll()
    view._on_delete_selected_clicked()
    assert view._rows == []


def test_delete_selected_no_selection_does_nothing():
    view = _view()
    view._maybe_add_row("1", "NOTE", "60", "manual")
    # Deselect everything explicitly
    view._table.clearSelection()
    before = len(view._rows)
    view._on_delete_selected_clicked()
    assert len(view._rows) == before


def test_on_cell_changed_updates_row():
    view = _view()
    view._maybe_add_row("1", "NOTE", "60", "manual")
    from PySide6.QtWidgets import QTableWidgetItem
    view._table.blockSignals(True)
    view._table.setItem(0, 0, QTableWidgetItem("DECK"))
    view._table.setItem(0, 1, QTableWidgetItem("Play"))
    view._table.blockSignals(False)
    view._on_cell_changed(0, 0)
    assert view._rows[0].section == "DECK"


def test_on_cell_changed_skips_when_rebuilding():
    view = _view()
    view._maybe_add_row("1", "NOTE", "60", "manual")
    view._rebuilding = True
    # should not raise
    view._on_cell_changed(0, 0)
    view._rebuilding = False


def test_on_cell_changed_skips_source_column():
    view = _view()
    view._maybe_add_row("1", "NOTE", "60", "manual")
    # column 5 = source (read-only)
    view._on_cell_changed(0, 5)


def test_on_cell_changed_skips_out_of_range_row():
    view = _view()
    view._on_cell_changed(99, 0)


# ─── import config ────────────────────────────────────────────────────────────

def test_import_config_adds_unique_triggers():
    view = _view()
    config = parse_file(FIXTURE)
    added = view._import_config(config)
    assert added > 0


def test_import_config_idempotent():
    view = _view()
    config = parse_file(FIXTURE)
    first = view._import_config(config)
    second = view._import_config(config)
    assert second == 0
    assert first > 0


# ─── session save/load ────────────────────────────────────────────────────────

def test_save_and_load_session_round_trips(tmp_path):
    view = _view("RoundTripCtrl")
    view._maybe_add_row("1", "NOTE", "60", "manual")
    path = tmp_path / "session.json"
    view._save_session(path)
    assert not view._dirty

    view2 = ControllerSetupView()
    view2._load_session(path)
    assert view2._controller_name == "RoundTripCtrl"
    assert len(view2._rows) == 1
    assert view2._rows[0].data1 == "60"


def test_rows_to_session_dict_structure():
    view = _view("TestCtrl")
    view._maybe_add_row("1", "NOTE", "42", "manual")
    d = view._rows_to_session_dict()
    assert d["version"] == 1
    assert d["controller_name"] == "TestCtrl"
    assert len(d["rows"]) == 1
    assert d["rows"][0]["data1"] == "42"


def test_load_session_unsupported_version_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"version": 99, "controller_name": "x", "rows": []}))
    view = _view()
    import pytest
    with pytest.raises(ValueError, match="Unsupported session version"):
        view._load_session(path)


# ─── learn / port refresh ────────────────────────────────────────────────────

def test_start_and_stop_learning_toggles_flag():
    view = _view()
    with patch.object(view._monitor, "open_input"):
        view._start_learning()
    assert view._learning is True
    with patch.object(view._monitor, "close_all"):
        view._stop_learning()
    assert view._learning is False


def test_toggle_learning_start_then_stop():
    view = _view()
    with patch.object(view._monitor, "open_input"):
        view._toggle_learning()
    assert view._learning is True
    with patch.object(view._monitor, "close_all"):
        view._toggle_learning()
    assert view._learning is False


def test_refresh_ports_populates_list():
    view = _view()
    with patch("seratomidiconf.gui.controller_setup.list_input_ports", return_value=["Port X"]):
        view._refresh_ports()
    assert view._port_list.count() == 1


# ─── poll / maybe_add_row ─────────────────────────────────────────────────────

def test_poll_adds_learned_note_event():
    view = _view()
    from seratomidiconf.midi_io import MidiEvent
    event = MidiEvent(direction="in", channel="1", event_type="Note On", data1="60", data2="100", timestamp=0.0)
    with patch.object(view._monitor, "poll", return_value=[event]):
        view._poll()
    assert len(view._rows) == 1


def test_poll_skips_unknown_event_type():
    view = _view()
    from seratomidiconf.midi_io import MidiEvent
    event = MidiEvent(direction="in", channel="1", event_type="SysEx", data1="0", data2="0", timestamp=0.0)
    with patch.object(view._monitor, "poll", return_value=[event]):
        view._poll()
    assert len(view._rows) == 0


# ─── on_name_changed ──────────────────────────────────────────────────────────

def test_on_name_changed_updates_controller_name_in_rows():
    view = _view("OldName")
    view._maybe_add_row("1", "NOTE", "60", "manual")
    view._name_edit.setText("NewName")
    assert view._controller_name == "NewName"
    assert all(r.controller == "NewName" for r in view._rows)


# ─── check conflicts ──────────────────────────────────────────────────────────

def test_on_check_conflicts_no_conflict(monkeypatch):
    import seratomidiconf.gui.controller_setup as mod
    view = _view()
    view._maybe_add_row("1", "NOTE", "60", "manual")
    view._rows[0] = ControlInfo("TestCtrl", "DECK", "Play", "NOTE", ("1",), "60")
    view._sources = ["manual"]
    view._devices = [""]

    shown = {}
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a: shown.update(ok=True))
    view._on_check_conflicts_clicked()
    assert shown.get("ok")


def test_on_check_conflicts_with_conflict(monkeypatch):
    import seratomidiconf.gui.controller_setup as mod
    view = _view()
    # Two rows with same trigger but different names
    view._rows = [
        ControlInfo("TestCtrl", "DECK", "Play", "NOTE", ("1",), "60"),
        ControlInfo("TestCtrl", "DECK", "Stop", "NOTE", ("1",), "60"),
    ]
    view._sources = ["manual", "manual"]
    view._devices = ["", ""]

    shown = {}
    monkeypatch.setattr(mod.QMessageBox, "warning", lambda *a: shown.update(warned=True))
    view._on_check_conflicts_clicked()
    assert shown.get("warned")


# ─── shutdown ─────────────────────────────────────────────────────────────────

def test_shutdown_when_learning_calls_stop():
    view = _view()
    view._learning = True
    with patch.object(view, "_stop_learning") as mock_stop:
        view.shutdown()
    mock_stop.assert_called_once()


def test_shutdown_when_not_learning_is_noop():
    view = _view()
    view.shutdown()  # must not raise


