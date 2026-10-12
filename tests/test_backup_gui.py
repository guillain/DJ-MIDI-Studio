"""File → Back Up / Restore Workspace and the Preferences buttons (issue #187)."""

import zipfile

from PySide6.QtWidgets import QFileDialog, QMessageBox

from djmidi import backup, user_paths
from djmidi.gui.main_window import MainWindow
from djmidi.gui.preferences_dialog import PreferencesDialog
from djmidi.plugins import PluginPreferences


def test_back_up_and_restore_from_the_file_menu(tmp_path, monkeypatch):
    monkeypatch.setenv("DJMIDI_PREFERENCES_FILE", str(tmp_path / "preferences.json"))
    window = MainWindow()
    try:
        labels = [action.text() for action in window.menuBar().actions()[0].menu().actions()]
        assert "&Back Up Workspace..." in labels
        assert "Restore &Workspace..." in labels

        window._save_preferences()
        profile = user_paths.controllers_dir() / "mine.json"
        profile.write_text("original")
        captured = {}

        def fake_save(_parent, _title, start, _filter):
            captured["start"] = start
            return str(tmp_path / "my backup"), ""

        monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_save)
        target = window._on_backup_workspace()
        assert captured["start"].startswith(str(user_paths.subfolder(user_paths.EXPORTS)))
        assert target == tmp_path / f"my backup{backup.BACKUP_SUFFIX}"
        names = zipfile.ZipFile(target).namelist()
        assert "workspace/Controllers/mine.json" in names
        assert "preferences/preferences.json" in names
        assert "library/library.sqlite3" not in names  # the test library is in memory

        profile.write_text("edited")
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(target), ""))
        monkeypatch.setattr(window, "_confirm_restore", lambda plan: None)
        assert window._on_restore_workspace() is False
        assert profile.read_text() == "edited"

        plans = []
        monkeypatch.setattr(window, "_confirm_restore", lambda plan: plans.append(plan) or False)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
        assert window._on_restore_workspace() is True
        assert profile.read_text() == "original"
        assert any(item.target == profile for item in plans[0].overwrites)
    finally:
        window.close()


def test_restore_reports_an_invalid_backup(tmp_path, monkeypatch):
    bogus = tmp_path / "bogus.zip"
    bogus.write_text("nope")
    window = MainWindow()
    errors = []
    try:
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(bogus), ""))
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a[1]))
        assert window._on_restore_workspace() is False
        assert errors == ["Cannot restore this backup"]
    finally:
        window.close()


def test_preferences_dialog_has_backup_and_restore_buttons():
    dialog = PreferencesDialog(PluginPreferences())
    fired = []
    dialog.backupRequested.connect(lambda: fired.append("backup"))
    dialog.restoreRequested.connect(lambda: fired.append("restore"))
    dialog._backup_button.click()
    dialog._restore_button.click()
    assert fired == ["backup", "restore"]


def test_confirm_restore_lists_overwrites_and_offers_the_library(tmp_path, monkeypatch):
    plan = backup.RestorePlan(
        backup.BackupManifest("0.48.58", "2026-10-11T10:00:00+00:00", (
            backup.BackupEntry(backup.WORKSPACE, "workspace/a.json", 1),
            backup.BackupEntry(backup.LIBRARY, "library/library.sqlite3", 1),
        )),
        [backup.RestoreItem(backup.WORKSPACE, "workspace/a.json", tmp_path / "a.json", True)],
    )
    shown = {}

    def fake_exec(box):
        shown["text"] = box.informativeText()
        shown["check"] = box.checkBox().text() if box.checkBox() else None
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    window = MainWindow()
    try:
        assert window._confirm_restore(plan) is None  # no button clicked = cancelled
    finally:
        window.close()
    assert str(tmp_path / "a.json") in shown["text"]
    assert "0.48.58" in shown["text"]
    assert "library" in shown["check"]
