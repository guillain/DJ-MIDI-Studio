"""The "Compare mappings" window (issue #189): `mapping_diff.MappingDiff`
rendered as a tree grouped by kind, each row naming the physical control(s)
behind its trigger. Non-modal, so the layouts stay usable while it is open:
selecting a row emits `triggerSelected`, which MainWindow turns into the same
highlight + navigation as a layout click."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from djmidi import catalog
from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.mapping_diff import KIND_LABELS, KINDS, DiffEntry, MappingDiff

ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1


def physical_names(entry: DiffEntry) -> str:
    """Every registered controller's name for this trigger, or "" when no
    catalog knows it (a mixed DDJ-XP2 + XDJ-XZ file can match both)."""
    hits = catalog.lookup(*entry.trigger)
    names = dict.fromkeys(f"{hit.controller}: {hit.name}" for hit in hits)
    return " / ".join(names)


def trigger_text(entry: DiffEntry) -> str:
    kind = "CC" if entry.event_type == "Control Change" else entry.event_type
    return f"Ch {entry.channel} {kind} {entry.control} ({entry.event})"


class MappingDiffDialog(QDialog):
    triggerSelected = Signal(str, str, str)

    def __init__(self, diff: MappingDiff, old_name: str, new_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare Mappings")
        self.setModal(False)
        self.resize(900, 520)
        self.diff = diff

        counts = diff.counts()
        if diff.is_empty:
            summary = "No difference: both mappings bind the same functions with the same values."
        else:
            summary = ", ".join(f"{counts[kind]} {KIND_LABELS[kind].lower()}" for kind in KINDS if counts[kind])
        header = QLabel(f"From <b>{old_name}</b> to <b>{new_name}</b>: {summary}")
        header.setWordWrap(True)
        header.setTextFormat(Qt.TextFormat.RichText)
        header_row = QHBoxLayout()
        header_row.addWidget(header, 1)
        header_row.addWidget(help_button(self, *help_texts.MAPPING_DIFF))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Physical control", "Trigger", "Change"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        for kind in KINDS:
            entries = diff.by_kind(kind)
            if not entries:
                continue
            group = QTreeWidgetItem([f"{KIND_LABELS[kind]} ({len(entries)})"])
            group.setFirstColumnSpanned(True)
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(group)
            for entry in entries:
                item = QTreeWidgetItem(
                    [physical_names(entry) or "(not in any controller profile)", trigger_text(entry), entry.summary()]
                )
                item.setData(0, ENTRY_ROLE, entry)
                item.setToolTip(0, item.text(0).replace(" / ", "\n"))
                item.setToolTip(2, entry.summary())
                group.addChild(item)
            group.setExpanded(True)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 190)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(header_row)
        layout.addWidget(self.tree, 1)
        layout.addLayout(buttons)

    def entry_items(self) -> list[QTreeWidgetItem]:
        return [
            group.child(row)
            for group in (self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount()))
            for row in range(group.childCount())
        ]

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        entry = current.data(0, ENTRY_ROLE) if current is not None else None
        if isinstance(entry, DiffEntry):
            self.triggerSelected.emit(*entry.trigger)
