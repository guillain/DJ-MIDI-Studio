"""Change history window of the Music Library tab (issue #261).

Lists the persistent change log `djmidi.library.change_log` keeps in the
library index (newest first: when, what, how many files, status) and, for
the selected entry, every file with its before -> after state. *Revert…*
undoes the selected entry after a confirmation, through
`change_log.revert_change`: only files still in the state this app left
them in are touched, and the result (reverted / already reverted / left
alone, with the reason) is shown. Survives restarts, unlike the tab's
session-only undo stack.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.library import change_log
from djmidi.library.db import ChangeItem, ChangeRecord, LibraryDB

_CONTEXT = "ChangeHistoryDialog"

KIND_LABELS = {
    change_log.KIND_TAGS: QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Tags"),
    change_log.KIND_TRASH: QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Moved to Trash"),
    change_log.KIND_RESTORE: QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Restored from Trash"),
    change_log.KIND_RENAME: QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Rename"),
    change_log.KIND_COVER: QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Cover art"),
}

# How many entries the window lists (the log itself keeps MAX_ENTRIES).
_LIST_LIMIT = 500

# Entry summaries are stored in English when the change is made (issue #319):
# the ones this app writes are recognized and shown in the interface
# language; anything else (another writer's own text) is shown as stored.
_SUMMARY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Undo: (?P<summary>.+)"), QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Undo: {summary}")),
    (re.compile(r"Revert #(?P<id>\d+): (?P<summary>.+)"), QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Revert #{id}: {summary}")),
    (
        re.compile(r"Edit (?P<fields>.+?) of (?P<count>\d+) track(?:s|\(s\))"),
        QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Edit {fields} of {count} track(s)"),
    ),
    (re.compile(r"Edit (?P<fields>.+?) of (?P<name>.+)"), QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Edit {fields} of {name}")),
    (re.compile(r"Set cover of (?P<name>.+)"), QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Set cover of {name}")),
    (re.compile(r"Remove cover of (?P<name>.+)"), QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Remove cover of {name}")),
    (re.compile(r"Rename (?P<count>\d+) file\(s\)"), QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Rename {count} file(s)")),
    (
        re.compile(r"Move (?P<count>\d+) duplicate\(s\) to the Trash"),
        QT_TRANSLATE_NOOP("ChangeHistoryDialog", "Move {count} duplicate(s) to the Trash"),
    ),
)


def _tr(text: str) -> str:
    return QCoreApplication.translate("ChangeHistoryDialog", text)


def _field(name: str) -> str:
    """A tag field as the Music Library's columns name it (``bpm`` -> ``BPM``)."""
    return "BPM" if name == "bpm" else QCoreApplication.translate("MusicLibraryView", name.capitalize())


def describe_summary(summary: str) -> str:
    """An entry's stored English summary in the interface language."""
    for pattern, template in _SUMMARY_PATTERNS:
        match = pattern.fullmatch(summary)
        if match is None:
            continue
        values = match.groupdict()
        if "summary" in values:
            values["summary"] = describe_summary(values["summary"])
        if "fields" in values:
            values["fields"] = ", ".join(_field(name) for name in values["fields"].split(", "))
        return _tr(template).format(**values)
    return summary


def _when(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _value(value: object) -> str:
    if value is None or value == "":
        return QCoreApplication.translate("ChangeHistoryDialog", "(empty)")
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _cover(state: dict[str, object]) -> str:
    """``image/jpeg, 120 KB`` for a logged cover, ``(none)`` when absent."""
    if not state.get("sha256"):
        return QCoreApplication.translate("ChangeHistoryDialog", "(none)")
    size = state.get("size")
    kilobytes = ""
    if isinstance(size, int):
        kilobytes = QCoreApplication.translate("ChangeHistoryDialog", ", {size} KB").format(
            size=max(1, round(size / 1024))
        )
    mime = state.get("mime") or QCoreApplication.translate("ChangeHistoryDialog", "image")
    return f"{mime}{kilobytes}"


def _trash() -> str:
    return QCoreApplication.translate("ChangeHistoryDialog", "the Trash")


def describe_item(kind: str, item: ChangeItem) -> str:
    """One line saying what changed for this file, in the interface language."""
    if kind == change_log.KIND_TRASH:
        return QCoreApplication.translate("ChangeHistoryDialog", "moved to {where} (kept {kept})").format(
            where=item.after.get("trash_path") or _trash(), kept=item.before.get("kept", "?")
        )
    if kind == change_log.KIND_RESTORE:
        return QCoreApplication.translate("ChangeHistoryDialog", "put back from {where}").format(
            where=item.before.get("trash_path") or _trash()
        )
    if kind == change_log.KIND_RENAME:
        return f"{item.before.get('path', '?')} → {item.after.get('path', '?')}"
    if kind == change_log.KIND_COVER:
        return QCoreApplication.translate("ChangeHistoryDialog", "front cover: {before} → {after}").format(
            before=_cover(item.before), after=_cover(item.after)
        )
    names = sorted(set(item.before) | set(item.after))
    template = QCoreApplication.translate("ChangeHistoryDialog", "{field}: {before} → {after}")
    return "; ".join(
        template.format(field=_field(name), before=_value(item.before.get(name)), after=_value(item.after.get(name)))
        for name in names
    )


def _status(change: ChangeRecord) -> str:
    if change.reverted_at is not None:
        return QCoreApplication.translate("ChangeHistoryDialog", "Reverted {when}").format(
            when=_when(change.reverted_at)
        )
    if change_log.is_revertible(change):
        return ""
    return QCoreApplication.translate("ChangeHistoryDialog", "Not revertible")


class ChangeHistoryDialog(QDialog):
    """Persistent change log: inspect entries, revert one."""

    reverted = Signal(list)
    """Paths of the files a revert touched (the tab re-reads their tags)."""

    def __init__(self, db: LibraryDB, parent: QWidget | None = None, context: change_log.RevertContext | None = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Change history"))
        fit_to_screen(self, 900, 560)
        self._db = db
        self._context = context
        self._changes: list[ChangeRecord] = []

        intro = QLabel(
            self.tr(
                "Every tag, cover art and rename write and Trash move this app made to your files, "
                "newest first. Revert puts a file back only while it still holds what this app wrote."
            )
        )
        intro.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(intro, 1)
        top.addWidget(help_button(self, *help_texts.LIBRARY_CHANGE_HISTORY), 0, Qt.AlignmentFlag.AlignTop)

        self.entries = QTreeWidget()
        self.entries.setRootIsDecorated(False)
        self.entries.setHeaderLabels(
            ["#", self.tr("When"), self.tr("Change"), self.tr("Summary"), self.tr("Files"), self.tr("Status")]
        )
        self.entries.currentItemChanged.connect(self._on_entry_changed)
        self.items = QTreeWidget()
        self.items.setRootIsDecorated(False)
        self.items.setHeaderLabels([self.tr("File"), self.tr("Change")])
        usable_minimum(self.entries, 420, 120)
        usable_minimum(self.items, 420, 90)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.entries)
        splitter.addWidget(self.items)

        self.revert_button = QPushButton(self.tr("Revert…"))
        self.revert_button.setToolTip(self.tr("Undo the selected change on the files it touched."))
        self.revert_button.clicked.connect(self._on_revert_clicked)
        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.refresh_button.clicked.connect(self.refresh)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.addButton(self.revert_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.refresh_button, QDialogButtonBox.ButtonRole.ActionRole)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addWidget(buttons)
        keep_wrapped_text_visible(self)
        self.refresh()

    def refresh(self) -> None:
        current = self.current_change()
        self._changes = self._db.list_changes(limit=_LIST_LIMIT)
        self.entries.clear()
        for change in self._changes:
            item = QTreeWidgetItem(
                [
                    str(change.id),
                    _when(change.created_at),
                    _tr(KIND_LABELS[change.kind]) if change.kind in KIND_LABELS else change.kind,
                    describe_summary(change.summary),
                    str(change.item_count),
                    _status(change),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, change.id)
            self.entries.addTopLevelItem(item)
        for column in range(self.entries.columnCount()):
            self.entries.resizeColumnToContents(column)
        if self._changes:
            index = next((i for i, c in enumerate(self._changes) if current and c.id == current.id), 0)
            self.entries.setCurrentItem(self.entries.topLevelItem(index))
        else:
            self.items.clear()
        self._update_buttons()

    def current_change(self) -> ChangeRecord | None:
        item = self.entries.currentItem()
        if item is None:
            return None
        change_id = item.data(0, Qt.ItemDataRole.UserRole)
        return next((c for c in self._changes if c.id == change_id), None)

    def _on_entry_changed(self, *_args: object) -> None:
        self.items.clear()
        summary = self.current_change()
        change = self._db.get_change(summary.id) if summary is not None else None
        if change is not None:
            for entry in change.items:
                row = QTreeWidgetItem([entry.path, describe_item(change.kind, entry)])
                row.setToolTip(0, entry.path)
                self.items.addTopLevelItem(row)
            self.items.resizeColumnToContents(0)
        self._update_buttons()

    def _update_buttons(self) -> None:
        change = self.current_change()
        self.revert_button.setEnabled(change is not None and change_log.is_revertible(change))

    def _on_revert_clicked(self) -> None:
        change = self.current_change()
        if change is None or not change_log.is_revertible(change):
            return
        answer = QMessageBox.question(
            self,
            self.tr("Revert change"),
            self.tr(
                "Revert #{id} ({summary}) on {count} file(s)?\n\n"
                "Files changed again since are left alone. The revert is itself logged here."
            ).format(id=change.id, summary=describe_summary(change.summary), count=change.item_count),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.revert(change.id)

    def revert(self, change_id: int) -> change_log.RevertResult:
        """Revert entry `change_id` (no confirmation) and report the outcome."""
        result = change_log.revert_change(self._db, change_id, self._context, translate=translator(_CONTEXT))
        self.refresh()
        if result.reverted:
            self.reverted.emit(list(result.reverted))
        lines = [self.tr("Reverted {count} file(s).").format(count=len(result.reverted))]
        if result.already:
            lines.append(self.tr("{count} already held their previous state.").format(count=len(result.already)))
        if result.failed:
            lines.append(self.tr("{count} left alone:").format(count=len(result.failed)))
            lines += [f"• {Path(path).name}: {reason}" for path, reason in result.failed[:20]]
            if len(result.failed) > 20:
                lines.append(self.tr("… and {count} more").format(count=len(result.failed) - 20))
            QMessageBox.warning(self, self.tr("Revert change"), "\n".join(lines))
        else:
            QMessageBox.information(self, self.tr("Revert change"), "\n".join(lines))
        return result


__all__ = ["KIND_LABELS", "ChangeHistoryDialog", "describe_item", "describe_summary"]
