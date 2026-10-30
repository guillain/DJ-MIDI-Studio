"""The prepared set on the Stage Mode screen (issue #366)."""

from djmidi.library.set_prep import (
    STATUS_INCOMPATIBLE,
    STATUS_OK,
    SetTrack,
    analyze_set,
)
from djmidi.stage import stage_set_view

TRACKS = [
    SetTrack("/a.mp3", "Intro", "DJ A", 124.0, "8A", 5),
    SetTrack("/b.mp3", "Build", "DJ B", 126.0, "9A", 7),
    SetTrack("/c.mp3", "Clash", None, 150.0, "2B"),
]


def test_view_shows_position_current_next_and_transition():
    transitions = analyze_set(TRACKS)
    first = stage_set_view(TRACKS, transitions, 0)
    assert first.position == "Set 1/3"
    assert first.current == "DJ A — Intro"
    assert first.current_details == "124 BPM · 8A · energy 5"
    assert first.next == "Next: DJ B — Build · 126 BPM · 9A · energy 7"
    assert first.transition == "Transition OK · BPM +1.6 %" and first.status == STATUS_OK
    second = stage_set_view(TRACKS, transitions, 1)
    assert second.status == STATUS_INCOMPATIBLE and "8A" not in second.transition and second.transition
    last = stage_set_view(TRACKS, transitions, 9)  # clamped
    assert last.position == "Set 3/3" and last.next == "Last track of the set" and last.status == ""
    assert stage_set_view([], [], 0) is None


def test_stage_window_moves_through_the_set():
    from djmidi.gui.stage_window import StageWindow

    window = StageWindow(config_provider=lambda: None, set_provider=lambda: (TRACKS, analyze_set(TRACKS)))
    try:
        assert window._set_title.text() == "Set 1/3" and not window._set_previous_button.isEnabled()
        assert window.move_in_set(1) == 1 and window._set_current.text() == "DJ B — Build"
        assert window._set_transition.property("status") == "incompatible"
        window._set_shortcuts[0].activated.emit()  # PageDown
        assert window.set_index == 2 and not window._set_next_button.isEnabled()
        window._set_shortcuts[1].activated.emit()  # PageUp
        assert window.set_index == 1
    finally:
        window.close()

    empty = StageWindow(config_provider=lambda: None)
    try:
        assert "No set prepared" in empty._set_details.text()
        assert not empty._set_next_button.isEnabled()
    finally:
        empty.close()


def test_main_window_resumes_the_set_where_stage_mode_left_it(monkeypatch):
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        monkeypatch.setattr(window, "_stage_set", lambda: (TRACKS, analyze_set(TRACKS)))
        monkeypatch.setattr(window.live_monitor_view, "ensure_monitoring_started", lambda: None)
        window._stage_mode_action.setChecked(True)
        window._stage_window.move_in_set(2)
        window._stage_window.close()
        window._stage_mode_action.setChecked(True)
        assert window._stage_window.set_index == 2
        window._stage_window.close()
    finally:
        window.close()
