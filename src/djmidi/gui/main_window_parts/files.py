"""MainWindow, part: The mapping's files: open / save / save as, recents and start folders, previous version and comparisons, workspace backup and restore, snapshots, deck copy.

A mixin of `djmidi.gui.main_window.MainWindow` (issue #429); its strings keep the
"MainWindow" translation context."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QAction,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from djmidi import (
    backup,
    file_locations,
    software,
    user_paths,
)
from djmidi.deck_copy import DeckCopyPlan
from djmidi.gui.commands import ReplaceControlsCommand
from djmidi.gui.deck_copy_dialog import DeckCopyDialog
from djmidi.gui.file_reveal import reveal_in_file_manager
from djmidi.gui.list_dialog import ListDialog
from djmidi.gui.main_window_parts._shared import (
    _LAST_DIR_SETTINGS_KEY,
    _LAST_DRAFT_SETTINGS_KEY,
    _LAST_MAPPING_SETTINGS_KEY,
    _LAST_SOFTWARE_SETTINGS_KEY,
    _RECENT_SETTINGS_KEY,
    _detection_translate,
    _human_size,
)
from djmidi.gui.mapping_diff_dialog import MappingDiffDialog
from djmidi.gui.safe_update_dialog import SafeUpdateDialog
from djmidi.gui.snapshots_dialog import SnapshotsDialog
from djmidi.gui.translation import translator
from djmidi.integration_detection import (
    detect_software_mapping,
)
from djmidi.mapping_diff import diff_configs
from djmidi.model import MidiConfig
from djmidi.safe_update import prepare_update
from djmidi.snapshots import Snapshot, list_snapshots, save_snapshot

_LOGGER = logging.getLogger("djmidi.gui.main_window")


class MappingFilesMixin:
    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            QCoreApplication.translate("MainWindow", "Open DJ mapping"),
            str(self._mapping_start_dir()),
            QCoreApplication.translate("MainWindow", "Supported mapping files (*.xml *.nml *.tsi *.csv);;All files (*)"),
        )
        if not path_str:
            return
        self._load_mapping_from_path(Path(path_str))

    def _on_open_mapping_requested(self, path_str: str) -> None:
        """Controller Setup's "open this XML for editing too" follow-up — the
        same as File -> Open on that path."""
        self._load_mapping_from_path(Path(path_str))
        if self.config is not None:
            self.left_tabs.setCurrentIndex(self._tab_indexes["channel"])

    def _load_mapping_from_path(self, path: Path, software_id: str | None = None) -> None:
        """Open a mapping. With `software_id` (a reopened file whose software
        is already known) the detection prompt is skipped."""
        _LOGGER.info("Opening mapping file %s", path)
        try:
            mapping_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            _LOGGER.exception("Failed to read %s", path)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Failed to open file"), str(exc))
            return
        definitions = software.active_definitions()
        names = [definition.name for definition in definitions]
        detection = detect_software_mapping(mapping_text, path.suffix, _detection_translate)
        detected = detection.best
        detected_index = next(
            (
                index
                for index, definition in enumerate(definitions)
                if detected is not None and definition.plugin_id == detected.plugin_id
            ),
            -1,
        )
        current = detected_index if detected_index >= 0 else next(
            (index for index, definition in enumerate(definitions) if definition.plugin_id == self.software_id),
            0,
        )
        prompt = QCoreApplication.translate("MainWindow", "Mapping software:")
        if detected is not None:
            prompt = QCoreApplication.translate("MainWindow", "Mapping software (detected: {name}, {score}% — {reason}):").format(
                name=detected.name, score=detected.score, reason=detected.reasons[0]
            )
        known = next((definition for definition in definitions if definition.plugin_id == software_id), None)
        if known is not None:
            selected = known
        elif detected is not None and detection.status == "match" and self.preferences.detection_policy == "suggest":
            selected = definitions[detected_index]
        else:
            software_name, accepted = QInputDialog.getItem(
                self,
                QCoreApplication.translate("MainWindow", "Open DJ mapping"),
                prompt,
                names,
                current,
                False,
            )
            if not accepted:
                return
            selected = definitions[names.index(software_name)]
        try:
            self.config = selected.parser(mapping_text)
        except Exception as exc:
            _LOGGER.exception("Failed to parse %s as %s", path, selected.plugin_id)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Failed to open file"), str(exc))
            return
        self.current_path = path
        self.software_id = selected.plugin_id
        self.undo_stack.clear()
        self._load_tree()
        self.issues_table.setRowCount(0)
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "Loaded {count} controls from {name}").format(
                count=len(self.config.controls), name=self.current_path.name
            )
        )
        self._remember_mapping(path)
        _LOGGER.info("Loaded %d control(s) from %s (software=%s)", len(self.config.controls), path, selected.plugin_id)

    def _update_window_title(self) -> None:
        """Reflects the loaded file and its software (issue #121) -- the
        title used to stay a static "DJ MIDI Studio" for the entire session,
        the one-time "which software?" load dialog being the only place that
        ever named it."""
        if self.current_path is None or self.config is None:
            self.setWindowTitle("DJ MIDI Studio")
            return
        definition = software.get_definition(self.software_id)
        self.setWindowTitle(f"DJ MIDI Studio — {self.current_path.name} [{definition.name}]")

    def _on_save(self) -> None:
        if self.config is None:
            return
        if self.current_path is None:
            self._on_save_as()
            return
        definition = software.get_definition(self.software_id)
        self._safe_save(self.current_path, definition)

    def _on_save_as(self) -> None:
        if self.config is None:
            return
        definition = software.get_definition(self.software_id)
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            QCoreApplication.translate("MainWindow", "Export {software} mapping").format(software=definition.name),
            str(self.current_path or self._mapping_start_dir()),
            QCoreApplication.translate("MainWindow", "{software} files ({patterns})").format(
                software=definition.name, patterns=" ".join(f"*{extension}" for extension in definition.extensions)
            ),
        )
        if not path_str:
            return
        target = Path(path_str)
        if self._safe_save(target, definition):
            self.current_path = target
            self._remember_mapping(target)
            self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Saved to {path}").format(path=self.current_path))

    def _safe_save(self, target: Path, definition) -> bool:
        _LOGGER.info("Preparing to save %s as %s", target, definition.plugin_id)
        try:
            plan = prepare_update(
                target,
                definition.exporter(self.config),
                definition.parser,
                summarize=definition.change_summary,
            )
        except (OSError, TypeError, ValueError) as exc:
            _LOGGER.exception("Failed to prepare save for %s", target)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Failed to save mapping"), str(exc))
            return False
        dialog = SafeUpdateDialog(str(target), plan.diff, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            _LOGGER.info("Save to %s cancelled by user at the preview/diff step", target)
            return False
        try:
            plan.apply()
        except OSError as exc:
            _LOGGER.exception("Failed to apply save to %s", target)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Failed to save mapping"), str(exc))
            return False
        self._last_save_plan = plan
        self._refresh_file_actions()
        self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Saved to {path}").format(path=target))
        return True

    def _on_rollback_last_save(self) -> None:
        """Restore the version saved before the mapping's last save: the
        `.bak` every save keeps next to the file, so this also works for a
        save made in an earlier session (it used to need this session's)."""
        if self.current_path is None:
            return
        backup = file_locations.backup_path(self.current_path)
        if not backup.is_file():
            self._refresh_file_actions()
            return
        when = datetime.fromtimestamp(backup.stat().st_mtime, tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        answer = QMessageBox.question(
            self,
            QCoreApplication.translate("MainWindow", "Restore previous version"),
            QCoreApplication.translate("MainWindow", 
                "Replace {name} with the version saved before its last save ({when})?\n\n"
                "Unsaved edits in the app are lost."
            ).format(name=self.current_path.name, when=when),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.copy2(backup, self.current_path)
        except OSError as exc:
            _LOGGER.exception("Failed to restore %s from %s", self.current_path, backup)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Failed to restore the previous version"), str(exc))
            return
        _LOGGER.info("Restored %s from %s", self.current_path, backup)
        self._last_save_plan = None
        restored = self.current_path
        self._load_mapping_from_path(restored)
        self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Restored the previous version of {name}").format(name=restored.name))

    def _on_compare_with_file(self) -> None:
        if self.config is None:
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            QCoreApplication.translate("MainWindow", "Compare with mapping"),
            str(self._mapping_start_dir()),
            QCoreApplication.translate("MainWindow", "Supported mapping files (*.xml *.nml *.tsi *.csv *.bak);;All files (*)"),
        )
        if path_str:
            self._compare_with_path(Path(path_str))

    def _on_compare_with_backup(self) -> None:
        if self.config is None or self.current_path is None:
            return
        backup = file_locations.backup_path(self.current_path)
        if not backup.is_file():
            self._refresh_file_actions()
            return
        self._compare_with_path(backup, name=QCoreApplication.translate("MainWindow", "previous version ({name})").format(name=backup.name))

    def _parse_other_mapping(self, path: Path) -> MidiConfig:
        """Parse a file to compare against: as the software detection says
        when it is sure, else with the open mapping's software (a `.bak` has
        no telling suffix but is always the same format)."""
        text = path.read_text(encoding="utf-8")
        definition = software.get_definition(self.software_id)
        detection = detect_software_mapping(text, path.suffix)
        if detection.best is not None and detection.status == "match":
            definition = next(
                (d for d in software.active_definitions() if d.plugin_id == detection.best.plugin_id),
                definition,
            )
        return definition.parser(text)

    def _compare_with_path(self, path: Path, name: str | None = None) -> MappingDiffDialog | None:
        """Diff `path` (the reference) against the mapping as it is in the
        app now, unsaved edits included, and show the result."""
        assert self.config is not None
        try:
            other = self._parse_other_mapping(path)
        except Exception as exc:
            _LOGGER.exception("Failed to read %s for comparison", path)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Failed to compare"), str(exc))
            return None
        diff = diff_configs(other, self.config, translator("MappingDiff"))
        current = self.current_path.name if self.current_path is not None else QCoreApplication.translate("MainWindow", "the open mapping")
        if self.undo_stack.count() and not self.undo_stack.isClean():
            current += QCoreApplication.translate("MainWindow", " (with unsaved edits)")
        if self._diff_dialog is not None:
            self._diff_dialog.close()
        dialog = MappingDiffDialog(diff, name or path.name, current, self)
        dialog.triggerSelected.connect(self._on_diff_trigger_selected)
        self._diff_dialog = dialog
        dialog.show()
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "Compared with {name}: {count} difference(s)").format(name=path.name, count=len(diff.entries))
        )
        return dialog

    def _on_diff_trigger_selected(self, channel: str, event_type: str, control_no: str) -> None:
        """Like a layout click: select the control in By Channel when the open
        mapping has it (a removed one only exists in the other file) and
        highlight it on the layouts either way."""
        if self.config is not None:
            match = next(
                (
                    c
                    for c in self.config.controls
                    if (c.channel, c.event_type, c.control) == (channel, event_type, control_no)
                ),
                None,
            )
            if match is not None and self._select_control_in_channel_columns(match):
                self.left_tabs.setCurrentIndex(self._tab_indexes["channel"])
        self._update_layout_selection(channel, event_type, control_no)

    def _on_backup_workspace(self) -> Path | None:
        """File → Back Up Workspace (issue #187): one zip of the workspace
        folder, preferences.json and, if asked, the library index."""
        include_library = False
        size = backup.library_db_size()
        if size is not None:
            answer = QMessageBox.question(
                self,
                QCoreApplication.translate("MainWindow", "Back up workspace"),
                QCoreApplication.translate("MainWindow", 
                    "Also include the music library index ({size})?\n\n"
                    "It lists your tracks, categories and playlists -- never the audio files -- "
                    "but it can be large, and a fresh scan rebuilds it."
                ).format(size=_human_size(size)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return None
            include_library = answer == QMessageBox.StandardButton.Yes
        exports = user_paths.subfolder(user_paths.EXPORTS)
        exports.mkdir(parents=True, exist_ok=True)
        path_str, _ = QFileDialog.getSaveFileName(
            self, QCoreApplication.translate("MainWindow", "Back Up Workspace"), str(exports / backup.default_backup_name()), self._backup_filter()
        )
        if not path_str:
            return None
        target = Path(path_str)
        if target.suffix.lower() != ".zip":
            target = target.with_name(target.name + backup.BACKUP_SUFFIX)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            manifest = backup.create_backup(target, include_library=include_library)
        except (OSError, sqlite3.Error) as exc:
            _LOGGER.exception("Workspace backup to %s failed", target)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Backup failed"), str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        _LOGGER.info("Backed up %d files to %s", len(manifest.entries), target)
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "Backed up {count} files to {path}").format(count=len(manifest.entries), path=target), 10_000
        )
        return target

    def _backup_filter(self) -> str:
        return QCoreApplication.translate("MainWindow", "DJ MIDI Studio backup (*.zip);;All files (*)")

    def _confirm_restore(self, plan: backup.RestorePlan) -> bool | None:
        """Ask before a restore writes anything. Returns whether to include
        the library index, or None when cancelled."""
        overwrites = plan.overwrites
        made = (
            QCoreApplication.translate("MainWindow", "Backup made {date} with DJ MIDI Studio {version}.")
            if plan.manifest.created_at
            else QCoreApplication.translate("MainWindow", "Backup made at an unknown date with DJ MIDI Studio {version}.")
        )
        lines = [
            made.format(date=plan.manifest.created_at, version=plan.manifest.app_version),
            QCoreApplication.translate("MainWindow", "{added} file(s) will be added, {overwritten} existing file(s) overwritten.").format(
                added=len(plan.creates), overwritten=len(overwrites)
            ),
        ]
        lines.append(QCoreApplication.translate("MainWindow", "Files that are not in the backup are kept."))
        # Every overwritten file is listed (a message box showed only 8).
        has_library = plan.manifest.has(backup.LIBRARY)
        dialog = ListDialog(
            QCoreApplication.translate("MainWindow", "Restore workspace"),
            QCoreApplication.translate("MainWindow", "Restore this backup over your current files?"),
            [QCoreApplication.translate("MainWindow", "Overwritten file")],
            [str(item.target) for item in overwrites],
            note="\n\n".join(lines),
            accept_text=QCoreApplication.translate("MainWindow", "Restore"),
            parent=self,
            check_text=(
                QCoreApplication.translate("MainWindow", "Also restore the music library index (replaces the current one)")
                if has_library
                else ""
            ),
            checked=has_library and backup.library_db_size() is None,
        )
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        library = dialog.check is not None and dialog.check.isChecked()
        dialog.deleteLater()
        if not accepted:
            return None
        return library

    def _on_restore_workspace(self) -> bool:
        """File → Restore Workspace (issue #187). The restored preferences,
        profiles and library are picked up at the next launch."""
        exports = user_paths.subfolder(user_paths.EXPORTS)
        path_str, _ = QFileDialog.getOpenFileName(
            self, QCoreApplication.translate("MainWindow", "Restore Workspace"), str(exports if exports.is_dir() else Path.home()), self._backup_filter()
        )
        if not path_str:
            return False
        try:
            plan = backup.restore_backup(path_str)
        except (backup.BackupError, OSError) as exc:
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Cannot restore this backup"), str(exc))
            return False
        include_library = self._confirm_restore(plan)
        if include_library is None:
            return False
        if include_library:
            self.music_library_view.close_db()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            backup.restore_backup(path_str, dry_run=False, include_library=include_library)
        except (backup.BackupError, OSError, sqlite3.Error) as exc:
            _LOGGER.exception("Workspace restore from %s failed", path_str)
            QMessageBox.critical(self, QCoreApplication.translate("MainWindow", "Restore failed"), str(exc))
            return False
        finally:
            QApplication.restoreOverrideCursor()
        _LOGGER.info("Restored workspace backup %s", path_str)
        self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Restored {name}").format(name=Path(path_str).name), 10_000)
        answer = QMessageBox.question(
            self,
            QCoreApplication.translate("MainWindow", "Workspace restored"),
            QCoreApplication.translate("MainWindow", 
                "Your files are restored. Restart DJ MIDI Studio to load the restored preferences, "
                "controller profiles and library -- until then, saving preferences would overwrite "
                "the restored ones.\n\nQuit now?"
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.close()
        return True

    def _remember_draft(self, path: str) -> None:
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue(_LAST_DRAFT_SETTINGS_KEY, path)

    def _prepare_reopen_last_files(self) -> None:
        """Pick up where the user left off (issue #175): reopen the last
        mapping with its software -- no detection prompt -- and hand the last
        Controller Setup draft to that tab, which loads it the first time
        it's shown (unless a default file is set in Preferences). Real app
        only: tests and screenshot scripts have no settings."""
        settings = self._layout_settings()
        if settings is None or not self.preferences.reopen_last_files:
            return
        draft = settings.value(_LAST_DRAFT_SETTINGS_KEY, "", type=str)
        if draft and not self.preferences.controller_setup_default_file and Path(draft).is_file():
            self.controller_setup_view.set_default_file(draft)
        mapping = settings.value(_LAST_MAPPING_SETTINGS_KEY, "", type=str)
        software_id = settings.value(_LAST_SOFTWARE_SETTINGS_KEY, "", type=str) or None
        if mapping and Path(mapping).is_file():
            QTimer.singleShot(0, lambda: self._reopen_mapping(Path(mapping), software_id))

    def _reopen_mapping(self, path: Path, software_id: str | None) -> None:
        if self.config is not None:
            return  # something was opened meanwhile
        _LOGGER.info("Reopening the last mapping %s", path)
        self._load_mapping_from_path(path, software_id=software_id)

    def _on_dashboard_file_action(self, action: str) -> None:
        """The Dashboard's "Your files" card buttons."""
        if action == "open":
            self._on_open()
        elif action == "reveal":
            self._on_reveal_mapping()
        elif action == "restore":
            self._on_rollback_last_save()
        elif action == "sync":
            self._on_preferences(tab="Controller sync")
        elif action.startswith("recent:"):
            self._load_mapping_from_path(Path(action.removeprefix("recent:")))

    def _mapping_start_dir(self) -> Path:
        settings = self._layout_settings()
        last_dir = settings.value(_LAST_DIR_SETTINGS_KEY, "", type=str) if settings is not None else ""
        return file_locations.mapping_start_dir(self.software_id, last_dir or None)

    def _remember_mapping(self, path: Path) -> None:
        self._recent_mappings = file_locations.push_recent(self._recent_mappings, path)
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue(_RECENT_SETTINGS_KEY, self._recent_mappings)
            settings.setValue(_LAST_DIR_SETTINGS_KEY, str(path.parent))
            settings.setValue(_LAST_MAPPING_SETTINGS_KEY, str(path))
            settings.setValue(_LAST_SOFTWARE_SETTINGS_KEY, self.software_id)
        self._rebuild_recent_menu()
        self._refresh_file_actions()

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        recents = file_locations.existing_recents(self._recent_mappings)
        for entry in recents:
            action = QAction(f"{Path(entry).name}  —  {Path(entry).parent}", self)
            action.triggered.connect(lambda _checked=False, e=entry: self._load_mapping_from_path(Path(e)))
            self._recent_menu.addAction(action)
        self._recent_menu.setEnabled(bool(recents))

    def _refresh_file_actions(self) -> None:
        """Enable the mapping file actions and refresh the Dashboard's
        "Your files" card from the current state."""
        has_file = self.current_path is not None
        backup = file_locations.backup_path(self.current_path) if has_file else None
        self._rollback_action.setEnabled(backup is not None and backup.is_file())
        self._compare_action.setEnabled(self.config is not None)
        self._compare_backup_action.setEnabled(self.config is not None and backup is not None and backup.is_file())
        self._reveal_action.setEnabled(has_file)
        self._save_snapshot_action.setEnabled(has_file and self.config is not None)
        self._snapshots_action.setEnabled(has_file and self.config is not None)
        self._cheat_sheet_action.setEnabled(self.config is not None)
        self._cheat_sheet_web_action.setEnabled(self.config is not None)
        self._layer_map_action.setEnabled(self.config is not None)
        self.introduction_view.set_files_summary(
            mapping=self.current_path,
            backup=backup if backup is not None and backup.is_file() else None,
            sync_sets=[sync_set.label for sync_set in self.preferences.controller_sync_sets],
            recents=file_locations.existing_recents(self._recent_mappings),
        )

    def save_snapshot(self, name: str | None = None) -> Snapshot | None:
        """File → Save Snapshot…: the mapping as it is in the app, unsaved
        edits included, kept under a name."""
        if self.config is None or self.current_path is None:
            return None
        if name is None:
            name, accepted = QInputDialog.getText(
                self, QCoreApplication.translate("MainWindow", "Save Snapshot"), QCoreApplication.translate("MainWindow", "Name of this version (e.g. before the gig):")
            )
            if not accepted:
                return None
        definition = software.get_definition(self.software_id)
        try:
            snapshot = save_snapshot(self.current_path, name, definition.exporter(self.config), self.software_id)
        except Exception as exc:
            _LOGGER.exception("Failed to save a snapshot of %s", self.current_path)
            QMessageBox.warning(self, QCoreApplication.translate("MainWindow", "Save Snapshot"), str(exc))
            return None
        self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Snapshot “{name}” saved.").format(name=snapshot.name))
        if self._snapshots_dialog is not None:
            self._snapshots_dialog.refresh()
        return snapshot

    def open_snapshots(self) -> SnapshotsDialog | None:
        if self.config is None or self.current_path is None:
            return None
        if self._snapshots_dialog is not None:
            self._snapshots_dialog.close()
        path = self.current_path
        dialog = SnapshotsDialog(
            path.name, lambda: list_snapshots(path), can_restore=self.software_id == "serato", parent=self
        )
        dialog.compareRequested.connect(self._compare_with_snapshot)
        dialog.restoreRequested.connect(self.restore_snapshot)
        dialog.finished.connect(lambda _result: setattr(self, "_snapshots_dialog", None))
        self._snapshots_dialog = dialog
        dialog.show()
        return dialog

    def _compare_with_snapshot(self, snapshot: Snapshot) -> MappingDiffDialog | None:
        if self.config is None:
            return None
        return self._compare_with_path(snapshot.path, name=QCoreApplication.translate("MainWindow", "snapshot “{name}”").format(name=snapshot.name))

    def restore_snapshot(self, snapshot: Snapshot) -> bool:
        """Puts the snapshot's mappings back as one undo step (Serato only:
        the other writers patch their source file and can't take a
        different set of bindings)."""
        if self.config is None or self.software_id != "serato":
            return False
        try:
            restored = software.get_definition("serato").parser(snapshot.path.read_text(encoding="utf-8"))
        except Exception as exc:
            _LOGGER.exception("Failed to read snapshot %s", snapshot.path)
            QMessageBox.warning(self, QCoreApplication.translate("MainWindow", "Restore Snapshot"), str(exc))
            return False
        summary = f"Restore snapshot {snapshot.name}"
        text = QCoreApplication.translate("MainWindow", "Restore snapshot “{name}”").format(name=snapshot.name)
        self.undo_stack.push(
            ReplaceControlsCommand(self.config, restored.controls, summary, text, self._on_structure_changed)
        )
        self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Snapshot “{name}” restored (Edit → Undo takes it back).").format(name=snapshot.name))
        return True

    def open_deck_copy(self) -> DeckCopyDialog | None:
        """Edit → Copy Deck Mappings… (Serato only: the other formats' writers
        can't add bindings)."""
        if self.config is None:
            self.statusBar().showMessage(QCoreApplication.translate("MainWindow", "Copy deck mappings: open a mapping first."))
            return None
        if self.software_id != "serato":
            QMessageBox.information(
                self,
                QCoreApplication.translate("MainWindow", "Copy Deck Mappings"),
                QCoreApplication.translate("MainWindow", "Copying a deck's mappings works on Serato mappings only."),
            )
            return None
        dialog = DeckCopyDialog(self.config, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.accepted.connect(lambda: self.apply_deck_copy(dialog.plan, dialog.source_combo.currentData(),
                                                             dialog.target_combo.currentData()))  # fmt: skip
        dialog.open()
        return dialog

    def apply_deck_copy(self, plan: DeckCopyPlan | None, source: str, target: str) -> None:
        if self.config is None or plan is None or not plan.copied:
            return
        summary = f"Copy deck {source} mappings to deck {target}"
        text = QCoreApplication.translate("MainWindow", "Copy deck {source} mappings to deck {target}").format(source=source, target=target)
        self.undo_stack.push(
            ReplaceControlsCommand(self.config, plan.controls, summary, text, self._on_structure_changed)
        )
        self.statusBar().showMessage(
            QCoreApplication.translate("MainWindow", "Copied deck {source} to deck {target}: {count} control(s).").format(
                source=source, target=target, count=len(plan.copied)
            )
        )

    def _on_reveal_mapping(self) -> None:
        if self.current_path is not None:
            reveal_in_file_manager(self.current_path)
