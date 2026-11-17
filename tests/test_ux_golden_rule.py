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
