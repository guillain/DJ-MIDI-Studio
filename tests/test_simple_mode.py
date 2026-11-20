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
