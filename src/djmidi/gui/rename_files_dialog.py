"""Rename files… dialog of the Music Library tab (issue #260).

A template field, a live preview table (current name, new name, status per
selected track) built by `library.rename.plan_renames` through the
`planner` the view passes in, the relink warning, and an option to save an
``old_path,new_path`` CSV once the files are renamed. The dialog itself
never touches a file: on accept the view pushes a `RenameFilesCommand`
with `renames()`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from djmidi.library import rename
from djmidi.library.rename import RenamePlan, TemplateError

_STATUS_COLOUR = {
    rename.STATUS_CONFLICT: QColor("#c0392b"),
    rename.STATUS_REFUSED: QColor("#c0392b"),
    rename.STATUS_MISSING_TAGS: QColor("#b7791f"),
}


class RenameFilesDialog(QDialog):
    def __init__(
        self,
        planner: Callable[[str], RenamePlan],
        template: str = rename.DEFAULT_TEMPLATE,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Rename files"))
        fit_to_screen(self, 900, 480)
        self._planner = planner
        self.plan: RenamePlan | None = None
        self._status_text = {
            rename.STATUS_RENAME: self.tr("Rename"),
            rename.STATUS_UNCHANGED: self.tr("Unchanged"),
            rename.STATUS_MISSING_TAGS: self.tr("Skipped"),
            rename.STATUS_CONFLICT: self.tr("Conflict"),
            rename.STATUS_REFUSED: self.tr("Refused"),
        }
        box = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Template")))
        self.template_edit = QLineEdit(template)
        self.template_edit.setToolTip(self.tr("Fields: ") + ", ".join(f"{{{name}}}" for name in rename.TEMPLATE_FIELDS))
        row.addWidget(self.template_edit, 1)
        row.addWidget(help_button(self, *help_texts.LIBRARY_RENAME))
        box.addLayout(row)
        fields = QLabel(self.tr("Fields: ") + "  ".join(f"{{{name}}}" for name in rename.TEMPLATE_FIELDS))
        fields.setWordWrap(True)
        box.addWidget(fields)

        warning = QLabel("⚠ " + self.tr(rename.RELINK_WARNING))
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b7791f;")
        box.addWidget(warning)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("Current name"), self.tr("New name"), self.tr("Status")])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 330)
        self.tree.setColumnWidth(1, 330)
        usable_minimum(self.tree, 480, 140)
        box.addWidget(self.tree, 1)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        box.addWidget(self.summary_label)

        self.csv_checkbox = QCheckBox(self.tr("Save an old → new path CSV for relinking after renaming"))
        self.csv_checkbox.setChecked(True)
        box.addWidget(self.csv_checkbox)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)
        keep_wrapped_text_visible(self)
        self.template_edit.textChanged.connect(self.refresh)
        self.refresh()

    @property
    def template(self) -> str:
        return self.template_edit.text()

    @property
    def save_csv(self) -> bool:
        return self.csv_checkbox.isChecked()

    def renames(self) -> list[tuple[str, str]]:
        return self.plan.renames if self.plan is not None else []

    def refresh(self, *_args: object) -> None:
        """Re-plan with the current template and refill the preview."""
        self.tree.clear()
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        try:
            self.plan = self._planner(self.template)
        except TemplateError as exc:
            self.plan = None
            self.summary_label.setText(str(exc))
            ok.setText(self.tr("Rename"))
            ok.setEnabled(False)
            return
        for item in self.plan.items:
            new_name = Path(item.new_path).name if item.new_path else ""
            status = self._status_text.get(item.status, item.status)
            row = QTreeWidgetItem([Path(item.old_path).name, new_name, f"{status}: {item.reason}" if item.reason else status])
            row.setToolTip(0, item.old_path)
            row.setToolTip(1, item.new_path or "")
            colour = _STATUS_COLOUR.get(item.status)
            if colour is not None:
                row.setForeground(2, QBrush(colour))
            self.tree.addTopLevelItem(row)
        count = len(self.plan.renames)
        others = [
            f"{self.plan.count(status)} {self._status_text[status].lower()}"
            for status in (rename.STATUS_UNCHANGED, rename.STATUS_MISSING_TAGS, rename.STATUS_CONFLICT, rename.STATUS_REFUSED)
            if self.plan.count(status)
        ]
        self.summary_label.setText(
            self.tr("{count} file(s) will be renamed").format(count=count)
            + (f" ({', '.join(others)})." if others else ".")
        )
        ok.setText(self.tr("Rename {count} file(s)").format(count=count))
        ok.setEnabled(count > 0)


__all__ = ["RenameFilesDialog"]
