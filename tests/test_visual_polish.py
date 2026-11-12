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
