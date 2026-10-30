"""Guided controller profile verification (issue #364)."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from djmidi.catalog._registry import ControlInfo, ControllerDefinition, register
from djmidi.gui.profile_check import (
    MISMATCH,
    OK,
    PLAIN,
    SHIFT,
    SKIPPED,
    ProfileCheck,
    check_items,
    press_from_event,
    report_issue_url,
    report_text,
)
from djmidi.midi_io import MidiEvent

NAME = "Check Profile"


def _register():
    entries = [
        ControlInfo(NAME, "Deck", "Sync", "NOTE", ("1", "2"), "88"),
        ControlInfo(NAME, "Deck", "Sync +SHIFT", "NOTE", ("1", "2"), "92"),
        ControlInfo(NAME, "Deck", "Cue", "NOTE", ("1", "2"), "12"),
        ControlInfo(NAME, "PAD", "Pad 1 (HotCue)", "NOTE", ("8",), "0"),
        ControlInfo(NAME, "PAD", "Pad 1 (Sampler)", "NOTE", ("8",), "48"),
    ]
    register(ControllerDefinition(name=NAME, static_entries=entries, section_order=("Deck", "PAD")), replace=True)


def _event(data1, data2="127", event_type="Note On", channel="1", port="TEST", direction="in"):
    return MidiEvent(direction, channel, event_type, str(data1), data2, 0.0, port)


def test_items_follow_the_layout_one_per_control_and_layer():
    _register()
    items = check_items(NAME)
    assert [(item.label, item.layer) for item in items] == [
        ("Sync", PLAIN),
        ("Sync", SHIFT),
        ("Cue", PLAIN),
        ("Pad 1", PLAIN),
    ]
    assert items[0].triggers == {("1", "NOTE", "88"), ("2", "NOTE", "88")}
    assert items[3].triggers == {("8", "NOTE", "0"), ("8", "NOTE", "48")}  # any pad mode
    assert items[1].title == "SHIFT + Sync" and items[1].prompt() == "Hold SHIFT and press Sync"


def test_presses_are_judged_and_back_redoes_one():
    _register()
    check = ProfileCheck.start(NAME)
    assert check.press(("2", "NOTE", "88")).status == OK  # deck 2 counts
    wrong = check.press(("1", "NOTE", "12"))  # SHIFT + Sync expected, got Cue's note
    assert wrong.status == MISMATCH and wrong.detail() == "got Note 12 on channel 1, which the profile gives to Cue"
    check.back()
    assert check.current.title == "SHIFT + Sync"
    assert check.press(("1", "NOTE", "92")).status == OK
    check.skip()
    unknown = check.press(("8", "NOTE", "99"))
    assert unknown.detail() == "got Note 99 on channel 8, which isn't in the profile"
    assert check.done and check.press(("1", "NOTE", "88")) is None
    assert check.counts() == {OK: 2, MISMATCH: 1, SKIPPED: 1}


def test_only_presses_count():
    assert press_from_event(_event(40)) == ("1", "NOTE", "40")
    assert press_from_event(_event(40, "0")) is None
    assert press_from_event(_event(7, "0", "Control Change")) is None  # a CC button's release
    assert press_from_event(_event(7, "64", "Control Change")) == ("1", "CC", "7")
    assert press_from_event(_event(40, direction="out")) is None


def test_report_and_issue_url():
    _register()
    check = ProfileCheck.start(NAME)
    check.press(("1", "NOTE", "88"))
    check.press(("1", "NOTE", "99"))
    check.skip()
    text = report_text(check, "1.2.3", "DDJ TEST", now=datetime(2026, 10, 30, tzinfo=UTC))
    assert "## Profile check: Check Profile" in text
    assert "- Result: 1 ok, 1 mismatch, 1 skipped, 1 not checked (of 4)" in text
    assert "- **SHIFT + Sync** (Deck): got Note 99 on channel 1, which isn't in the profile" in text
    assert "### Skipped (not on this unit)" in text and "- Cue (Deck)" in text
    url, inlined = report_issue_url(check, text)
    query = parse_qs(urlparse(url).query)
    assert inlined and query["labels"] == ["profile-check"] and query["body"] == [text]
    assert query["title"] == ["Profile check: Check Profile (1 ok, 1 mismatch)"]
    long_url, inlined = report_issue_url(check, text * 50)
    assert not inlined and len(long_url) < 6000


def test_dialog_runs_a_check_from_live_events(tmp_path):
    from djmidi.gui.profile_check_dialog import ProfileCheckDialog

    _register()
    opened = []
    dialog = ProfileCheckDialog([NAME], ["TEST", "OTHER"], ensure_listening=lambda: True, initial=NAME,
                                open_url=opened.append, reports_dir=tmp_path)
    assert not dialog.feed_event(_event(88))  # not started
    assert dialog.start()
    assert dialog.prompt.text().startswith("Press Sync")
    dialog.port_combo.setCurrentIndex(dialog.port_combo.findData("TEST"))
    assert not dialog.feed_event(_event(88, port="OTHER"))  # another input
    assert not dialog.feed_event(_event(88, "0"))  # a release
    assert dialog.feed_event(_event(88))
    assert dialog.feed_event(_event(99))
    assert "isn't in the profile" in dialog.status.text()
    dialog.skip()
    assert dialog.results.count() == 3 and dialog.results.item(0).text() == "✓ Sync"
    dialog.save_report(str(tmp_path / "report.md"))
    assert "1 ok, 1 mismatch" in (tmp_path / "report.md").read_text(encoding="utf-8")
    url = dialog.submit_report()
    assert opened == [url] and "profile-check" in url


def test_main_window_routes_presses_to_the_check_not_to_macros(tmp_path, monkeypatch):
    from djmidi.gui import main_window as main_window_module
    from djmidi.gui.main_window import MainWindow

    _register()
    monkeypatch.setattr(main_window_module, "list_input_ports", lambda: ["TEST"])
    window = MainWindow()
    try:
        played = []
        monkeypatch.setattr(window, "_play_triggered_macros", lambda event: played.append(event))
        monkeypatch.setattr(window, "_ensure_learn_listening", lambda: True)
        dialog = window.open_profile_check(NAME)
        assert window.open_profile_check() is dialog  # one window
        dialog._ensure_listening = lambda: True
        dialog.start()
        window._on_live_midi_event(_event(88))
        assert dialog.check.counts()[OK] == 1 and played == []
        dialog.close()
        assert window._profile_check_dialog is None
        window._on_live_midi_event(_event(88))
        assert len(played) == 1
    finally:
        window.close()
