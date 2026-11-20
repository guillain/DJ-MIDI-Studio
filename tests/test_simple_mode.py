"""Simple mode (default) vs Expert mode: testers found the app too
complicated (2026-11-20); expert tools are hidden, never removed."""

from djmidi.gui.main_window import MainWindow
from djmidi.plugins.preferences import PluginPreferences


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
