"""Library health report window of the Music Library tab (issue #225).

Shows the `HealthReport` `djmidi.library.health` produced: one row per
problem (issue, detail, file), a check box per issue kind with its count, a
free-text filter, *Reveal in Finder*, *Show in library* (selects the track
in the tab's table) and *Export CSV…*, which writes exactly the rows the
filters show. Read-only: the dialog never touches an audio file.

The table is a small `QAbstractTableModel` rather than a `QTableWidget`:
"missing artwork" alone can list most of an 85k-track collection.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from djmidi import user_paths
from djmidi.gui import help_texts
from djmidi.gui.file_reveal import reveal_in_file_manager
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.library.health import (
    ISSUE_KINDS,
    ISSUE_LABELS,
    HealthIssue,
    HealthReport,
    export_csv,
    filter_issues,
)

COLUMNS = (
    QT_TRANSLATE_NOOP("HealthReportDialog", "Issue"),
    QT_TRANSLATE_NOOP("HealthReportDialog", "Detail"),
    QT_TRANSLATE_NOOP("HealthReportDialog", "File"),
)
# Labels and fixed details come from Qt-free library.health (issue #313).
_translate = translator("HealthReportDialog")


class HealthIssueModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._issues: list[HealthIssue] = []

    def set_issues(self, issues: list[HealthIssue]) -> None:
        self.beginResetModel()
        self._issues = list(issues)
        self.endResetModel()

    def issues(self) -> list[HealthIssue]:
        return list(self._issues)

    def issue(self, row: int) -> HealthIssue | None:
        return self._issues[row] if 0 <= row < len(self._issues) else None

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._issues)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return QCoreApplication.translate("HealthReportDialog", COLUMNS[section])
        return None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        issue = self.issue(index.row()) if index.isValid() else None
        if issue is None:
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return (_translate(issue.label), _translate(issue.detail), issue.path)[index.column()]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        kind_order = {kind: index for index, kind in enumerate(ISSUE_KINDS)}
        keys = (
            lambda issue: (kind_order.get(issue.kind, len(kind_order)), issue.path),
            lambda issue: (_translate(issue.detail).casefold(), issue.path),
            lambda issue: (issue.path.casefold(), kind_order.get(issue.kind, 0)),
        )
        self.layoutAboutToBeChanged.emit()
        self._issues.sort(key=keys[column], reverse=order == Qt.SortOrder.DescendingOrder)
        self.layoutChanged.emit()


class HealthReportDialog(QDialog):
    showTrackRequested = Signal(str)
    """Path of the track to select in the Music Library table."""

    def __init__(self, report: HealthReport, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Library health report"))
        self.resize(900, 560)
        self.report = report
        box = QVBoxLayout(self)

        header = QHBoxLayout()
        self.summary_label = QLabel(
            self.tr(
                "{checked} file(s) checked, {affected} with at least one issue ({issues} issue(s)). "
                "Read-only: nothing is changed."
            ).format(checked=report.checked, affected=report.affected_files, issues=len(report.issues))
        )
        self.summary_label.setWordWrap(True)
        header.addWidget(self.summary_label, 1)
        header.addWidget(help_button(self, *help_texts.LIBRARY_HEALTH), 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(header)

        counts = report.counts()
        kinds_row = QHBoxLayout()
        self.kind_checkboxes: dict[str, QCheckBox] = {}
        for kind in ISSUE_KINDS:
            checkbox = QCheckBox(f"{_translate(ISSUE_LABELS[kind])} ({counts[kind]})")
            checkbox.setChecked(True)
            checkbox.setEnabled(counts[kind] > 0)
            checkbox.toggled.connect(self._apply_filters)
            self.kind_checkboxes[kind] = checkbox
            kinds_row.addWidget(checkbox)
        kinds_row.addStretch(1)
        box.addLayout(kinds_row)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("Filter by path or detail…"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filters)
        box.addWidget(self.filter_edit)

        self.model = HealthIssueModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _index: self._show_in_library())
        box.addWidget(self.table, 1)

        self.count_label = QLabel()
        box.addWidget(self.count_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.reveal_button = QPushButton(self.tr("Reveal in Finder"))
        self.reveal_button.setToolTip(self.tr("Show the selected file in your file manager."))
        self.reveal_button.clicked.connect(self._reveal)
        buttons.addButton(self.reveal_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.show_button = QPushButton(self.tr("Show in library"))
        self.show_button.setToolTip(
            self.tr("Select this track in the Music Library table (double-click does the same).")
        )
        self.show_button.clicked.connect(self._show_in_library)
        buttons.addButton(self.show_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.export_button = QPushButton(self.tr("Export CSV…"))
        self.export_button.setToolTip(self.tr("Save the rows shown (current filters) as a CSV file."))
        self.export_button.clicked.connect(self._on_export_clicked)
        buttons.addButton(self.export_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

        self.table.selectionModel().currentRowChanged.connect(self._update_buttons)
        self._apply_filters()

    def checked_kinds(self) -> list[str]:
        return [kind for kind, checkbox in self.kind_checkboxes.items() if checkbox.isChecked()]

    def visible_issues(self) -> list[HealthIssue]:
        return self.model.issues()

    def _apply_filters(self, *_args: object) -> None:
        issues = filter_issues(self.report.issues, self.checked_kinds(), self.filter_edit.text(), _translate)
        self.model.set_issues(issues)
        header = self.table.horizontalHeader()
        if header.sortIndicatorSection() >= 0 and self.table.isSortingEnabled():
            self.model.sort(header.sortIndicatorSection(), header.sortIndicatorOrder())
        self.count_label.setText(
            self.tr("{shown} of {total} issue(s) shown").format(shown=len(issues), total=len(self.report.issues))
        )
        self._update_buttons()

    def current_issue(self) -> HealthIssue | None:
        index = self.table.currentIndex()
        return self.model.issue(index.row()) if index.isValid() else None

    def _update_buttons(self, *_args: object) -> None:
        has_current = self.current_issue() is not None
        self.reveal_button.setEnabled(has_current)
        self.show_button.setEnabled(has_current)
        self.export_button.setEnabled(self.model.rowCount() > 0)

    def _reveal(self) -> None:
        issue = self.current_issue()
        if issue is not None:
            reveal_in_file_manager(issue.path)

    def _show_in_library(self) -> None:
        issue = self.current_issue()
        if issue is not None:
            self.showTrackRequested.emit(issue.path)

    def export_to(self, path: str) -> int:
        """Write the visible rows to `path`; returns the row count."""
        return export_csv(path, self.visible_issues())

    def _on_export_clicked(self) -> None:
        default = str(user_paths.subfolder(user_paths.EXPORTS) / "library-health.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export health report"), default, self.tr("CSV files (*.csv)")
        )
        if not path:
            return
        try:
            count = self.export_to(path)
        except OSError as exc:
            QMessageBox.warning(
                self, self.tr("Export health report"), self.tr("Could not write {path}:\n{error}").format(path=path, error=exc)
            )
            return
        self.count_label.setText(self.tr("Exported {count} row(s) to {path}").format(count=count, path=path))


__all__ = ["COLUMNS", "HealthIssueModel", "HealthReportDialog"]
