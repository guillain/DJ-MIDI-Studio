"""Guided hardware session (issue #426)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from djmidi import catalog, hardware_session
from djmidi.hardware_session import (
    CHECKS,
    CHECKS_BY_ID,
    FAIL,
    PASS,
    SKIP,
    TODO,
    CapturedMessage,
    CheckResult,
    HardwareSession,
    captured_from_event,
    load_session,
    report_text,
    save_session,
    verdict,
)
from djmidi.midi_io import MidiEvent


def _event(event_type="Note On", channel="1", data1="16", data2="127", direction="in", port="DDJ-XP2"):
    return MidiEvent(direction, channel, event_type, data1, data2, 0.0, port)


def _note(number, velocity=127):
    return CapturedMessage("DDJ-XP2", "Note On", 1, number, velocity)


def test_check_ids_are_unique_and_controllers_are_registered():
    assert len(CHECKS_BY_ID) == len(CHECKS)
    for check in CHECKS:
        assert check.issue.startswith("#")
        if check.controller:
            assert check.controller in catalog.CONTROLLER_NAMES
        if check.compare:
            assert check.capture


def test_the_ddj_xp2_comparison_agrees_with_the_catalog():
    check = CHECKS_BY_ID["ddj-xp2-loop-notes"]
    from djmidi.catalog import ddj_xp2

    names = {"1/2X": None, "2X": None}

    for entry in ddj_xp2._STATIC:
        if entry.name in names:
            names[entry.name] = int(entry.data1)
    profile = next(numbers for source, numbers in check.compare.items() if "profile" in source)
    assert profile == (names["1/2X"], names["2X"])


def test_captured_from_event_keeps_only_input_direction():
    assert captured_from_event(_event()) == CapturedMessage("DDJ-XP2", "Note On", 1, 16, 127)
    assert captured_from_event(_event(direction="out")) is None
    assert captured_from_event(_event(data1="x")) is None


def test_verdict_names_the_source_the_capture_agrees_with():
    check = CHECKS_BY_ID["ddj-xp2-loop-notes"]
    assert verdict(check, CheckResult()) == "Nothing captured yet."
    result = CheckResult(captured=[_note(16), _note(16, 0), _note(17), _note(17, 0)])
    assert verdict(check, result) == "Captured notes 16, 17: they match official PDF and this app's profile."
    result = CheckResult(captured=[_note(18), _note(19)])
    assert "rekordbox" in verdict(check, result)
    assert "no known source" in verdict(check, CheckResult(captured=[_note(20)]))
    cc_only = CheckResult(captured=[CapturedMessage("p", "Control Change", 1, 33, 65)])
    assert verdict(check, cc_only) == "No press captured: 1 other message(s)."


def test_verdict_summarizes_a_capture_without_comparison_and_is_empty_without_capture():
    jog = CHECKS_BY_ID["cmd-micro-jog"]
    result = CheckResult(
        captured=[
            CapturedMessage("CMD Micro", "Control Change", 5, 33, 65),
            CapturedMessage("CMD Micro", "Control Change", 5, 33, 63),
        ]
    )
    assert verdict(jog, result) == "2 message(s) captured: Control Change ch 5 #33 ×2."
    assert verdict(CHECKS_BY_ID["serato-learn"], result) == ""


def test_session_round_trips_and_ignores_unknown_checks(tmp_path):
    session = HardwareSession()
    session.set_status("cmd-micro-jog", PASS)
    session.set_note("cmd-micro-jog", "CC 33, 65 = clockwise")
    session.capture("cmd-micro-jog", _note(3))
    session.results["gone"] = CheckResult(status=FAIL)
    path = tmp_path / "sub" / "hardware-session.json"
    save_session(session, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == hardware_session.FORMAT
    assert "gone" not in data["results"]
    loaded = load_session(path)
    assert loaded.results["cmd-micro-jog"] == session.results["cmd-micro-jog"]
    assert loaded.counts()[PASS] == 1
    assert loaded.counts()[TODO] == len(CHECKS) - 1


def test_load_session_starts_fresh_on_a_missing_or_unreadable_file(tmp_path):
    assert load_session(tmp_path / "none.json").results == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_session(bad).results == {}
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"format": "else"}), encoding="utf-8")
    assert load_session(other).results == {}


def test_capture_is_bounded_and_status_validated():
    session = HardwareSession()
    for _ in range(hardware_session.MAX_CAPTURED):
        assert session.capture("cmd-micro-jog", _note(1))
    assert not session.capture("cmd-micro-jog", _note(1))
    with pytest.raises(ValueError):
        session.set_status("cmd-micro-jog", "maybe")


def test_report_lists_every_check_with_its_result():
    session = HardwareSession()
    session.set_status("ddj-xp2-loop-notes", PASS)
    session.capture("ddj-xp2-loop-notes", _note(16))
    session.capture("ddj-xp2-loop-notes", _note(17))
    session.set_status("traktor-import", SKIP)
    session.set_note("traktor-import", "no Traktor\nhere")
    text = report_text(session, "0.48.198", datetime(2026, 11, 10, 9, 0, tzinfo=UTC))
    assert "App version: 0.48.198" in text
    assert "1 pass" in text and "1 skipped" in text
    for check in CHECKS:
        assert check.title in text
    assert "Note: no Traktor here" in text
    assert "DDJ-XP2 · Note On ch 1 · 16 = 127" in text
    assert "they match official PDF" in text


# --- the dialog ---------------------------------------------------------------


@pytest.fixture
def dialog(tmp_path):
    from djmidi.gui.hardware_session_dialog import HardwareSessionDialog

    listening = []
    widget = HardwareSessionDialog(tmp_path / "session.json", ensure_listening=lambda: listening.append(1) or True)
    widget.listening = listening
    return widget


def test_dialog_captures_only_while_capturing_and_saves(dialog, tmp_path):
    dialog.select_check("ddj-xp2-loop-notes")
    assert not dialog.feed_event(_event())
    assert dialog.toggle_capture()
    assert dialog.listening
    assert dialog.feed_event(_event(data1="16"))
    assert dialog.feed_event(_event(data1="17"))
    assert not dialog.feed_event(_event(direction="out"))
    assert dialog.captured.count() == 2
    assert "official PDF" in dialog.verdict.text()
    dialog.mark(PASS)
    assert not dialog.capturing
    assert dialog.check_list.item(0).text().startswith("✓")
    saved = load_session(tmp_path / "session.json")
    assert saved.results["ddj-xp2-loop-notes"].status == PASS
    assert len(saved.results["ddj-xp2-loop-notes"].captured) == 2


def test_dialog_keeps_notes_per_check_and_hides_capture_for_manual_checks(dialog, tmp_path):
    dialog.select_check("serato-learn")
    assert dialog.capture_button.isHidden()
    assert not dialog.toggle_capture()
    dialog.note.setPlainText("exported, attached")
    dialog.select_check("cmd-micro-jog")
    assert not dialog.capture_button.isHidden()
    assert dialog.note.toPlainText() == ""
    dialog.select_check("serato-learn")
    assert dialog.note.toPlainText() == "exported, attached"
    assert load_session(tmp_path / "session.json").results["serato-learn"].note == "exported, attached"


def test_dialog_refuses_capture_without_input(tmp_path):
    from djmidi.gui.hardware_session_dialog import HardwareSessionDialog

    widget = HardwareSessionDialog(tmp_path / "s.json", ensure_listening=lambda: False)
    widget.select_check("cmd-micro-jog")
    assert not widget.toggle_capture()
    assert "No MIDI input" in widget.status.text()


def test_dialog_saves_the_report(dialog, tmp_path):
    dialog.select_check("traktor-exports")
    dialog.mark(FAIL)
    path = tmp_path / "report.md"
    dialog.save_report(str(path))
    assert "Result: **fail**" in path.read_text(encoding="utf-8")


def test_main_window_routes_live_events_to_a_capture(monkeypatch):
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    monkeypatch.setattr(window, "_ensure_learn_listening", lambda: True)
    played = []
    monkeypatch.setattr(window, "_play_triggered_macros", lambda event: played.append(event))
    dialog = window.open_hardware_session()
    assert window.open_hardware_session() is dialog
    dialog.select_check("cmd-micro-jog")
    dialog.session.clear_capture("cmd-micro-jog")
    dialog.toggle_capture()
    window._on_live_midi_event(_event("Control Change", "5", "33", "65", port="CMD Micro"))
    assert dialog.captured.count() == 1
    assert played == []
    dialog.close()
    assert window._hardware_session_dialog is None
