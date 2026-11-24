"""Golden rule: our features must become obvious -- the next step is always
on screen, with one clear button."""

from djmidi import startup_check as sc
from djmidi.gui.start_hint import StartHint


def _window(monkeypatch, inputs=()):
    from djmidi.gui import main_window as mw

    monkeypatch.setattr(mw, "list_input_ports", lambda: list(inputs))
    monkeypatch.setattr(mw, "list_output_ports", list)
    return mw, mw.MainWindow()


def test_mapping_views_say_what_to_do_before_a_mapping_is_open(monkeypatch):
    _mw, window = _window(monkeypatch)
    opened = []
    monkeypatch.setattr(window, "_on_open", lambda: opened.append(True))
    for splitter in (window.channel_splitter, window.deck_splitter, window.controller_splitter):
        hint = splitter.widget(0)
        assert isinstance(hint, StartHint) and hint.title_label.text() == "No mapping open yet"
    window.channel_splitter.widget(0).button.click()
    assert opened == [True]


def test_the_mapping_group_is_named_mapping(monkeypatch):
    from PySide6.QtWidgets import QTabWidget

    _mw, window = _window(monkeypatch)
    titles = [tabs.tabText(i) for tabs in window.left_tabs.findChildren(QTabWidget) for i in range(tabs.count())]
    assert "Mapping" in titles and "By…" not in titles


def test_the_dashboard_shows_the_setup_verdict_and_opens_the_check(monkeypatch):
    _mw, window = _window(monkeypatch, ["DDJ-XP2"])
    report = window.update_setup_summary()
    intro = window.introduction_view
    assert report.devices == ["DDJ-XP2"]
    assert intro.setup_headline.text().startswith("Almost ready")
    assert "DDJ-XP2" in intro.setup_devices.text()
    assert intro._setup_card.property("status") == sc.TODO
    intro.setup_check_button.click()
    assert window._startup_check_dialog is not None


def test_nothing_plugged_in_still_tells_the_dj_what_to_do(monkeypatch):
    _mw, window = _window(monkeypatch)
    window.update_setup_summary()
    assert "plug one in" in window.introduction_view.setup_devices.text()


def test_controller_setup_offers_learning_on_its_empty_table(monkeypatch):
    from djmidi.gui.controller_setup import ControllerSetupView

    view = ControllerSetupView()
    assert view._learn_button.text() == "Learn"
    assert view.table_empty_state.title_label.text() == "Nothing learned yet"
    started = []
    monkeypatch.setattr(view, "_start_learning", lambda: started.append(True))
    view._port_list.addItem("DDJ-XP2")
    from PySide6.QtCore import Qt

    view._port_list.item(view._port_list.count() - 1).setCheckState(Qt.CheckState.Unchecked)
    view.start_learning_from_hint()
    assert started and view._is_checked(view._port_list.count() - 1)


def test_the_studio_modes_are_chosen_at_the_top():
    from djmidi.gui.atelier_view import AtelierView

    view = AtelierView()
    labels = [b.text() for b in view.mode_group.buttons()]
    assert labels == ["Light scenes", "Remap", "Macros"]
    assert view.lower_tabs.tabBar().isHidden()
    assert view.mode_group.checkedId() == 0 and "lights up" in view.mode_hint.text()
    view.mode_group.button(2).click()
    assert view.editing_macros and view.mode_group.checkedId() == 2
    assert view.scene_actions.isHidden()  # save / send belong to scenes
    view.lower_tabs.setCurrentIndex(1)  # programmatic switches follow too
    assert view.mode_group.checkedId() == 1 and "act as another" in view.mode_hint.text()
    view.mode_group.button(0).click()
    assert not view.scene_actions.isHidden()


def test_an_empty_scene_says_how_to_start():
    from djmidi.gui.atelier_view import AtelierView

    view = AtelierView()
    view.resize(1000, 700)
    view.show()
    assert view.state_list.count() == 0
    assert view.state_empty.isVisible() and view.state_empty.title_label.text() == "No light in this scene yet"
    view.close()


def test_the_images_tab_says_what_it_is_for():
    from djmidi.gui.controller_image_view import ControllerImageView

    view = ControllerImageView()
    assert "Press a button on your controller" in view.usage_hint.text()


def test_preferences_group_what_a_dj_changes_and_hide_the_advanced():
    from PySide6.QtWidgets import QGroupBox

    from djmidi.gui.preferences_dialog import PreferencesDialog
    from djmidi.plugins.preferences import PluginPreferences

    dialog = PreferencesDialog(PluginPreferences())
    titles = [box.title() for box in dialog.findChildren(QGroupBox)]
    for title in ("Look", "When the app starts", "Controller sync", "Your files", "Advanced"):
        assert title in titles
    assert dialog.advanced_box.isHidden()
    dialog.show_advanced.setChecked(True)
    assert not dialog.advanced_box.isHidden()


def test_routing_off_offers_the_switch_in_its_own_window(monkeypatch):
    _mw, window = _window(monkeypatch)
    window.preferences.routing_enabled = False
    window.midi_routing_view.set_routing_enabled(False)
    assert not window.midi_routing_view.routing_off_banner.isHidden()
    saved = []
    monkeypatch.setattr(window, "_save_preferences", lambda: saved.append(True))
    window.midi_routing_view.enable_routing_button.click()
    assert window.preferences.routing_enabled and saved
    assert window.midi_routing_view.routing_off_banner.isHidden()


def test_the_live_monitor_log_says_how_to_start():
    from djmidi.gui.live_monitor import LiveMonitorView

    view = LiveMonitorView()
    assert view.log_empty_state.title_label.text() == "Nothing received yet"
    assert view._recording_label.isHidden()


def test_the_metronome_says_what_it_does():
    from djmidi.gui.metronome_view import MetronomeView

    assert "Controller Setup session" in MetronomeView().purpose_label.text()


def test_tools_have_their_own_menu_and_view_only_changes_the_look(monkeypatch):
    _mw, window = _window(monkeypatch)
    menus = {a.text(): a.menu() for a in window.menuBar().actions() if a.menu()}
    assert list(menus)[:7] == ["&File", "&Edit", "&View", "&Tools", "&Macros", "&Tests", "&Help"]
    tools = menus["&Tools"].actions()
    for action in (window._new_emulator_action, window._layer_map_action):
        assert action in tools and action not in menus["&View"].actions()
    assert window._latency_action in menus["&Tests"].actions()
    assert window._tool_docks["monitor"].toggleViewAction() in tools
    assert window._helpful_notes_action in menus["&Help"].actions()
    assert window._sync_scene_label.text() == "Scene:"


def test_an_untagged_track_shows_its_file_name():
    from djmidi.gui.music_library_view import LibraryTableModel

    class Row:
        path = "/music/07 Anoa - Echoes.mp3"
        metadata = None
        category = None
        category_suggestion = None
        missing = False
        bpm = None
        camelot_key = None

    assert LibraryTableModel._display(Row(), "title") == "07 Anoa - Echoes"
    assert LibraryTableModel._display(Row(), "artist") == ""


def test_folders_fold_into_one_line_once_the_library_has_tracks(monkeypatch):
    from djmidi.gui.music_library_view import MusicLibraryView

    view = MusicLibraryView()
    view._update_first_steps()
    assert view._folders_summary_row.isHidden() and not view._folders_body.isHidden()
    monkeypatch.setattr(view.table_model, "rowCount", lambda *_a: 12)
    view.roots_list.addItem("/music")
    view._update_first_steps()
    assert not view._folders_summary_row.isHidden() and view._folders_body.isHidden()
    assert "12 track(s) in 1 folder(s)" in view.folders_summary.text()
    assert view.status_label.text() == ""
    view.folders_toggle.setChecked(True)
    assert not view._folders_body.isHidden()


def test_an_empty_set_says_how_to_fill_it():
    from djmidi.gui.music_library_view import MusicLibraryView
    from djmidi.gui.set_preparation import SetPreparationPanel

    panel = MusicLibraryView().findChild(SetPreparationPanel)
    assert panel.list_empty_state.title_label.text() == "Your set is empty"
