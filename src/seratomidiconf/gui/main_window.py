from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTreeView,
)

from seratomidiconf.exporter import write_file
from seratomidiconf.gui.edit_panel import EditPanel
from seratomidiconf.gui.tree_model import NODE_ROLE, build_tree_model, relabel_item
from seratomidiconf.model import MidiConfig
from seratomidiconf.parser import parse_file
from seratomidiconf.validator import ValidationIssue, validate

_SEVERITY_COLORS = {
    "error": QColor(255, 200, 200),
    "warning": QColor(255, 235, 180),
    "info": QColor(225, 225, 225),
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Serato MIDI Config Editor")
        self.resize(1100, 700)

        self.config: MidiConfig | None = None
        self.current_path: Path | None = None

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(False)

        self.edit_panel = EditPanel()
        self.edit_panel.changed.connect(self._on_node_changed)

        self.issues_table = QTableWidget(0, 3)
        self.issues_table.setHorizontalHeaderLabels(["Severity", "Message", "Location"])
        self.issues_table.horizontalHeader().setStretchLastSection(True)
        self.issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.edit_panel)
        right_splitter.addWidget(self.issues_table)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.tree_view)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        self.setCentralWidget(main_splitter)

        self.setStatusBar(QStatusBar())
        self._build_menu()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        validate_action = QAction("&Validate", self)
        validate_action.triggered.connect(self._on_validate)
        edit_menu.addAction(validate_action)

    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open Serato MIDI config", "", "XML files (*.xml)")
        if not path_str:
            return
        try:
            self.config = parse_file(path_str)
        except Exception as exc:  # noqa: BLE001 - surface any parse error to the user
            QMessageBox.critical(self, "Failed to open file", str(exc))
            return
        self.current_path = Path(path_str)
        self._load_tree()
        self.issues_table.setRowCount(0)
        self.statusBar().showMessage(f"Loaded {len(self.config.controls)} controls from {self.current_path.name}")

    def _load_tree(self) -> None:
        assert self.config is not None
        model = build_tree_model(self.config)
        self.tree_view.setModel(model)
        self.tree_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.tree_view.expandToDepth(0)

    def _on_selection_changed(self) -> None:
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if not indexes:
            self.edit_panel.set_node(None)
            return
        model = self.tree_view.model()
        item = model.itemFromIndex(indexes[0])
        node = item.data(NODE_ROLE)
        self.edit_panel.set_node(node)

    def _on_node_changed(self, node: object) -> None:
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if not indexes:
            return
        model = self.tree_view.model()
        item = model.itemFromIndex(indexes[0])
        relabel_item(item, node)

    def _on_save(self) -> None:
        if self.config is None:
            return
        if self.current_path is None:
            self._on_save_as()
            return
        write_file(self.config, self.current_path)
        self.statusBar().showMessage(f"Saved to {self.current_path}")

    def _on_save_as(self) -> None:
        if self.config is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(self, "Export Serato MIDI config", "", "XML files (*.xml)")
        if not path_str:
            return
        self.current_path = Path(path_str)
        write_file(self.config, self.current_path)
        self.statusBar().showMessage(f"Saved to {self.current_path}")

    def _on_validate(self) -> None:
        if self.config is None:
            return
        issues: list[ValidationIssue] = validate(self.config)
        self.issues_table.setRowCount(0)
        for issue in issues:
            row = self.issues_table.rowCount()
            self.issues_table.insertRow(row)
            severity_item = QTableWidgetItem(issue.severity)
            message_item = QTableWidgetItem(issue.message)
            location_item = QTableWidgetItem(issue.location)
            color = _SEVERITY_COLORS.get(issue.severity)
            if color is not None:
                for cell in (severity_item, message_item, location_item):
                    cell.setBackground(color)
            self.issues_table.setItem(row, 0, severity_item)
            self.issues_table.setItem(row, 1, message_item)
            self.issues_table.setItem(row, 2, location_item)

        errors = sum(1 for i in issues if i.severity == "error")
        warnings = sum(1 for i in issues if i.severity == "warning")
        infos = sum(1 for i in issues if i.severity == "info")
        self.statusBar().showMessage(f"Validation: {errors} error(s), {warnings} warning(s), {infos} info")
