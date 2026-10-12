"""Duplicates window of the Music Library tab (issue #184).

Shows the groups `djmidi.library.duplicates` found -- exact copies first,
then same artist + title -- one tree row per group, one child per file
(path, format, size, bitrate). Strictly read-only: the only file action is
*Reveal in Finder*; deleting or moving a copy stays the DJ's call, made in
their file manager or DJ software.

Bitrates are read lazily, when a group is expanded: it opens the file's
stream header, cheap per file but not across a whole 85k-track library.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
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
    def __init__(self, groups: list[DuplicateGroup], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicate tracks")
        self.resize(820, 520)
        self.groups = list(groups)
        box = QVBoxLayout(self)

        header = QHBoxLayout()
        exact = sum(1 for group in self.groups if group.tier == TIER_EXACT)
        metadata = len(self.groups) - exact
        self.summary_label = QLabel(
            f"{exact} group(s) of identical files, {metadata} group(s) sharing artist + title. "
            "Nothing is deleted or moved here -- reveal a copy in Finder to deal with it."
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
        box.addWidget(self.tree, 1)
        self._populate()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.reveal_button = QPushButton("Reveal in Finder")
        self.reveal_button.setToolTip("Show the selected file in your file manager.")
        self.reveal_button.clicked.connect(lambda: self._reveal(self.tree.currentItem()))
        buttons.addButton(self.reveal_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self._update_buttons()

    def _populate(self) -> None:
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

    def _update_buttons(self, *_args: object) -> None:
        item = self.tree.currentItem()
        self.reveal_button.setEnabled(item is not None and bool(item.data(0, PATH_ROLE)))

    def _reveal(self, item: QTreeWidgetItem | None) -> None:
        path = item.data(0, PATH_ROLE) if item is not None else None
        if path:
            reveal_in_file_manager(path)


__all__ = ["DuplicatesDialog", "format_size"]
