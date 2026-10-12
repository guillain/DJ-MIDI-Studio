"""Duplicates window of the Music Library tab (issue #184).

Shows the groups `djmidi.library.duplicates` found -- exact copies first,
then same artist + title -- one tree row per group, one child per file
(path, format, size, bitrate). *Reveal in Finder* shows a copy; ticking
copies and clicking *Move ticked to Trash…* emits `discardRequested` with
the ticked paths (issue #208) -- the Music Library view confirms, refuses a
group that would keep no copy, moves them with `QFile.moveToTrash` (never a
hard delete) and calls `remove_paths` back. This dialog never touches a
file itself.

Bitrates are read lazily, when a group is expanded: it opens the file's
stream header, cheap per file but not across a whole 85k-track library.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui import help_texts
from djmidi.gui.file_reveal import reveal_in_file_manager
from djmidi.gui.help_button import help_button
from djmidi.library.duplicates import (
    TIER_EXACT,
    TIER_METADATA,
    DuplicateGroup,
    audio_bitrate,
)

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
_BITRATE_PENDING = "…"

COLUMNS = ("Track / file", "Format", "Size", "Bitrate")
_TIER_TITLES = {
    TIER_EXACT: "Exact copies (identical files)",
    TIER_METADATA: "Same artist + title",
}


def format_size(size: int | None) -> str:
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _file_size(path: str) -> int | None:
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


class DuplicatesDialog(QDialog):
    discardRequested = Signal(list)
    """Ticked copies' paths, deduplicated, in tree order."""

    def __init__(self, groups: list[DuplicateGroup], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicate tracks")
        self.resize(820, 520)
        self.groups = list(groups)
        self._syncing = False
        box = QVBoxLayout(self)

        header = QHBoxLayout()
        exact = sum(1 for group in self.groups if group.tier == TIER_EXACT)
        metadata = len(self.groups) - exact
        self.summary_label = QLabel(
            f"{exact} group(s) of identical files, {metadata} group(s) sharing artist + title. "
            "Tick the copies you don't want and move them to the Trash (at least one copy per group stays)."
        )
        self.summary_label.setWordWrap(True)
        header.addWidget(self.summary_label, 1)
        header.addWidget(help_button(self, *help_texts.LIBRARY_DUPLICATES), 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(list(COLUMNS))
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemDoubleClicked.connect(lambda item, _column: self._reveal(item))
        self.tree.currentItemChanged.connect(self._update_buttons)
        self.tree.itemChanged.connect(self._on_item_changed)
        box.addWidget(self.tree, 1)
        self._populate()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.reveal_button = QPushButton("Reveal in Finder")
        self.reveal_button.setToolTip("Show the selected file in your file manager.")
        self.reveal_button.clicked.connect(lambda: self._reveal(self.tree.currentItem()))
        buttons.addButton(self.reveal_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.trash_button = QPushButton("Move ticked to Trash…")
        self.trash_button.setToolTip(
            "Move the ticked copies to the Trash, after a confirmation. At least one copy of each group must stay."
        )
        self.trash_button.clicked.connect(self._on_trash_clicked)
        buttons.addButton(self.trash_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self._update_buttons()

    def _populate(self) -> None:
        self._syncing = True
        try:
            self._fill_tree()
        finally:
            self._syncing = False

    def _fill_tree(self) -> None:
        for tier in (TIER_EXACT, TIER_METADATA):
            tier_groups = [group for group in self.groups if group.tier == tier]
            tier_item = QTreeWidgetItem([f"{_TIER_TITLES[tier]} — {len(tier_groups)} group(s)"])
            tier_item.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(tier_item)
            for group in tier_groups:
                label = (
                    f"{len(group.paths)} identical files"
                    if tier == TIER_EXACT
                    else f"{group.label or group.key} ({len(group.paths)} files)"
                )
                group_item = QTreeWidgetItem([label, "", format_size(group.size), ""])
                tier_item.addChild(group_item)
                for path in group.paths:
                    size = group.size if group.size is not None else _file_size(path)
                    child = QTreeWidgetItem(
                        [path, Path(path).suffix.lstrip(".").upper(), format_size(size), _BITRATE_PENDING]
                    )
                    child.setData(0, PATH_ROLE, path)
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                    child.setToolTip(0, path)
                    group_item.addChild(child)
            tier_item.setExpanded(True)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            path = child.data(0, PATH_ROLE)
            if path and child.text(3) == _BITRATE_PENDING:
                bitrate = audio_bitrate(path)
                child.setText(3, f"{round(bitrate / 1000)} kbps" if bitrate else "")

    def file_items(self) -> list[QTreeWidgetItem]:
        items = []
        for top in range(self.tree.topLevelItemCount()):
            tier_item = self.tree.topLevelItem(top)
            for group_index in range(tier_item.childCount()):
                group_item = tier_item.child(group_index)
                items.extend(group_item.child(index) for index in range(group_item.childCount()))
        return items

    def checked_paths(self) -> list[str]:
        """Ticked copies, each once (a file can sit in two groups)."""
        ticked = [
            item.data(0, PATH_ROLE) for item in self.file_items() if item.checkState(0) == Qt.CheckState.Checked
        ]
        return list(dict.fromkeys(ticked))

    def set_checked(self, path: str, checked: bool) -> None:
        for item in self.file_items():
            if item.data(0, PATH_ROLE) == path:
                item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, PATH_ROLE)
        if column != 0 or not path or self._syncing:
            return
        # The same file may be listed in an exact group and a metadata one:
        # keep its tick boxes in step.
        self._syncing = True
        try:
            self.set_checked(path, item.checkState(0) == Qt.CheckState.Checked)
        finally:
            self._syncing = False
        self._update_buttons()

    def _on_trash_clicked(self) -> None:
        paths = self.checked_paths()
        if paths:
            self.discardRequested.emit(paths)

    def remove_paths(self, paths: list[str]) -> None:
        """Drop moved copies from the tree; a group left with one file goes."""
        gone = set(paths)
        self.groups = [
            replace(group, paths=kept)
            for group in self.groups
            if len(kept := tuple(path for path in group.paths if path not in gone)) > 1
        ]
        self.tree.clear()
        self._populate()
        self._update_buttons()

    def _update_buttons(self, *_args: object) -> None:
        item = self.tree.currentItem()
        self.reveal_button.setEnabled(item is not None and bool(item.data(0, PATH_ROLE)))
        self.trash_button.setEnabled(bool(self.checked_paths()))

    def _reveal(self, item: QTreeWidgetItem | None) -> None:
        path = item.data(0, PATH_ROLE) if item is not None else None
        if path:
            reveal_in_file_manager(path)


__all__ = ["DuplicatesDialog", "format_size"]
