"""View -> Layer Map (issue #253): one table per controller, a row per
physical control and a column per layer (normal, +SHIFT, each pad bank),
showing what the loaded mapping binds to each combination and highlighting
the free ones. Read-only and non-modal; the resolution lives in the
Qt-free gui/layer_map.py.

The dialog keeps a `config_provider` callable rather than a snapshot, so
*Refresh* picks up edits made in the editor since it opened."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from djmidi import catalog
from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.layer_map import (
    STATUS_FREE,
    STATUS_PARTIAL,
    LayerMap,
    build_layer_map,
    describe_trigger,
)
from djmidi.model import MidiConfig

ALL_SECTIONS = "All sections"
NOT_APPLICABLE = "—"
FREE_TEXT = "free"

# Translucent, so they read on both the dark and the light theme.
FREE_BRUSH = QBrush(QColor(46, 160, 67, 90))
PARTIAL_BRUSH = QBrush(QColor(214, 158, 46, 90))


class LayerMapDialog(QDialog):
    def __init__(
        self,
        config_provider: Callable[[], MidiConfig | None],
        controllers: list[tuple[str, int]],
        preselected: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Layer Map")
        self.resize(1100, 640)
        self._config_provider = config_provider
        self.layer_map: LayerMap | None = None
        box = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Controller:"))
        self.controller_combo = QComboBox()
        for name, count in controllers:
            self.controller_combo.addItem(f"{name} — {count} mapped trigger(s)" if count else name, name)
        if preselected is not None and (index := self.controller_combo.findData(preselected)) >= 0:
            self.controller_combo.setCurrentIndex(index)
        self.controller_combo.currentIndexChanged.connect(lambda _index: self.rebuild())
        controls.addWidget(self.controller_combo, 1)
        controls.addWidget(QLabel("Section:"))
        self.section_combo = QComboBox()
        self.section_combo.currentIndexChanged.connect(lambda _index: self._fill_table())
        controls.addWidget(self.section_combo)
        self.free_only_checkbox = QCheckBox("Only controls with a free layer")
        self.free_only_checkbox.setToolTip("Hide the controls whose every layer is already mapped.")
        self.free_only_checkbox.toggled.connect(lambda _checked: self._fill_table())
        controls.addWidget(self.free_only_checkbox)
        controls.addWidget(help_button(self, *help_texts.LAYER_MAP))
        box.addLayout(controls)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        box.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(170)
        box.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Re-read the loaded mapping, including edits made since this window opened.")
        self.refresh_button.clicked.connect(self.rebuild)
        buttons.addButton(self.refresh_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.rebuild()

    def current_controller(self) -> str | None:
        return self.controller_combo.currentData()

    def rebuild(self) -> None:
        """Recompute the map for the chosen controller and the current
        mapping, keeping the section filter when it still exists."""
        controller = self.current_controller()
        if controller is None or controller not in catalog.CONTROLLER_NAMES:
            self.layer_map = None
        else:
            self.layer_map = build_layer_map(self._config_provider(), controller)
        previous = self.section_combo.currentText()
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.addItem(ALL_SECTIONS)
        if self.layer_map is not None:
            self.section_combo.addItems(self.layer_map.sections())
        index = self.section_combo.findText(previous)
        self.section_combo.setCurrentIndex(max(index, 0))
        self.section_combo.blockSignals(False)
        self._fill_table()

    def _fill_table(self) -> None:
        layer_map = self.layer_map
        self.table.clear()
        if layer_map is None:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.summary_label.setText("No controller to show.")
            return
        section = self.section_combo.currentText()
        rows = [
            row
            for row in layer_map.rows
            if (section in ("", ALL_SECTIONS) or row.section == section)
            and (
                not self.free_only_checkbox.isChecked()
                or any(cell.status in (STATUS_FREE, STATUS_PARTIAL) for cell in row.cells.values())
            )
        ]
        layers = [layer for layer in layer_map.layers if any(layer in row.cells for row in rows)]
        self.table.setColumnCount(len(layers))
        self.table.setHorizontalHeaderLabels(layers)
        self.table.setRowCount(len(rows))
        self.table.setVerticalHeaderLabels([f"{row.section} · {row.control}" for row in rows])
        for row_index, row in enumerate(rows):
            for column, layer in enumerate(layers):
                cell = row.cells.get(layer)
                if cell is None:
                    item = QTableWidgetItem(NOT_APPLICABLE)
                    item.setForeground(QBrush(QColor(128, 128, 128)))
                    item.setToolTip(f"{row.control} has no {layer} layer on this controller.")
                elif cell.status == STATUS_FREE:
                    item = QTableWidgetItem(FREE_TEXT)
                    item.setBackground(FREE_BRUSH)
                    item.setToolTip(
                        "Free: nothing in this mapping uses it.\n"
                        + "\n".join(describe_trigger(t) for t in cell.free_triggers)
                    )
                else:
                    item = QTableWidgetItem("\n".join(cell.functions))
                    tooltip = "\n".join(cell.functions)
                    if cell.status == STATUS_PARTIAL:
                        item.setBackground(PARTIAL_BRUSH)
                        tooltip += "\n\nStill free on:\n" + "\n".join(
                            describe_trigger(t) for t in cell.free_triggers
                        )
                    item.setToolTip(tooltip)
                item.setData(Qt.ItemDataRole.UserRole, cell.status if cell is not None else None)
                self.table.setItem(row_index, column, item)
        self.table.resizeRowsToContents()
        self.summary_label.setText(
            f"{layer_map.controller}: {layer_map.count('mapped')} mapped, "
            f"{layer_map.count(STATUS_PARTIAL)} partly free (amber), "
            f"{layer_map.count(STATUS_FREE)} free (green) combination(s) across "
            f"{len(layer_map.layers)} layer(s). Hover a free cell for the raw MIDI triggers left."
        )


__all__ = ["LayerMapDialog"]
