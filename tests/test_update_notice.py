"""GUI side of the update notice (issue #193). Fake fetchers only: no network."""

import json

from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication, QMessageBox

from djmidi.gui import main_window as main_window_module
from djmidi.gui.main_window import MainWindow
from djmidi.gui.update_notice import UpdateChecker
from djmidi.plugins import PluginPreferences
from djmidi.update_check import ReleaseInfo

_RELEASE = ReleaseInfo(
    tag="v9.0.0-future",
    version=(9, 0, 0),
    url="https://github.com/guillain/DJ-MIDI-Studio/releases/tag/v9.0.0-future",
)
_OLD_RELEASE = ReleaseInfo(tag="v0.0.1-ancient", version=(0, 0, 1), url=_RELEASE.url)


def _fake_fetch(url):
    return json.dumps({"tag_name": "v9.0.0-future", "html_url": _RELEASE.url}).encode()


def _wait_for(checker, pool):
    pool.waitForDone(5000)
    for _ in range(50):
        QApplication.processEvents()
        if not checker.running:
            return


def _window(tmp_path, monkeypatch):
    window = MainWindow()
    window.preferences = PluginPreferences()
    window.preferences_path = tmp_path / "preferences.json"
    monkeypatch.setattr(main_window_module, "current_version", lambda: "0.48.65")
    return window


def _settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_update_checker_runs_off_the_main_thread_and_reports_back():
    checker = UpdateChecker(fetch=_fake_fetch)
    results = []
    checker.finished.connect(lambda release, manual: results.append((release, manual)))
    pool = QThreadPool()
    assert checker.start(manual=True, pool=pool) is True
    assert checker.start(manual=True, pool=pool) is False  # one check at a time
    _wait_for(checker, pool)
    assert results == [(_RELEASE, True)]
    assert checker.running is False


def test_update_checker_reports_none_when_offline():
    def offline(url):
        raise OSError("offline")

    checker = UpdateChecker(fetch=offline)
    results = []
    checker.finished.connect(lambda release, manual: results.append((release, manual)))
    pool = QThreadPool()
    checker.start(pool=pool)
    _wait_for(checker, pool)
    assert results == [(None, False)]


def test_main_window_never_checks_for_updates_in_tests(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    started = []
    monkeypatch.setattr(window._update_checker, "start", lambda manual=False: started.append(manual) or True)
    assert window._check_for_updates_at_startup() is False  # no QSettings outside the real app
    assert started == []
    assert window._update_label.isHidden()


def test_startup_check_respects_the_preference_and_the_daily_limit(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    settings = _settings(tmp_path)
    monkeypatch.setattr(window, "_layout_settings", lambda: settings)
    started = []
    monkeypatch.setattr(window._update_checker, "start", lambda manual=False: started.append(manual) or True)

    window.preferences.check_for_updates = False
    assert window._check_for_updates_at_startup() is False

    window.preferences.check_for_updates = True
    assert window._check_for_updates_at_startup() is True
    assert started == [False]

    window._on_update_check_finished(_OLD_RELEASE, False)  # a successful check is remembered
    assert window._check_for_updates_at_startup() is False
    assert started == [False]


def test_failed_startup_check_does_not_count_toward_the_daily_limit(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    settings = _settings(tmp_path)
    monkeypatch.setattr(window, "_layout_settings", lambda: settings)
    monkeypatch.setattr(window._update_checker, "start", lambda manual=False: True)
    window._on_update_check_finished(None, False)
    assert settings.value("updates/last_check") is None
    assert window._check_for_updates_at_startup() is True


def test_newer_release_shows_a_status_bar_link(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    window._on_update_check_finished(_RELEASE, False)
    assert not window._update_label.isHidden()
    assert _RELEASE.url in window._update_label.text()
    assert "Update available: v9.0.0" in window._update_label.text()
    assert window._update_label.openExternalLinks()
    assert "v9.0.0 is available (you have v0.48.65)" in window.statusBar().currentMessage()


def test_automatic_check_is_silent_when_up_to_date_or_offline(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: shown.append(args))
    window._on_update_check_finished(_OLD_RELEASE, False)
    window._on_update_check_finished(None, False)
    assert shown == []
    assert window._update_label.isHidden()


def test_manual_check_reports_every_outcome(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    shown = []
    opened = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[2]))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(main_window_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))

    window._on_update_check_finished(None, True)
    assert "Couldn't reach GitHub" in shown[-1]
    window._on_update_check_finished(_OLD_RELEASE, True)
    assert "up to date" in shown[-1]
    window._on_update_check_finished(_RELEASE, True)
    assert opened == [_RELEASE.url]


def test_help_menu_action_starts_a_manual_check(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    started = []
    monkeypatch.setattr(window._update_checker, "start", lambda manual=False: started.append(manual) or True)
    window._check_updates_action.trigger()
    assert started == [True]
    assert window.statusBar().currentMessage() == "Checking for updates..."
