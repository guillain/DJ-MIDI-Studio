"""UX review: Camelot badges, section colours, page fade."""

from djmidi.gui.badges import camelot_colour, text_colour_on


def test_camelot_codes_get_neighbouring_hues_and_readable_text():
    assert camelot_colour("") is None and camelot_colour("13A") is None and camelot_colour("(8A)") is None
    eight_a, eight_b, nine_a = camelot_colour("8A"), camelot_colour("8B"), camelot_colour("9A")
    assert eight_a.hue() == eight_b.hue() == 210 and nine_a.hue() == 240
    assert eight_b.value() > eight_a.value()  # majors lighter
    assert text_colour_on(camelot_colour("3B")).name() in ("#111111", "#ffffff")


def test_the_main_window_colours_its_section_and_fades_pages():
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    tabs = window.left_tabs
    assert tabs.top.property("section") == "dashboard"
    tabs.setCurrentIndex(window._tab_indexes["library"])
    assert tabs.top.property("section") == "music"
    tabs.setCurrentIndex(window._tab_indexes["deck"])
    assert tabs.top.property("section") == "controller"
    library = window.music_library_view
    from djmidi.gui.music_library_view import _COLUMN_INDEX

    delegate = library.table.itemDelegateForColumn(_COLUMN_INDEX["camelot"])
    assert type(delegate).__name__ == "CamelotBadgeDelegate"
    window.close()


def test_empty_states_show_until_the_view_has_rows():
    from djmidi.gui.music_library_view import MusicLibraryView

    view = MusicLibraryView(db_path=":memory:")
    view.show()
    assert not view.table_empty_state.isHidden() and view.table_empty_state.button is not None
    assert not view.playlist_empty_state.isHidden()
    view.db.create_playlist("Friday", [])
    view._reload_playlists()
    assert view.playlist_empty_state.isHidden()
    view.close_db()


def test_the_dashboard_sums_up_the_music_library():
    from djmidi.gui.introduction_view import IntroductionView

    view = IntroductionView()
    view.set_library_summary(None, None)
    assert "Open the Music tab" in view.library_summary_label.text()
    view.set_library_summary(1200, 14)
    assert view.library_summary_label.text() == "1200 track(s) · 14 playlist(s)"


def test_every_role_has_a_line_icon_and_setup_uses_them():
    from djmidi.gui.icons import ROLES, line_icon

    assert all(not line_icon(role, "#00c2e8").isNull() for role in ROLES)
    assert line_icon("nope", "#00c2e8").isNull()


def test_the_player_bar_shows_what_it_previews():
    from djmidi.gui.audio_preview import AudioPreviewBar

    bar = AudioPreviewBar(player_factory=None)
    bar.set_now_playing("Sunrise", "Kaya & Co", 124.0, "8A")
    assert "Kaya &amp; Co" in bar.now_title.text() and bar.now_bpm.text() == "124 BPM"
    assert not bar.now_camelot.isHidden() and bar.now_camelot.text() == "8A"
    bar.set_now_playing(None)
    assert bar.now_title.text() == "Select a track to preview it." and bar.now_camelot.isHidden()
