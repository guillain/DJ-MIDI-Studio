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

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
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
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.library import change_log
from djmidi.library.db import ChangeItem, ChangeRecord, LibraryDB

KIND_LABELS = {
    change_log.KIND_TAGS: "Tags",
    change_log.KIND_TRASH: "Moved to Trash",
    change_log.KIND_RESTORE: "Restored from Trash",
    change_log.KIND_RENAME: "Rename",
    change_log.KIND_COVER: "Cover art",
}

# How many entries the window lists (the log itself keeps MAX_ENTRIES).
_LIST_LIMIT = 500


def _when(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _value(value: object) -> str:
    if value is None or value == "":
        return "(empty)"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _cover(state: dict[str, object]) -> str:
    """``image/jpeg, 120 KB`` for a logged cover, ``(none)`` when absent."""
    if not state.get("sha256"):
        return "(none)"
    size = state.get("size")
    kilobytes = f", {max(1, round(size / 1024))} KB" if isinstance(size, int) else ""
    return f"{state.get('mime') or 'image'}{kilobytes}"


def describe_item(kind: str, item: ChangeItem) -> str:
    """One line saying what changed for this file."""
    if kind == change_log.KIND_TRASH:
        where = item.after.get("trash_path") or "the Trash"
        return f"moved to {where} (kept {item.before.get('kept', '?')})"
    if kind == change_log.KIND_RESTORE:
        return f"put back from {item.before.get('trash_path', 'the Trash')}"
    if kind == change_log.KIND_RENAME:
        return f"{item.before.get('path', '?')} → {item.after.get('path', '?')}"
    if kind == change_log.KIND_COVER:
        return f"front cover: {_cover(item.before)} → {_cover(item.after)}"
    names = sorted(set(item.before) | set(item.after))
    return "; ".join(f"{name}: {_value(item.before.get(name))} → {_value(item.after.get(name))}" for name in names)


def _status(change: ChangeRecord) -> str:
    if change.reverted_at is not None:
        return f"Reverted {_when(change.reverted_at)}"
    return "" if change_log.is_revertible(change) else "Not revertible"


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
                    KIND_LABELS.get(change.kind, change.kind),
                    change.summary,
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
            ).format(id=change.id, summary=change.summary, count=change.item_count),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.revert(change.id)

    def revert(self, change_id: int) -> change_log.RevertResult:
        """Revert entry `change_id` (no confirmation) and report the outcome."""
        result = change_log.revert_change(self._db, change_id, self._context)
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


__all__ = ["KIND_LABELS", "ChangeHistoryDialog", "describe_item"]
