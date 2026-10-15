"""Report window of the "Ready for live" check (issue #254).

Shows the `ReadyReport` `djmidi.live_ready` produced: a verdict line, a
check box per severity with its count, and one row per finding (severity,
what's wrong, what to do). *Show control* (or a double-click) asks the main
window to select the control a finding is about; *Copy report* puts the
whole report on the clipboard. Read-only: nothing is ever fixed from here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
from djmidi.live_ready import ReadyFinding, ReadyReport, report_text
from djmidi.model import Control

COLUMNS = ("Severity", "Finding", "What to do")
SEVERITIES = ("error", "warning", "info")
_SEVERITY_LABELS = {"error": "Errors", "warning": "Warnings", "info": "Info"}


class LiveReadyDialog(QDialog):
    showControlRequested = Signal(object)
    """The raw `Control` a finding is about, to select in the By Channel tab."""

    def __init__(self, report: ReadyReport, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ready for live")
        fit_to_screen(self, 900, 520)
        self.report = report
        box = QVBoxLayout(self)

        header = QHBoxLayout()
        decks = ", ".join(report.decks) if report.decks else "none"
        self.verdict_label = QLabel(
            f"<b>{report.verdict}</b><br>Decks checked: {decks}. Read-only: nothing is changed."
        )
        self.verdict_label.setWordWrap(True)
        header.addWidget(self.verdict_label, 1)
        header.addWidget(help_button(self, *help_texts.LIVE_READY), 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(header)

        counts = report.counts()
        severity_row = QHBoxLayout()
        self.severity_checkboxes: dict[str, QCheckBox] = {}
        for severity in SEVERITIES:
            checkbox = QCheckBox(f"{_SEVERITY_LABELS[severity]} ({counts[severity]})")
            checkbox.setChecked(True)
            checkbox.setEnabled(counts[severity] > 0)
            checkbox.toggled.connect(self._fill_table)
            self.severity_checkboxes[severity] = checkbox
            severity_row.addWidget(checkbox)
        severity_row.addStretch(1)
        box.addLayout(severity_row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _index: self._show_control())
        usable_minimum(self.table, 480, 180)
        box.addWidget(self.table, 1)

        self.count_label = QLabel()
        box.addWidget(self.count_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.show_button = QPushButton("Show control")
        self.show_button.setToolTip("Select this control in the By Channel view (double-click does the same).")
        self.show_button.clicked.connect(self._show_control)
        buttons.addButton(self.show_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button = QPushButton("Copy report")
        self.copy_button.setToolTip("Copy the whole report as text.")
        self.copy_button.clicked.connect(self._copy_report)
        buttons.addButton(self.copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        keep_wrapped_text_visible(self)

        self.table.itemSelectionChanged.connect(self._update_buttons)
        self._visible: list[ReadyFinding] = []
        self._fill_table()

    def visible_findings(self) -> list[ReadyFinding]:
        return list(self._visible)

    def _fill_table(self, *_args: object) -> None:
        shown = {severity for severity, checkbox in self.severity_checkboxes.items() if checkbox.isChecked()}
        self._visible = [finding for finding in self.report.findings if finding.severity in shown]
        self.table.setRowCount(0)
        for finding in self._visible:
            row = self.table.rowCount()
            self.table.insertRow(row)
            cells = (finding.severity, finding.message, finding.hint)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(finding.location or text)
                self.table.setItem(row, column, item)
        self.table.resizeRowsToContents()
        self.count_label.setText(f"{len(self._visible)} of {len(self.report.findings)} finding(s) shown")
        self._update_buttons()

    def current_finding(self) -> ReadyFinding | None:
        row = self.table.currentRow()
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def _update_buttons(self, *_args: object) -> None:
        finding = self.current_finding()
        self.show_button.setEnabled(finding is not None and finding.control is not None)
        self.copy_button.setEnabled(bool(self.report.findings))

    def _show_control(self) -> None:
        finding = self.current_finding()
        if finding is not None and isinstance(finding.control, Control):
            self.showControlRequested.emit(finding.control)

    def _copy_report(self) -> None:
        QGuiApplication.clipboard().setText(report_text(self.report))
        self.count_label.setText("Report copied to the clipboard")


__all__ = ["COLUMNS", "LiveReadyDialog"]
