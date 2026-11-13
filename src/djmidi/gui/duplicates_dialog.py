"""Duplicates window of the Music Library tab (issue #184).

Shows the groups `djmidi.library.duplicates` found -- exact copies first,
then same artist + title -- one tree row per group, one child per file
(path, format, size, bitrate). *Reveal in Finder* shows a copy; ticking
copies and clicking *Move ticked to Trash…* emits `discardRequested` with
the ticked paths (issue #208) -- the Music Library view confirms, refuses a
group that would keep no copy, moves them with `QFile.moveToTrash` (never a
hard delete) and calls `remove_paths` back. This dialog never touches a
file itself.

A third section, *Other versions of the same song* (issue #257), lists
`TIER_VERSIONS` groups -- radio edit / extended / remaster of one song --
as suggestions only: each file shows its own title, can be revealed, but
has no tick box, so it can never be moved to the Trash from here.

Bitrates are read lazily, when a group is expanded: it opens the file's
stream header, cheap per file but not across a whole 85k-track library.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt, Signal
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
from djmidi.gui.action_groups import FlowLayout
from djmidi.gui.file_reveal import reveal_in_file_manager
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.library.duplicates import (
    TIER_EXACT,
    TIER_METADATA,
    TIER_VERSIONS,
    DuplicateGroup,
    audio_bitrate,
)
from djmidi.library.keep_copy import (
    CopyFacts,
    KeepSuggestion,
    read_copy_facts,
    suggest_keep,
)

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
_BITRATE_PENDING = "…"
_keep_translate = translator("KeepCopy")

COLUMNS = (
    QT_TRANSLATE_NOOP("DuplicatesDialog", "Track / file"),
    QT_TRANSLATE_NOOP("DuplicatesDialog", "Format"),
    QT_TRANSLATE_NOOP("DuplicatesDialog", "Size"),
    QT_TRANSLATE_NOOP("DuplicatesDialog", "Bitrate"),
    QT_TRANSLATE_NOOP("DuplicatesDialog", "Suggestion"),
)
SUGGESTION_COLUMN = 4
KEEP_ROLE = Qt.ItemDataRole.UserRole + 2  # on a group item: the suggested path
_TIER_TITLES = {
    TIER_EXACT: QT_TRANSLATE_NOOP("DuplicatesDialog", "Exact copies (identical files)"),
    TIER_METADATA: QT_TRANSLATE_NOOP("DuplicatesDialog", "Same artist + title"),
    TIER_VERSIONS: QT_TRANSLATE_NOOP("DuplicatesDialog", "Other versions of the same song (suggestions, not duplicates)"),
}


_SIZE_UNITS = (
    QT_TRANSLATE_NOOP("DuplicatesDialog", "B"),
    QT_TRANSLATE_NOOP("DuplicatesDialog", "KB"),
    QT_TRANSLATE_NOOP("DuplicatesDialog", "MB"),
    QT_TRANSLATE_NOOP("DuplicatesDialog", "GB"),
)


def format_size(size: int | None) -> str:
    if size is None:
        return ""
    units = [QCoreApplication.translate("DuplicatesDialog", unit) for unit in _SIZE_UNITS]
    value = float(size)
    for index, unit in enumerate(units[:-1]):
        if value < 1024:
            return f"{value:.0f} {unit}" if index == 0 else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {units[-1]}"


def _file_size(path: str) -> int | None:
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


class DuplicatesDialog(QDialog):
    discardRequested = Signal(list)
    """Ticked copies' paths, deduplicated, in tree order."""
    mergeRequested = Signal(str, list)
    """The copy to keep and the group's other copies (issue #458)."""
    djPlaylistsRequested = Signal(str, list)
    """Same, for Serato crates / Traktor playlists (issue #458)."""

    def __init__(
        self,
        groups: list[DuplicateGroup],
        parent: QWidget | None = None,
        roots: Sequence[str] = (),
        facts_reader: Callable[[str, Sequence[str]], CopyFacts] = read_copy_facts,
    ) -> None:
        super().__init__(parent)
        self._roots = tuple(roots)
        self._facts_reader = facts_reader
        self.setWindowTitle(self.tr("Duplicate tracks"))
        fit_to_screen(self, 820, 520)
        self.groups = list(groups)
        self._syncing = False
        box = QVBoxLayout(self)

        header = QHBoxLayout()
        exact = sum(1 for group in self.groups if group.tier == TIER_EXACT)
        metadata = sum(1 for group in self.groups if group.tier == TIER_METADATA)
        versions = sum(1 for group in self.groups if group.tier == TIER_VERSIONS)
        self.summary_label = QLabel(
            self.tr(
                "{exact} group(s) of identical files, {metadata} group(s) sharing artist + title, "
                "{versions} song(s) with several versions. "
                "Tick the copies you don't want and move them to the Trash (at least one copy per group stays). "
                "Other versions are suggestions to review only."
            ).format(exact=exact, metadata=metadata, versions=versions)
        )
        self.summary_label.setWordWrap(True)
        header.addWidget(self.summary_label, 1)
        header.addWidget(help_button(self, *help_texts.LIBRARY_DUPLICATES), 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(header)

        self.tree = QTreeWidget()
        usable_minimum(self.tree, 240, 120)  # a few rows even in the smallest window
        self.tree.setHeaderLabels([QCoreApplication.translate("DuplicatesDialog", column) for column in COLUMNS])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemDoubleClicked.connect(lambda item, _column: self._reveal(item))
        self.tree.currentItemChanged.connect(self._update_buttons)
        self.tree.itemChanged.connect(self._on_item_changed)
        box.addWidget(self.tree, 1)
        self._populate()

        # The actions wrap onto more lines in a narrow window (a button box
        # would make the dialog wider than a small screen).
        actions = QWidget()
        actions_flow = FlowLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.reveal_button = QPushButton(self.tr("Reveal in Finder"))
        self.reveal_button.setToolTip(self.tr("Show the selected file in your file manager."))
        self.reveal_button.clicked.connect(lambda: self._reveal(self.tree.currentItem()))
        actions_flow.addWidget(self.reveal_button)
        self.suggest_button = QPushButton(self.tr("Tick all but the suggested copies"))
        self.suggest_button.setToolTip(
            self.tr(
                "Suggest the copy to keep in every group (audio quality, DJ software data, location, tags) and tick "
                "the others. A copy holding DJ software data the kept one lacks is never ticked."
            )
        )
        self.suggest_button.clicked.connect(self.tick_all_but_suggested)
        actions_flow.addWidget(self.suggest_button)
        self.merge_button = QPushButton(self.tr("Merge onto the kept copy…"))
        self.merge_button.setToolTip(
            self.tr(
                "Copy the tags the kept copy lacks from the other copies of the group and point this app's "
                "playlists at it. The kept copy is the selected file, else the suggested one. Nothing is discarded."
            )
        )
        self.merge_button.clicked.connect(self._on_merge_clicked)
        actions_flow.addWidget(self.merge_button)
        self.dj_playlists_button = QPushButton(self.tr("DJ software playlists…"))
        self.dj_playlists_button.setToolTip(
            self.tr(
                "Point Serato crates or Traktor playlists at the kept copy instead of the group's other copies: "
                "a preview first, a backup of every file, refused while that software is running."
            )
        )
        self.dj_playlists_button.clicked.connect(self._on_dj_playlists_clicked)
        actions_flow.addWidget(self.dj_playlists_button)
        self.trash_button = QPushButton(self.tr("Move ticked to Trash…"))
        self.trash_button.setToolTip(
            self.tr(
                "Move the ticked copies to the Trash, after a confirmation. At least one copy of each group must stay."
            )
        )
        self.trash_button.clicked.connect(self._on_trash_clicked)
        actions_flow.addWidget(self.trash_button)
        buttons.rejected.connect(self.reject)
        box.addWidget(actions)
        box.addWidget(buttons)
        self._update_buttons()
        keep_wrapped_text_visible(self)

    def _populate(self) -> None:
        self._syncing = True
        try:
            self._fill_tree()
        finally:
            self._syncing = False

    def _fill_tree(self) -> None:
        for tier in (TIER_EXACT, TIER_METADATA, TIER_VERSIONS):
            tier_groups = [group for group in self.groups if group.tier == tier]
            tier_item = QTreeWidgetItem(
                [
                    self.tr("{title} — {count} group(s)").format(
                        title=QCoreApplication.translate("DuplicatesDialog", _TIER_TITLES[tier]), count=len(tier_groups)
                    )
                ]
            )
            self.tree.addTopLevelItem(tier_item)
            # Spanning only takes once the item is in the tree: before, the
            # tier title was cut at the first column's width.
            tier_item.setFirstColumnSpanned(True)
            for group in tier_groups:
                if tier == TIER_EXACT:
                    label = self.tr("{count} identical files").format(count=len(group.paths))
                elif tier == TIER_VERSIONS:
                    label = self.tr("{name} ({count} versions)").format(
                        name=group.label or group.key, count=len(group.paths)
                    )
                else:
                    label = self.tr("{name} ({count} files)").format(name=group.label or group.key, count=len(group.paths))
                group_item = QTreeWidgetItem([label, "", format_size(group.size), "", ""])
                tier_item.addChild(group_item)
                for index, path in enumerate(group.paths):
                    size = group.size if group.size is not None else _file_size(path)
                    text = path
                    if tier == TIER_VERSIONS and index < len(group.variants):
                        text = f"{group.variants[index]} — {path}"
                    child = QTreeWidgetItem(
                        [text, Path(path).suffix.lstrip(".").upper(), format_size(size), _BITRATE_PENDING, ""]
                    )
                    child.setData(0, PATH_ROLE, path)
                    if tier == TIER_VERSIONS:
                        # Versions are suggestions: never tickable for the Trash.
                        child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    else:
                        child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        child.setCheckState(0, Qt.CheckState.Unchecked)
                    child.setToolTip(0, path)
                    group_item.addChild(child)
            tier_item.setExpanded(True)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        if self._group_children(item) and not self._is_versions(item):
            self.suggest(item)
            return
        for index in range(item.childCount()):
            child = item.child(index)
            path = child.data(0, PATH_ROLE)
            if path and child.text(3) == _BITRATE_PENDING:
                bitrate = audio_bitrate(path)
                child.setText(3, f"{round(bitrate / 1000)} kbps" if bitrate else "")

    @staticmethod
    def _group_children(item: QTreeWidgetItem) -> list[QTreeWidgetItem]:
        children = [item.child(index) for index in range(item.childCount())]
        return children if children and all(child.data(0, PATH_ROLE) for child in children) else []

    @staticmethod
    def _is_versions(group_item: QTreeWidgetItem) -> bool:
        child = group_item.child(0)
        return child is not None and not child.flags() & Qt.ItemFlag.ItemIsUserCheckable

    def group_items(self) -> list[QTreeWidgetItem]:
        """Group items whose copies can be discarded (not the versions tier)."""
        result = []
        for top in range(self.tree.topLevelItemCount()):
            tier_item = self.tree.topLevelItem(top)
            result.extend(
                group
                for group in (tier_item.child(index) for index in range(tier_item.childCount()))
                if self._group_children(group) and not self._is_versions(group)
            )
        return result

    def suggest(self, group_item: QTreeWidgetItem) -> KeepSuggestion | None:
        """Reads the group's copies once and shows which one to keep and why
        (issue #458); a copy whose DJ software data the kept one lacks is
        flagged."""
        children = self._group_children(group_item)
        facts = [self._facts_reader(child.data(0, PATH_ROLE), self._roots) for child in children]
        suggestion = suggest_keep(facts, _keep_translate)
        self._syncing = True
        try:
            for child, fact in zip(children, facts, strict=True):
                child.setText(3, f"{round(fact.bitrate / 1000)} kbps" if fact.bitrate else "")
                path = fact.path
                if suggestion is None:
                    text = ""
                elif path == suggestion.keep:
                    text = self.tr("★ Keep: {reasons}").format(reasons=", ".join(suggestion.reasons))
                elif path in suggestion.losses:
                    text = self.tr("⚠ Holds {software} data the suggested copy lacks").format(
                        software=" + ".join(suggestion.losses[path])
                    )
                else:
                    text = ""
                child.setText(SUGGESTION_COLUMN, text)
                child.setToolTip(SUGGESTION_COLUMN, text)
            group_item.setData(0, KEEP_ROLE, suggestion.keep if suggestion else None)
        finally:
            self._syncing = False
        return suggestion

    def tick_all_but_suggested(self) -> int:
        """Ticks every copy but the suggested one in each group; returns how
        many are ticked. Copies holding DJ software data the kept one lacks
        stay unticked: the DJ decides."""
        keep: set[str] = set()
        drop: set[str] = set()
        for group_item in self.group_items():
            suggestion = self.suggest(group_item)
            if suggestion is None:
                continue
            keep.add(suggestion.keep)
            drop.update(
                path
                for path in (child.data(0, PATH_ROLE) for child in self._group_children(group_item))
                if path != suggestion.keep and path not in suggestion.losses
            )
        self._syncing = True
        try:
            for path in drop - keep:  # a file kept in one group is never ticked in another
                self.set_checked(path, True)
        finally:
            self._syncing = False
        self._update_buttons()
        return len(drop - keep)

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
            if item.data(0, PATH_ROLE) == path and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
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

    def merge_target(self) -> tuple[str, list[str]] | None:
        """(kept, others) for the group of the selected row: the selected
        file is kept, else the suggested copy. None on a versions group or
        no group."""
        item = self.tree.currentItem()
        if item is None:
            return None
        group_item = item.parent() if item.data(0, PATH_ROLE) else item
        if group_item is None or not self._group_children(group_item) or self._is_versions(group_item):
            return None
        paths = [child.data(0, PATH_ROLE) for child in self._group_children(group_item)]
        if item.data(0, PATH_ROLE):
            kept = item.data(0, PATH_ROLE)
        else:
            suggestion = self.suggest(group_item)
            kept = suggestion.keep if suggestion else paths[0]
        return kept, [path for path in paths if path != kept]

    def _on_merge_clicked(self) -> None:
        target = self.merge_target()
        if target is not None:
            self.mergeRequested.emit(*target)

    def _on_dj_playlists_clicked(self) -> None:
        target = self.merge_target()
        if target is not None:
            self.djPlaylistsRequested.emit(*target)

    def _on_trash_clicked(self) -> None:
        paths = self.checked_paths()
        if paths:
            self.discardRequested.emit(paths)

    def remove_paths(self, paths: list[str]) -> None:
        """Drop moved copies from the tree; a group left with one file goes."""
        gone = set(paths)
        groups = []
        for group in self.groups:
            kept = [index for index, path in enumerate(group.paths) if path not in gone]
            if len(kept) < 2:
                continue
            variants = tuple(group.variants[index] for index in kept if index < len(group.variants))
            if group.tier == TIER_VERSIONS and len(set(variants)) < 2:
                continue
            groups.append(replace(group, paths=tuple(group.paths[index] for index in kept), variants=variants))
        self.groups = groups
        self.tree.clear()
        self._populate()
        self._update_buttons()

    def _update_buttons(self, *_args: object) -> None:
        item = self.tree.currentItem()
        self.reveal_button.setEnabled(item is not None and bool(item.data(0, PATH_ROLE)))
        self.trash_button.setEnabled(bool(self.checked_paths()))
        self.merge_button.setEnabled(self.merge_target() is not None)
        self.dj_playlists_button.setEnabled(self.merge_button.isEnabled())

    def _reveal(self, item: QTreeWidgetItem | None) -> None:
        path = item.data(0, PATH_ROLE) if item is not None else None
        if path:
            reveal_in_file_manager(path)


__all__ = ["DuplicatesDialog", "format_size"]
