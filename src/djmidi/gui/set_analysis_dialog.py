"""The analysis of a recorded live set (`set_analysis`), in four tabs:
buttons, continuous controls, sequences and activity. Read-only."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_tab_titles_whole,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.set_analysis import ACTIVITY_SLICE_S, SEQUENCE_GAP_S, SetAnalysis

_BAR_WIDTH = 40


def _table(headers: list[str], rows: list[list[object]]) -> QTableWidget:
    table = QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            item = QTableWidgetItem()
            if isinstance(value, int):
                item.setData(Qt.ItemDataRole.DisplayRole, value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                item.setText(str(value))
            table.setItem(row, column, item)
    header = table.horizontalHeader()
    for column in range(len(headers)):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    header.setStretchLastSection(True)
    usable_minimum(table, 360, 160)
    return table


class SetAnalysisDialog(QDialog):
    def __init__(self, analysis: SetAnalysis, path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Set analysis"))
        fit_to_screen(self, 900, 600)
        self.analysis = analysis
        box = QVBoxLayout(self)

        header = QHBoxLayout()
        minutes = analysis.duration_s / 60
        summary = self.tr(
            "{minutes} min · {events} MIDI event(s) · {presses} button press(es), {unnamed} of them on no known control"
        ).format(minutes=f"{minutes:.0f}", events=analysis.events, presses=analysis.presses, unnamed=analysis.unnamed_presses)
        ports = ", ".join(f"{port} ({count})" for port, count in analysis.ports.most_common())
        self.summary_label = QLabel(
            (f"<b>{path.name}</b><br>" if path is not None else "")
            + summary
            + ("<br>" + self.tr("Ports: {ports}").format(ports=ports) if ports else "")
        )
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header.addWidget(self.summary_label, 1)
        header.addWidget(help_button(self, *help_texts.SET_ANALYSIS), 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(header)

        self.tabs = QTabWidget()
        keep_tab_titles_whole(self.tabs, scroll=False)
        self.buttons_table = _table(
            [self.tr("Control"), self.tr("Port"), self.tr("Presses")],
            [[name, key.port, count] for key, name, count in analysis.buttons],
        )
        self.tabs.addTab(self.buttons_table, self.tr("Buttons"))
        self.continuous_table = _table(
            [self.tr("Control"), self.tr("Port"), self.tr("Messages")],
            [[name, key.port, count] for key, name, count in analysis.continuous],
        )
        self.tabs.addTab(self.continuous_table, self.tr("Jogs, knobs and faders"))
        self.sequences_table = _table(
            [self.tr("First"), self.tr("Then"), self.tr("Times")],
            [[first, then, count] for first, then, count in analysis.sequences],
        )
        self.sequences_table.setToolTip(
            self.tr("Two different buttons pressed within {seconds} s of each other.").format(seconds=SEQUENCE_GAP_S)
        )
        self.tabs.addTab(self.sequences_table, self.tr("Sequences"))
        busiest = max(analysis.activity, default=0) or 1
        slice_minutes = ACTIVITY_SLICE_S // 60
        self.activity_table = _table(
            [self.tr("From (min)"), self.tr("Presses"), ""],
            [
                [index * slice_minutes, count, "█" * round(_BAR_WIDTH * count / busiest)]
                for index, count in enumerate(analysis.activity)
            ],
        )
        self.tabs.addTab(self.activity_table, self.tr("Activity"))
        box.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        keep_wrapped_text_visible(self)


__all__ = ["SetAnalysisDialog"]
