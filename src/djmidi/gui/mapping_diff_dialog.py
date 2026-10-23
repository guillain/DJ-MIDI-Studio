"""The "Compare mappings" window (issue #189): `mapping_diff.MappingDiff`
rendered as a tree grouped by kind, each row naming the physical control(s)
behind its trigger. Non-modal, so the layouts stay usable while it is open:
selecting a row emits `triggerSelected`, which MainWindow turns into the same
highlight + navigation as a layout click.

Every label is in the interface language (issue #333): the dialog's own
strings through `tr()`, the report's through the "MappingDiff" translator,
also used by MainWindow to build the `MappingDiff` it shows."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
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
from djmidi.gui.translation import translator
from djmidi.mapping_diff import KIND_COUNTS, KIND_LABELS, KINDS, DiffEntry, MappingDiff

ENTRY_ROLE = Qt.ItemDataRole.UserRole + 1


def physical_names(entry: DiffEntry) -> str:
    """Every registered controller's name for this trigger, or "" when no
    catalog knows it (a mixed DDJ-XP2 + XDJ-XZ file can match both)."""
    hits = catalog.lookup(*entry.trigger)
    names = dict.fromkeys(f"{hit.controller}: {hit.name}" for hit in hits)
    return " / ".join(names)


def trigger_text(entry: DiffEntry) -> str:
    """"Ch 14 Note On 65 (click)": the MIDI words and Serato's event name stay
    as the file writes them; only "Ch" follows the interface language."""
    kind = "CC" if entry.event_type == "Control Change" else entry.event_type
    return QCoreApplication.translate("MappingDiffDialog", "Ch {channel} {kind} {control} ({event})").format(
        channel=entry.channel, kind=kind, control=entry.control, event=entry.event
    )


class MappingDiffDialog(QDialog):
    triggerSelected = Signal(str, str, str)

    def __init__(self, diff: MappingDiff, old_name: str, new_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Compare Mappings"))
        self.setModal(False)
        self.resize(900, 520)
        self.diff = diff

        report = translator("MappingDiff")
        counts = diff.counts()
        if diff.is_empty:
            summary = self.tr("No difference: both mappings bind the same functions with the same values.")
        else:
            summary = ", ".join(report(KIND_COUNTS[kind]).format(count=counts[kind]) for kind in KINDS if counts[kind])
        header = QLabel(
            self.tr("From <b>{old}</b> to <b>{new}</b>: {summary}").format(old=old_name, new=new_name, summary=summary)
        )
        header.setWordWrap(True)
        header.setTextFormat(Qt.TextFormat.RichText)
        header_row = QHBoxLayout()
        header_row.addWidget(header, 1)
        header_row.addWidget(help_button(self, *help_texts.MAPPING_DIFF))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("Physical control"), self.tr("Trigger"), self.tr("Change")])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        for kind in KINDS:
            entries = diff.by_kind(kind)
            if not entries:
                continue
            group = QTreeWidgetItem([f"{report(KIND_LABELS[kind])} ({len(entries)})"])
            group.setFirstColumnSpanned(True)
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(group)
            for entry in entries:
                summary = entry.summary(report)
                item = QTreeWidgetItem(
                    [
                        physical_names(entry) or self.tr("(not in any controller profile)"),
                        trigger_text(entry),
                        summary,
                    ]
                )
                item.setData(0, ENTRY_ROLE, entry)
                item.setToolTip(0, item.text(0).replace(" / ", "\n"))
                raw = entry.raw_summary(report)
                # The raw tags stay one hover away when a readable name replaced them.
                tooltip = summary if raw == summary else self.tr("{summary}\nRaw: {raw}").format(summary=summary, raw=raw)
                item.setToolTip(2, tooltip)
                group.addChild(item)
            group.setExpanded(True)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 190)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)

        close_button = QPushButton(self.tr("Close"))
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
