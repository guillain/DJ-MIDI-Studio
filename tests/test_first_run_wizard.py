from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QDialog

from djmidi.first_run import FirstRunChoices
from djmidi.gui.first_run_wizard import FirstRunWizard
from djmidi.gui.main_window import MainWindow
from djmidi.plugins import PluginPreferences


def _serato_folder(home: Path) -> Path:
    folder = home / "Music" / "_Serato_" / "MIDI" / "Xml"
    folder.mkdir(parents=True)
    return folder


def test_wizard_proposes_detected_controller_and_newest_mapping(tmp_path):
    folder = _serato_folder(tmp_path)
    mapping = folder / "mine.xml"
    mapping.write_text("<midi/>", encoding="utf-8")
    wizard = FirstRunWizard(lambda: ["PIONEER DDJ-XP2", "Mystery Box"], home=tmp_path)

    choices = wizard.choices()

    assert choices == FirstRunChoices(controller="DDJ-XP2", mapping=mapping, record_sync_set=False)
    assert "Mystery Box" in wizard.controllers_page.status_label.text()


def test_wizard_defaults_to_nothing_without_controllers_or_mappings(tmp_path):
    wizard = FirstRunWizard(list, home=tmp_path)
    assert wizard.choices() == FirstRunChoices()
    assert "No MIDI controller" in wizard.controllers_page.status_label.text()


def test_wizard_survives_a_failing_midi_backend(tmp_path):
    def broken() -> list[str]:
        raise RuntimeError("no backend")

    assert FirstRunWizard(broken, home=tmp_path).choices().controller is None


def test_rescan_picks_up_a_controller_plugged_in_later(tmp_path):
    ports: list[str] = []
    wizard = FirstRunWizard(lambda: ports, home=tmp_path)
    ports.append("XDJ-XZ")
    wizard.controllers_page.rescan_button.click()
    assert wizard.choices().controller == "XDJ-XZ"


def test_wizard_choices_follow_user_selection(tmp_path):
    folder = _serato_folder(tmp_path)
    (folder / "mine.xml").write_text("<midi/>", encoding="utf-8")
    wizard = FirstRunWizard(list, home=tmp_path)
    wizard.mapping_page.mapping_list.setCurrentRow(0)
    wizard.sync_page.record_checkbox.setChecked(True)
    assert wizard.choices() == FirstRunChoices(record_sync_set=True)


_WINDOWS: list[MainWindow] = []


@pytest.fixture(autouse=True)
def _close_windows():
    # Every MainWindow left alive makes later tests (a theme change restyles
    # every widget) dramatically slower -- close and delete them.
    yield
    while _WINDOWS:
        window = _WINDOWS.pop()
        window._layout_settings = lambda: None  # never persist a test's fake settings
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _window(tmp_path):
    window = MainWindow()
    _WINDOWS.append(window)
    window.preferences = PluginPreferences()
    window.preferences_path = tmp_path / "preferences.json"
    return window


class _StubWizard:
    def __init__(self, result, choices):
        self._result, self._choices = result, choices

    def exec(self):
        return self._result

    def choices(self):
        return self._choices


def test_wizard_never_opens_by_itself_in_tests(tmp_path):
    window = _window(tmp_path)
    window._preferences_existed = False
    assert not window._should_show_first_run_wizard()


def test_help_menu_offers_the_wizard(tmp_path):
    window = _window(tmp_path)
    assert window._first_run_action.text() == "First-Run &Setup..."


def test_accepted_wizard_applies_choices(tmp_path, monkeypatch):
    window = _window(tmp_path)
    opened, recorded = [], []
    monkeypatch.setattr(window, "_load_mapping_from_path", lambda path, software_id=None: opened.append((path, software_id)))
    monkeypatch.setattr(window, "_start_recording", lambda: recorded.append(True))
    choices = FirstRunChoices(controller="XDJ-XZ", mapping=tmp_path / "m.xml", record_sync_set=True)

    assert window._on_first_run_wizard(_StubWizard(QDialog.DialogCode.Accepted, choices)) == choices

    assert window.introduction_view._controller_combo.currentText() == "XDJ-XZ"
    assert opened == [(tmp_path / "m.xml", "serato")]
    assert recorded == [True]


def test_skipped_wizard_changes_nothing(tmp_path, monkeypatch):
    window = _window(tmp_path)
    opened = []
    monkeypatch.setattr(window, "_load_mapping_from_path", lambda *a, **k: opened.append(a))
    before = window.introduction_view._controller_combo.currentText()
    choices = FirstRunChoices(controller="XDJ-XZ", mapping=tmp_path / "m.xml")

    assert window._on_first_run_wizard(_StubWizard(QDialog.DialogCode.Rejected, choices)) is None

    assert opened == []
    assert window.introduction_view._controller_combo.currentText() == before


def test_disabled_wizard_never_shows_even_in_the_real_app(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window._preferences_existed = False
    monkeypatch.setattr(window, "_layout_settings", lambda: _FakeSettings())
    assert window._should_show_first_run_wizard()
    window.first_run_wizard_enabled = False
    assert not window._should_show_first_run_wizard()


def test_done_flag_stops_the_wizard_reopening(tmp_path, monkeypatch):
    window = _window(tmp_path)
    window._preferences_existed = False
    settings = _FakeSettings()
    monkeypatch.setattr(window, "_layout_settings", lambda: settings)
    window._on_first_run_wizard(_StubWizard(QDialog.DialogCode.Rejected, FirstRunChoices()))
    assert not window._should_show_first_run_wizard()


class _FakeSettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass
