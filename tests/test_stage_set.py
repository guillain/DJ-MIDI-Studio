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


LIBRARY = [
    SetTrack("/a.mp3", "Intro", "DJ A", 124.0, "8A"),  # in the set: never suggested
    SetTrack("/near.mp3", "Near", "DJ C", 124.5, "8A"),
    SetTrack("/relative.mp3", "Relative", "DJ D", 122.0, "8B"),
    SetTrack("/far.mp3", "Far", "DJ E", 140.0, "8A"),  # BPM out of tolerance
    SetTrack("/clash.mp3", "Clash", "DJ F", 124.0, "3B"),  # key clash
    SetTrack("/nokey.mp3", "No key", None, 124.0, None),
    SetTrack("/gone.mp3", "Gone", None, 124.0, "8A", indexed=False),
]


def test_suggestions_are_compatible_closest_first_and_outside_the_set():
    from djmidi.stage import suggest_next_tracks, suggestion_line

    current = TRACKS[0]
    suggestions = suggest_next_tracks(current, LIBRARY, {track.path for track in TRACKS})
    assert [track.path for track in suggestions] == ["/near.mp3", "/relative.mp3"]
    assert suggest_next_tracks(current, LIBRARY, (), limit=1)[0].path == "/near.mp3"
    assert suggest_next_tracks(TRACKS[2].__class__("/x.mp3", bpm=None, camelot_key="8A"), LIBRARY) == []
    assert suggestion_line(suggestions[0]) == "DJ C — Near · 124.5 BPM · 8A"


def test_stage_window_shows_suggestions_for_the_current_track():
    from djmidi.gui.stage_window import StageWindow
    from djmidi.stage import suggest_next_tracks

    asked = []

    def provider(current, set_paths):
        asked.append((current.path, set_paths))
        return suggest_next_tracks(current, LIBRARY, set_paths)

    window = StageWindow(
        config_provider=lambda: None,
        set_provider=lambda: (TRACKS, analyze_set(TRACKS)),
        suggestion_provider=provider,
    )
    try:
        assert asked[-1] == ("/a.mp3", {"/a.mp3", "/b.mp3", "/c.mp3"})
        assert "DJ C — Near" in window.set_suggestions_text and "Far" not in window.set_suggestions_text
        window.move_in_set(2)  # 150 BPM, 2B: nothing in the library fits
        assert window.set_suggestions_text == "No other compatible track in the library."
    finally:
        window.close()
    plain = StageWindow(config_provider=lambda: None, set_provider=lambda: (TRACKS, analyze_set(TRACKS)))
    try:
        assert plain._set_suggestions.isHidden()
    finally:
        plain.close()


def test_main_window_suggests_from_the_library_rows(monkeypatch):
    from djmidi.gui.main_window import MainWindow
    from djmidi.library.metadata import TrackMetadata
    from djmidi.library.workspace import LibraryRow

    window = MainWindow()
    try:
        rows = [
            LibraryRow(1, "/near.mp3", False, TrackMetadata(title="Near", artist="DJ C", bpm=124.5), "8A", None),
            LibraryRow(2, "/a.mp3", False, TrackMetadata(title="Intro", bpm=124.0), "8A", None),
        ]
        window.music_library_view.table_model.set_rows(rows)
        suggestions = window._stage_suggestions(TRACKS[0], {"/a.mp3"})
        assert [track.path for track in suggestions] == ["/near.mp3"]
    finally:
        window.close()


def test_stage_window_shows_the_current_note_and_the_next_one():
    from djmidi.gui.stage_window import StageWindow

    tracks = [
        SetTrack("/a.mp3", "Intro", "DJ A", 124.0, "8A", note="long intro"),
        SetTrack("/b.mp3", "Build", "DJ B", 126.0, "9A", note="mix out on the break"),
        SetTrack("/c.mp3", "Peak", "DJ C", 127.0, "9A"),
    ]
    window = StageWindow(config_provider=lambda: None, set_provider=lambda: (tracks, analyze_set(tracks)))
    try:
        assert window._set_note.text() == "long intro" and not window._set_note.isHidden()
        assert "Note: mix out on the break" in window._set_next.text()
        window.move_in_set(2)
        assert window._set_note.isHidden() and "Note:" not in window._set_next.text()
    finally:
        window.close()
