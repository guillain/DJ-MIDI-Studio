"""Organize into folders… dialog of the Music Library tab (issue #406).

A preview table (current path, new path, status per selected track) built
by `library.organize.plan_from_rows` through the `planner` the view passes
in -- nothing to type, since the target only depends on each track's
already-resolved category. The dialog itself never moves a file: on
accept the view pushes the move through `RenameFilesCommand` (issue #406
generalized it to take any old/new pair, not just a template rename).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
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
from djmidi.library import organize, rename
from djmidi.library.organize import OrganizePlan

_STATUS_COLOUR = {
    organize.STATUS_CONFLICT: QColor("#c0392b"),
    organize.STATUS_REFUSED: QColor("#c0392b"),
    organize.STATUS_NO_CATEGORY: QColor("#b7791f"),
}


class OrganizeFilesDialog(QDialog):
    def __init__(self, planner: Callable[[], OrganizePlan], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Organize into folders"))
        fit_to_screen(self, 900, 480)
        self._status_text = {
            organize.STATUS_MOVE: self.tr("Move"),
            organize.STATUS_UNCHANGED: self.tr("Unchanged"),
            organize.STATUS_NO_CATEGORY: self.tr("Skipped"),
            organize.STATUS_CONFLICT: self.tr("Conflict"),
            organize.STATUS_REFUSED: self.tr("Refused"),
        }
        box = QVBoxLayout(self)

        row = QLabel(
            self.tr("Moves each selected track into <root>/Family/Name, following its confirmed category. "
                     "The filename itself doesn't change.")
        )
        row.setWordWrap(True)
        box.addWidget(row)
        box.addWidget(help_button(self, *help_texts.LIBRARY_ORGANIZE))

        # Serato/Traktor/Rekordbox need relinking after a move exactly the
        # same way as after a rename -- the exact same warning, same
        # translation, so this reuses RenameFilesDialog's context too.
        warning = QLabel("⚠ " + QCoreApplication.translate("RenameFilesDialog", rename.RELINK_WARNING))
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b7791f;")
        box.addWidget(warning)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("Current path"), self.tr("New path"), self.tr("Status")])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 330)
        self.tree.setColumnWidth(1, 330)
        usable_minimum(self.tree, 480, 140)
        box.addWidget(self.tree, 1)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        box.addWidget(self.summary_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)
        keep_wrapped_text_visible(self)
        self.plan = planner()
        self._fill()

    def moves(self) -> list[tuple[str, str]]:
        return self.plan.moves if self.plan is not None else []

    def _fill(self) -> None:
        self.tree.clear()
        for item in self.plan.items:
            status = self._status_text.get(item.status, item.status)
            row = QTreeWidgetItem(
                [item.old_path, item.new_path or "", f"{status}: {item.reason}" if item.reason else status]
            )
            row.setToolTip(0, item.old_path)
            row.setToolTip(1, item.new_path or "")
            colour = _STATUS_COLOUR.get(item.status)
            if colour is not None:
                row.setForeground(2, QBrush(colour))
            self.tree.addTopLevelItem(row)
        count = len(self.plan.moves)
        other_statuses = (
            organize.STATUS_UNCHANGED,
            organize.STATUS_NO_CATEGORY,
            organize.STATUS_CONFLICT,
            organize.STATUS_REFUSED,
        )
        others = [
            f"{self.plan.count(status)} {self._status_text[status].lower()}"
            for status in other_statuses
            if self.plan.count(status)
        ]
        self.summary_label.setText(
            self.tr("{count} file(s) will move").format(count=count)
            + (f" ({', '.join(others)})." if others else ".")
        )
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(self.tr("Move {count} file(s)").format(count=count))
        ok.setEnabled(count > 0)


__all__ = ["OrganizeFilesDialog"]
