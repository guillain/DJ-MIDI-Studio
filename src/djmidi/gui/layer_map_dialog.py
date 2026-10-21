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
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.model import MidiConfig

# English source texts (what tests see); the dialog shows them through tr().
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
        self.setWindowTitle(self.tr("Layer Map"))
        fit_to_screen(self, 1100, 640)
        self._config_provider = config_provider
        self.layer_map: LayerMap | None = None
        box = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(self.tr("Controller:")))
        self.controller_combo = QComboBox()
        for name, count in controllers:
            label = self.tr("{name} — {count} mapped trigger(s)").format(name=name, count=count) if count else name
            self.controller_combo.addItem(label, name)
        if preselected is not None and (index := self.controller_combo.findData(preselected)) >= 0:
            self.controller_combo.setCurrentIndex(index)
        self.controller_combo.currentIndexChanged.connect(lambda _index: self.rebuild())
        controls.addWidget(self.controller_combo, 1)
        controls.addWidget(QLabel(self.tr("Section:")))
        self.section_combo = QComboBox()
        # Never cut a section name to a few letters when the window is small,
        # nor "All sections" in a language where it is longer (issue #290).
        self.section_combo.setMinimumContentsLength(max(len(ALL_SECTIONS), len(self.tr("All sections"))))
        self.section_combo.currentIndexChanged.connect(lambda _index: self._fill_table())
        controls.addWidget(self.section_combo)
        controls.addWidget(help_button(self, *help_texts.LAYER_MAP))
        box.addLayout(controls)
        # On its own row: beside the combos, its French label pushed the
        # minimum width past a 900 px screen (issue #290).
        self.free_only_checkbox = QCheckBox(self.tr("Only controls with a free layer"))
        self.free_only_checkbox.setToolTip(self.tr("Hide the controls whose every layer is already mapped."))
        self.free_only_checkbox.toggled.connect(lambda _checked: self._fill_table())
        box.addWidget(self.free_only_checkbox)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        box.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(170)
        usable_minimum(self.table, 480, 200)
        box.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.refresh_button.setToolTip(self.tr("Re-read the loaded mapping, including edits made since this window opened."))
        self.refresh_button.clicked.connect(self.rebuild)
        buttons.addButton(self.refresh_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        keep_wrapped_text_visible(self)
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
        # Item 0 is "All sections" (translated); the filter goes by index,
        # never by that text.
        previous = self.section_combo.currentText() if self.section_combo.currentIndex() > 0 else None
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.addItem(self.tr("All sections"))
        if self.layer_map is not None:
            self.section_combo.addItems(self.layer_map.sections())
        index = self.section_combo.findText(previous) if previous is not None else 0
        self.section_combo.setCurrentIndex(max(index, 0))
        self.section_combo.blockSignals(False)
        self._fill_table()

    def _fill_table(self) -> None:
        layer_map = self.layer_map
        self.table.clear()
        if layer_map is None:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.summary_label.setText(self.tr("No controller to show."))
            return
        section = self.section_combo.currentText() if self.section_combo.currentIndex() > 0 else None
        rows = [
            row
            for row in layer_map.rows
            if (section is None or row.section == section)
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
                    item.setToolTip(
                        self.tr("{control} has no {layer} layer on this controller.").format(
                            control=row.control, layer=layer
                        )
                    )
                elif cell.status == STATUS_FREE:
                    item = QTableWidgetItem(self.tr("free"))
                    item.setBackground(FREE_BRUSH)
                    item.setToolTip(
                        self.tr("Free: nothing in this mapping uses it.")
                        + "\n"
                        + "\n".join(describe_trigger(t) for t in cell.free_triggers)
                    )
                else:
                    item = QTableWidgetItem("\n".join(cell.functions))
                    tooltip = "\n".join(cell.functions)
                    if cell.status == STATUS_PARTIAL:
                        item.setBackground(PARTIAL_BRUSH)
                        tooltip += "\n\n" + self.tr("Still free on:") + "\n" + "\n".join(
                            describe_trigger(t) for t in cell.free_triggers
                        )
                    item.setToolTip(tooltip)
                item.setData(Qt.ItemDataRole.UserRole, cell.status if cell is not None else None)
                self.table.setItem(row_index, column, item)
        self.table.resizeRowsToContents()
        self.summary_label.setText(
            self.tr(
                "{controller}: {mapped} mapped, {partial} partly free (amber), {free} free (green) "
                "combination(s) across {layers} layer(s). Hover a free cell for the raw MIDI triggers left."
            ).format(
                controller=layer_map.controller,
                mapped=layer_map.count("mapped"),
                partial=layer_map.count(STATUS_PARTIAL),
                free=layer_map.count(STATUS_FREE),
                layers=len(layer_map.layers),
            )
        )


__all__ = ["LayerMapDialog"]
