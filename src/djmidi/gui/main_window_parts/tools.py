"""MainWindow, part: Command palette, cheat sheet export and Layer Map.

A mixin of `djmidi.gui.main_window.MainWindow` (issue #429); its strings keep the
"MainWindow" translation context."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    Qt,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QMessageBox,
)

from djmidi import (
    catalog,
    user_paths,
)
from djmidi.command_palette import (
    KIND_ACTION,
    KIND_FUNCTION,
    KIND_TAB,
    KIND_TRACK,
    PaletteEntry,
    PaletteIndex,
    track_entry,
)
from djmidi.gui import cheat_sheet
from djmidi.gui.cheat_sheet_dialog import CheatSheetExportDialog
from djmidi.gui.cheat_sheet_html import write_cheat_sheet_html
from djmidi.gui.cheat_sheet_pdf import write_cheat_sheet_pdf
from djmidi.gui.command_palette import CommandPaletteDialog, menu_entries
from djmidi.gui.layer_map_dialog import LayerMapDialog
from djmidi.gui.translation import translator


class ToolsMixin:
    def _palette_index(self) -> PaletteIndex:
        entries = menu_entries(self.menuBar(), skip={self._command_palette_action})
        for index in range(self.left_tabs.count()):
            entries.append(
                PaletteEntry(KIND_TAB, self.left_tabs.tabText(index), detail="Go to tab", payload=index)
            )
        functions = self.function_search_view._index if self.config is not None else []
        return PaletteIndex(entries, functions, self._palette_track_entries())

    def _palette_track_entries(self) -> list[PaletteEntry]:
        """The Music Library's rows as palette entries -- only once the tab
        has opened its index this session (the palette never opens the DB
        itself), rebuilt only when the rows were reloaded."""
        library = self.music_library_view
        if library._db is None:
            return []
        rows = library.table_model._rows
        cached = getattr(self, "_palette_track_cache", None)
        if cached is not None and cached[0] is rows:
            return cached[1]
        entries = []
        for row in rows:
            metadata = row.metadata
            facts = [f"{row.bpm:g} BPM" if row.bpm else "", row.camelot_key or ""]
            detail = " · ".join([fact for fact in facts if fact] + [row.path])
            entries.append(
                track_entry(
                    row.path,
                    metadata.title if metadata else None,
                    metadata.artist if metadata else None,
                    metadata.album if metadata else None,
                    detail=detail,
                    payload=row.path,
                )
            )
        self._palette_track_cache = (rows, entries)
        return entries

    def open_command_palette(self, query: str = "") -> CommandPaletteDialog:
        """Show the palette (window-modal, non-blocking: `open()`, not
        `exec()`, so tests can drive it) and run what the user picks."""
        dialog = CommandPaletteDialog(self._palette_index(), self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.entryChosen.connect(self._run_palette_entry)
        if query:
            dialog.set_query(query)
        self._command_palette = dialog
        dialog.open()
        dialog.search_field.setFocus()
        return dialog

    def _run_palette_entry(self, entry: PaletteEntry) -> None:
        if entry.kind == KIND_ACTION:
            entry.payload.trigger()
        elif entry.kind == KIND_TAB:
            self.left_tabs.setCurrentIndex(entry.payload)
        elif entry.kind == KIND_FUNCTION:
            self._on_function_result_selected(entry.payload)
        elif entry.kind == KIND_TRACK:
            self.left_tabs.setCurrentIndex(self._tab_indexes["library"])
            library = self.music_library_view
            # A filter may hide the track: clear them rather than miss it.
            if not library.select_path(entry.payload):
                library.reset_filters()
                library.select_path(entry.payload)
            library.table.setFocus()

    def _run_in_tab(self, tab_key: str, handler) -> None:
        """Show the tab an action belongs to, then run it, so a File menu
        entry lands the user where its result appears."""
        self.left_tabs.setCurrentIndex(self._tab_indexes[tab_key])
        handler()

    def _on_export_cheat_sheet(
        self, controllers: list[str] | None = None, path: Path | None = None, web: bool = False
    ) -> Path | None:
        """File -> Export -> Cheat Sheet (PDF) (issue #182), or with `web`
        the interactive web page (phase 6 item 6). `controllers` and `path`
        skip the dialogs (tests)."""
        if self.config is None:
            QMessageBox.information(self, QCoreApplication.translate("MainWindow", "Cheat Sheet"), QCoreApplication.translate("MainWindow", "Open a mapping first."))
            return None
        if controllers is None:
            candidates = cheat_sheet.candidate_controllers(self.config)
            if not candidates:
                QMessageBox.information(
                    self,
                    QCoreApplication.translate("MainWindow", "Cheat Sheet"),
                    QCoreApplication.translate("MainWindow", "No registered controller recognizes the triggers of this mapping."),
                )
                return None
            names = [name for name, _count in candidates]
            dialog = CheatSheetExportDialog(candidates, self._cheat_sheet_preselection(names), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            controllers = dialog.selected_controllers()
        if path is None:
            stem = self.current_path.stem if self.current_path is not None else "mapping"
            path_str, _ = QFileDialog.getSaveFileName(
                self,
                QCoreApplication.translate("MainWindow", "Export cheat sheet"),
                str(user_paths.subfolder(user_paths.EXPORTS) / f"{stem}-cheat-sheet.{'html' if web else 'pdf'}"),
                QCoreApplication.translate("MainWindow", "Web pages (*.html)") if web else QCoreApplication.translate("MainWindow", "PDF files (*.pdf)"),
            )
            if not path_str:
                return None
            path = Path(path_str)
        sheets = cheat_sheet.build_sheets(
            self.config, controllers, translator("FunctionNames"), translator("CheatSheet")
        )
        source = self.current_path.name if self.current_path is not None else None
        try:
            if web:
                size = write_cheat_sheet_html(path, sheets, source)
            else:
                pages = write_cheat_sheet_pdf(path, sheets, source)
        except OSError as exc:
            QMessageBox.warning(
                self, QCoreApplication.translate("MainWindow", "Cheat Sheet"), QCoreApplication.translate("MainWindow", "Could not write {path}:\n{error}").format(path=path, error=exc)
            )
            return None
        if web:
            self.statusBar().showMessage(
                QCoreApplication.translate("MainWindow", "Cheat sheet web page exported: {path} ({size} KB, opens offline on any device)").format(
                    path=path, size=max(1, size // 1024)
                )
            )
        else:
            self.statusBar().showMessage(
                QCoreApplication.translate("MainWindow", "Cheat sheet exported: {path} ({count} page(s))").format(path=path, count=pages)
            )
        return path

    def _on_show_layer_map(self) -> LayerMapDialog | None:
        """View -> Layer Map (issue #253): a non-modal, read-only overview
        of every layer of one controller. The controllers recognizing the
        mapping come first (most triggers first), then every other one, so a
        DJ can also look for room on a controller the mapping doesn't use
        yet. Returns the dialog (tests)."""
        if self.config is None:
            QMessageBox.information(self, QCoreApplication.translate("MainWindow", "Layer Map"), QCoreApplication.translate("MainWindow", "Open a mapping first."))
            return None
        candidates = cheat_sheet.candidate_controllers(self.config)
        known = {name for name, _count in candidates}
        controllers = candidates + [(name, 0) for name in catalog.CONTROLLER_NAMES if name not in known]
        preselected = self._cheat_sheet_preselection([name for name, _count in candidates]) if candidates else set()
        first = next((name for name, _count in candidates if name in preselected), None)
        if self._layer_map_dialog is not None:
            self._layer_map_dialog.close()
            self._layer_map_dialog.deleteLater()
        dialog = LayerMapDialog(lambda: self.config, controllers, first, self)
        self._layer_map_dialog = dialog
        dialog.show()
        return dialog
