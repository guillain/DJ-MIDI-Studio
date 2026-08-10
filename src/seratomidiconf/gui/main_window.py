from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from seratomidiconf import catalog
from seratomidiconf.exporter import write_file
from seratomidiconf.gui import layout as layout_mod
from seratomidiconf.gui.deck_tree import build_deck_tree
from seratomidiconf.gui.edit_panel import EditPanel
from seratomidiconf.gui.layout_view import ControllerLayoutView
from seratomidiconf.gui.mapping_group import MappingGroup
from seratomidiconf.gui.tree_model import NODE_ROLE, build_tree_model, relabel_item
from seratomidiconf.model import Control, MappingElement, MidiConfig
from seratomidiconf.parser import parse_file
from seratomidiconf.validator import ValidationIssue, validate

_SEVERITY_COLORS = {
    "error": QColor(255, 200, 200),
    "warning": QColor(255, 235, 180),
    "info": QColor(225, 225, 225),
}

# The official docs catalog.py was transcribed from (see README.md "Technical References").
_REFERENCE_LINKS = [
    ("Serato MIDI Mapping Guide", "https://support.serato.com/hc/en-us/articles/209377487-MIDI-mapping-with-Serato-DJ-Pro"),
    (
        "XDJ-XZ MIDI Message List (PDF)",
        "https://downloads.support.alphatheta.com/software_info/all-in-one-dj-systems/XDJ-XZ/XDJ-XZ_MIDI_Message_List_E3.pdf",
    ),
    (
        "DDJ-XP2 MIDI Message List (PDF)",
        "https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-XP2/DDJ-XP2_MIDI_Message_List_E1.pdf",
    ),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Serato MIDI Config Editor")
        self.resize(1100, 700)

        self.config: MidiConfig | None = None
        self.current_path: Path | None = None
        self.node_to_item: dict[int, object] = {}

        self.undo_stack = QUndoStack(self)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter by channel, control, event type, function, deck, slot...")
        self.search_box.textChanged.connect(self._on_search_text_changed)

        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(False)

        self.tree_proxy_model = QSortFilterProxyModel(self)
        self.tree_proxy_model.setRecursiveFilteringEnabled(True)
        self.tree_proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tree_view.setModel(self.tree_proxy_model)

        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.addWidget(self.search_box)
        tree_layout.addWidget(self.tree_view)

        self.layout_view = ControllerLayoutView()
        self.layout_view.cellActivated.connect(self._on_layout_cell_activated)

        self.deck_tree_view = QTreeView()
        self.deck_tree_view.setHeaderHidden(False)
        self.deck_tree_view.doubleClicked.connect(self._on_deck_item_double_clicked)

        self.deck_layout_view = ControllerLayoutView(show_deck_filter=True)
        self.deck_layout_view.cellActivated.connect(self._on_layout_cell_activated)

        # Each representation pairs a tree (text, precise) with a schematic
        # layout (visual, at-a-glance) of the same underlying data.
        channel_pair = QSplitter(Qt.Orientation.Vertical)
        channel_pair.addWidget(tree_container)
        channel_pair.addWidget(self.layout_view)
        channel_pair.setStretchFactor(0, 1)
        channel_pair.setStretchFactor(1, 1)

        deck_pair = QSplitter(Qt.Orientation.Vertical)
        deck_pair.addWidget(self.deck_tree_view)
        deck_pair.addWidget(self.deck_layout_view)
        deck_pair.setStretchFactor(0, 1)
        deck_pair.setStretchFactor(1, 1)

        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(channel_pair, "By Channel")
        self.left_tabs.addTab(deck_pair, "By Deck")

        self.edit_panel = EditPanel(self.undo_stack, self._on_command_applied, self._on_group_edit_applied)

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
        main_splitter.addWidget(self.left_tabs)
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

        undo_action = self.undo_stack.createUndoAction(self, "&Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)

        redo_action = self.undo_stack.createRedoAction(self, "&Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        validate_action = QAction("&Validate", self)
        validate_action.triggered.connect(self._on_validate)
        edit_menu.addAction(validate_action)

        help_menu = self.menuBar().addMenu("&Help")
        for title, url in _REFERENCE_LINKS:
            action = QAction(title, self)
            action.triggered.connect(lambda checked=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            help_menu.addAction(action)

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
        self.undo_stack.clear()
        self._load_tree()
        self.issues_table.setRowCount(0)
        self.statusBar().showMessage(f"Loaded {len(self.config.controls)} controls from {self.current_path.name}")

    def _load_tree(self) -> None:
        assert self.config is not None
        source_model, self.node_to_item = build_tree_model(self.config)
        self.tree_proxy_model.setSourceModel(source_model)
        self.tree_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.tree_view.expandToDepth(0)
        self._refresh_layout_usage()
        self._refresh_deck_view()

    def _refresh_deck_view(self) -> None:
        assert self.config is not None
        deck_model = build_deck_tree(self.config)
        self.deck_tree_view.setModel(deck_model)
        self.deck_tree_view.selectionModel().selectionChanged.connect(self._on_deck_selection_changed)
        self.deck_tree_view.expandToDepth(0)

    def _on_deck_selection_changed(self) -> None:
        indexes = self.deck_tree_view.selectionModel().selectedIndexes()
        if not indexes:
            self.edit_panel.set_node(None)
            return
        group = self.deck_tree_view.model().itemFromIndex(indexes[0]).data(NODE_ROLE)
        if not isinstance(group, MappingGroup):
            self.edit_panel.set_node(None)
            return
        self.edit_panel.set_node(group)

    def _on_deck_item_double_clicked(self, index) -> None:
        group = self.deck_tree_view.model().itemFromIndex(index).data(NODE_ROLE)
        if not isinstance(group, MappingGroup):
            return
        control = group.members[0][0]
        item = self.node_to_item.get(id(control))
        if item is not None:
            proxy_index = self.tree_proxy_model.mapFromSource(item.index())
            self.tree_view.setCurrentIndex(proxy_index)
            self.tree_view.scrollTo(proxy_index)
        self.left_tabs.setCurrentIndex(0)

    def _on_group_edit_applied(self) -> None:
        # A group edit may touch every duplicate's deck/slot label (main tree) and
        # can move the group to a different deck/slot (deck tree), so both need a
        # full refresh rather than a single relabel.
        current_group = self.edit_panel.current_node
        if isinstance(current_group, MappingGroup):
            for _, _, mapping in current_group.members:
                item = self.node_to_item.get(id(mapping))
                if item is not None:
                    relabel_item(item, mapping)
        QTimer.singleShot(0, self._refresh_edit_panel)
        QTimer.singleShot(0, self._refresh_layout_usage)
        QTimer.singleShot(0, self._refresh_deck_view)

    def _refresh_layout_usage(self) -> None:
        assert self.config is not None
        usage: dict[layout_mod.CellKey, dict[str, set[str]]] = {}
        linked_cells: dict[layout_mod.CellKey, set[layout_mod.CellKey]] = {}
        for control in self.config.controls:
            hits = catalog.lookup(control.channel, control.event_type, control.control)
            if not hits:
                continue
            # A single raw (channel, event_type, control) trigger can match both
            # controllers' catalogs at once (a merged config doesn't record which
            # physical device sent it) — link those cells so the layout can show
            # each controller's interpretation of the same trigger side by side.
            hit_keys = {layout_mod.cell_key(hit) for hit in hits}
            for key in hit_keys:
                others = {other for other in hit_keys if other[0] != key[0]}
                if others:
                    linked_cells.setdefault(key, set()).update(others)
            for userio in control.userios:
                for mapping in userio.mappings:
                    if not mapping.deck_id:
                        continue
                    for hit in hits:
                        cell = usage.setdefault(layout_mod.cell_key(hit), {})
                        cell.setdefault(mapping.deck_id, set()).add(mapping.tag)
        self.layout_view.set_usage(usage, linked_cells)
        self.deck_layout_view.set_usage(usage, linked_cells)

    def _on_layout_cell_activated(self, key: tuple) -> None:
        if self.config is None:
            return
        matches: list[Control] = []
        for control in self.config.controls:
            for hit in catalog.lookup(control.channel, control.event_type, control.control):
                if layout_mod.cell_key(hit) == key:
                    matches.append(control)
                    break
        if not matches:
            self.statusBar().showMessage(f"No control in this file uses '{key[2]}'")
            return
        item = self.node_to_item.get(id(matches[0]))
        if item is not None:
            proxy_index = self.tree_proxy_model.mapFromSource(item.index())
            self.tree_view.setCurrentIndex(proxy_index)
            self.tree_view.scrollTo(proxy_index)
        self.left_tabs.setCurrentIndex(0)
        self.statusBar().showMessage(f"'{key[2]}': {len(matches)} control(s) in this file, showing first")

    def _on_search_text_changed(self, text: str) -> None:
        self.tree_proxy_model.setFilterFixedString(text)

    def _current_node(self) -> object | None:
        indexes = self.tree_view.selectionModel().selectedIndexes()
        if not indexes:
            return None
        source_index = self.tree_proxy_model.mapToSource(indexes[0])
        item = self.tree_proxy_model.sourceModel().itemFromIndex(source_index)
        return item.data(NODE_ROLE)

    def _on_selection_changed(self) -> None:
        self.edit_panel.set_node(self._current_node())

    def _on_command_applied(self, relabel_node: object) -> None:
        item = self.node_to_item.get(id(relabel_node))
        if item is not None:
            relabel_item(item, relabel_node)
        # Deferred so we never rebuild the edit panel from inside the very
        # widget signal (editingFinished/itemChanged) that triggered the edit.
        QTimer.singleShot(0, self._refresh_edit_panel)
        if isinstance(relabel_node, (Control, MappingElement)):
            QTimer.singleShot(0, self._refresh_layout_usage)
            QTimer.singleShot(0, self._refresh_deck_view)

    def _refresh_edit_panel(self) -> None:
        self.edit_panel.set_node(self.edit_panel.current_node)

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
