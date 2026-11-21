"""Simple mode (default) vs Expert mode: testers found the app too
complicated (2026-11-20); expert tools are hidden, never removed."""

from pathlib import Path

from djmidi.gui.main_window import MainWindow
from djmidi.plugins.preferences import PluginPreferences

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_simple_mode_is_the_default_and_hides_the_expert_tools():
    assert PluginPreferences().expert_mode is False
    window = MainWindow()
    tabs = window.left_tabs
    for key in ("atelier", "channel", "deck"):
        assert not tabs.is_page_visible(key)
    for key in ("intro", "setup", "images", "controller", "library", "mix"):
        assert tabs.is_page_visible(key)
    assert not window._compare_action.isVisible()
    assert not window._performance_mode_action.isVisible()
    assert window._stage_mode_action.isVisible()  # set prep and Stage Mode stay
    assert window.introduction_view.expert_button.text() == "Show every tool"


def test_the_dashboard_button_switches_to_expert_and_back(tmp_path, monkeypatch):
    window = MainWindow()
    monkeypatch.setattr(window, "_save_preferences", lambda: None)
    window.introduction_view.expert_button.click()
    assert window.preferences.expert_mode
    assert window.left_tabs.is_page_visible("channel") and window._compare_action.isVisible()
    assert "Expert mode on" in window.statusBar().currentMessage()
    window.introduction_view.expert_button.click()
    assert not window.left_tabs.is_page_visible("atelier")


def test_a_button_that_asks_for_an_expert_page_still_opens_it():
    window = MainWindow()
    window.left_tabs.setCurrentIndex(window._tab_indexes["atelier"])
    assert window.left_tabs.currentIndex() == window._tab_indexes["atelier"]
    assert window.left_tabs.is_page_visible("atelier")


def test_expert_mode_round_trips_in_preferences():
    prefs = PluginPreferences(expert_mode=True)
    assert PluginPreferences.from_json(prefs.to_json()).expert_mode is True
    assert PluginPreferences.from_json('{"enabled": {}}').expert_mode is False


def test_the_dashboard_lists_what_needs_the_dj_with_its_button(monkeypatch):
    from djmidi import startup_check as sc
    from djmidi.dj_software import FoundSoftware
    from djmidi.gui import main_window as mw

    monkeypatch.setattr(mw, "list_input_ports", lambda: ["DDJ-XP2"])
    monkeypatch.setattr(mw, "list_output_ports", list)
    window = mw.MainWindow()
    monkeypatch.setattr(window, "_find_dj_software", lambda: [FoundSoftware("serato", "Serato DJ", True)])
    window.update_setup_summary()
    intro = window.introduction_view
    buttons = [w for w in intro.findChildren(type(intro.expert_button)) if w.property("chip")]
    labels = [b.text() for b in buttons if b.isVisibleTo(intro)]
    assert labels[:1] == ["Check it"] and len(labels) <= intro.MAX_STEPS
    assert "Serato DJ (open)" in intro.setup_software.text()
    first = next(b for b in buttons if b.text() == "Check it")
    opened = []
    monkeypatch.setattr(window, "open_profile_check", lambda controller=None: opened.append(controller))
    first.click()
    assert opened == ["DDJ-XP2"]
    assert sc.CHECK  # the action came from the startup check


def test_mapping_suggestions_pick_the_newest_file_named_after_each_controller(tmp_path):
    import os

    from djmidi.startup_check import mapping_suggestions

    old, new = tmp_path / "ddj-xp2 old.xml", tmp_path / "XDJ-XZ DDJ-XP2 - 4 decks.xml"
    for path in (old, new):
        path.write_text("<midi/>")
    os.utime(old, (1, 1))
    other = tmp_path / "flx4.xml"
    other.write_text("<midi/>")
    got = mapping_suggestions(["DDJ-XP2", "DDJ-1000"], {"serato": [old, new, other]})
    assert got == [("DDJ-XP2", "serato", new)]


def test_the_dashboard_opens_my_mapping_in_one_click(monkeypatch, tmp_path):
    from djmidi.gui import main_window as mw

    fixture = tmp_path / "XDJ-XZ DDJ-XP2.xml"
    fixture.write_bytes((__import__("pathlib").Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml").read_bytes())
    monkeypatch.setattr(mw, "list_input_ports", lambda: ["DDJ-XP2"])
    monkeypatch.setattr(mw, "list_output_ports", list)
    window = mw.MainWindow()
    monkeypatch.setattr(window, "_mapping_files_by_software", lambda: {"serato": [fixture]})
    window.update_setup_summary()
    intro = window.introduction_view
    button = intro.setup_mappings.itemAt(0).widget()
    assert button.text() == "Open my Serato mapping for the DDJ-XP2"
    button.click()
    assert window.current_path is not None and window.software_id == "serato"
    assert intro.setup_mappings.count() == 0  # that file is open now


def test_heavy_screens_keep_the_essentials_in_simple_mode():
    from djmidi.gui import simple_mode
    from djmidi.gui.controller_setup import ControllerSetupView
    from djmidi.gui.music_library_view import MusicLibraryView

    music = MusicLibraryView()
    setup = ControllerSetupView()
    hidden = [music.duplicates_button, music.health_button, music.stats_button, music.history_button]
    assert all(button.isHidden() for button in hidden)
    assert not music.analyse_button.isHidden() and not music.add_root_button.isHidden()
    categories = next(i for i in range(music.side_tabs.count()) if music.side_tabs.tabText(i) == "Categories")
    assert not music.side_tabs.isTabVisible(categories)
    simple_mode.apply(True)
    assert not any(button.isHidden() for button in hidden)
    assert music.side_tabs.isTabVisible(categories)
    assert setup  # built with its MIDI Output box registered


def test_a_group_left_with_one_page_hides_its_tab_row():
    window = MainWindow()
    mapping_group = window.left_tabs._pages[window._tab_indexes["controller"]].path[-1]
    assert mapping_group.tabBar().isHidden()  # only By Controller in simple mode
    window.set_expert_mode(True)
    assert not mapping_group.tabBar().isHidden()


def test_simple_mode_opens_no_window_at_launch(monkeypatch):
    window = MainWindow()
    opened = []
    monkeypatch.setattr(window, "_layout_settings", lambda: object())  # as in the real app
    monkeypatch.setattr(window, "update_setup_summary", lambda *a: None)
    monkeypatch.setattr(window, "_should_show_first_run_wizard", lambda: True)
    monkeypatch.setattr(window, "_on_first_run_wizard", lambda *a: opened.append("wizard"))
    monkeypatch.setattr(window, "_show_helpful_notes_if_enabled", lambda: opened.append("notes"))
    monkeypatch.setattr(window, "open_startup_check", lambda *a: opened.append("check"))
    window.left_tabs.setCurrentIndex(window._tab_indexes["library"])
    window._show_startup_dialog()
    assert opened == []
    assert window.left_tabs.currentIndex() == window._tab_indexes["intro"]
    window._startup_watch_timer.stop()
    window.preferences.expert_mode = True
    window._show_startup_dialog()
    assert opened == ["wizard"]
    window._startup_watch_timer.stop()


def test_by_controller_shows_only_my_controllers_in_simple_mode(monkeypatch):
    from djmidi.gui import main_window as mw
    from djmidi.startup_check import controllers_named_in

    assert controllers_named_in("xdj_xz-ddj_xp2-4decks", ["XDJ-XZ", "DDJ-XP2", "DDJ-REV1"]) == ["XDJ-XZ", "DDJ-XP2"]
    monkeypatch.setattr(mw, "list_input_ports", list)
    window = mw.MainWindow()
    window._load_mapping_from_path(FIXTURE, software_id="serato")
    titles = {v.model().horizontalHeaderItem(0).text() for v in window._controller_tree_views}
    assert titles == {"XDJ-XZ", "DDJ-XP2"}
    window.set_expert_mode(True)
    assert len(window._controller_tree_views) > 2  # every model the notes match
