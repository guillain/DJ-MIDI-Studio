from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog, software, user_paths
from djmidi.controller_sync import ControllerSyncSet
from djmidi.gui.file_reveal import reveal_in_file_manager
from djmidi.logging_config import default_log_path
from djmidi.midi_io import list_output_ports
from djmidi.plugins import PluginPreferences


class PreferencesDialog(QDialog):
    """Safe, explicit preferences for plugins and integration policies."""

    def __init__(self, preferences: PluginPreferences, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DJ MIDI Studio Preferences")
        self._preferences = preferences
        self._plugin_checks: dict[str, QCheckBox] = {}
        self._controller_plugin_ids: set[str] = set()

        detection = QComboBox()
        detection.addItem("Ask before enabling", "ask")
        detection.addItem("Suggest detected integration", "suggest")
        detection.setCurrentIndex(max(detection.findData(preferences.detection_policy), 0))
        self._detection = detection

        routing = QCheckBox("Enable MIDI routing policies")
        routing.setChecked(preferences.routing_enabled)
        self._routing = routing
        trust = QCheckBox("Trust external plugins")
        trust.setChecked(preferences.trust_external_plugins)
        self._trust = trust
        auto_start_live_monitor = QCheckBox("Auto-start Live Monitor when a mapping is loaded")
        auto_start_live_monitor.setChecked(preferences.auto_start_live_monitor)
        auto_start_live_monitor.setToolTip(
            "Automatically listen on every available MIDI input when a mapping is loaded, so "
            "By Channel/Deck/Controller reflect live controller presses without opening Live "
            "Monitor and clicking Start monitoring. Turn off to require that manual step."
        )
        self._auto_start_live_monitor = auto_start_live_monitor
        reopen_last_files = QCheckBox("Reopen my last mapping and Controller Setup draft at launch")
        reopen_last_files.setChecked(preferences.reopen_last_files)
        reopen_last_files.setToolTip(
            "Load the mapping you had open last (with the same DJ software, without asking again) and "
            "the Controller Setup draft you saved or opened last, so you pick up where you left off."
        )
        self._reopen_last_files = reopen_last_files
        workspace_row = QWidget()
        workspace_layout = QHBoxLayout(workspace_row)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_label = QLabel(str(user_paths.workspace_dir()))
        workspace_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        workspace_label.setToolTip(
            "Your controller profiles, sync sets, Controller Setup drafts, saved logs and exports. "
            "Your Serato / Traktor mappings stay where your DJ software keeps them."
        )
        open_workspace = QPushButton("Open folder")
        open_workspace.clicked.connect(lambda: reveal_in_file_manager(user_paths.ensure_workspace()))
        workspace_layout.addWidget(workspace_label, 1)
        workspace_layout.addWidget(open_workspace)
        theme = QComboBox()
        theme.addItem("Follow system", "system")
        theme.addItem("Light", "light")
        theme.addItem("Dark", "dark")
        theme.setCurrentIndex(max(theme.findData(preferences.theme), 0))
        self._theme = theme

        log_level = QComboBox()
        log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        log_level.setCurrentText(preferences.log_level)
        self._log_level = log_level
        
        log_path = QLineEdit()
        log_path.setText(preferences.log_path)
        log_path.setPlaceholderText(str(default_log_path()))
        self._log_path = log_path
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_log_path)
        log_path_row = QHBoxLayout()
        log_path_row.addWidget(log_path, 1)
        log_path_row.addWidget(browse_button)

        setup_file = QLineEdit()
        setup_file.setText(preferences.controller_setup_default_file)
        setup_file.setPlaceholderText("None — start with an empty draft")
        setup_file.setToolTip(
            "Session JSON, Serato XML or Traktor TSI loaded into Controller Setup the first time "
            "that tab is shown, when its draft is still empty."
        )
        self._setup_file = setup_file
        setup_browse = QPushButton("Browse...")
        setup_browse.clicked.connect(self._browse_setup_file)
        setup_file_row = QHBoxLayout()
        setup_file_row.addWidget(setup_file, 1)
        setup_file_row.addWidget(setup_browse)

        general_tab = QWidget()
        policy_layout = QFormLayout(general_tab)
        policy_layout.addRow("Theme:", theme)
        policy_layout.addRow("Detection:", detection)
        policy_layout.addRow("Log level:", log_level)
        policy_layout.addRow("Log file path:", log_path_row)
        policy_layout.addRow("Controller Setup default file:", setup_file_row)
        policy_layout.addRow(routing)
        policy_layout.addRow(trust)
        policy_layout.addRow(auto_start_live_monitor)
        policy_layout.addRow(reopen_last_files)
        policy_layout.addRow("Your files folder:", workspace_row)

        controller_ids = {
            definition.plugin_id or definition.name
            for definition in catalog.all_controller_definitions()
        }
        self._controller_plugin_ids = controller_ids

        plugins_page = QWidget()
        plugins_layout = QVBoxLayout(plugins_page)
        hint = QLabel(
            "Disabled controllers are hidden from the mapping tabs, the Dashboard, "
            "and the Controller Images selector. Use View → Show all controllers "
            "to see every registered controller without changing these choices."
        )
        hint.setWordWrap(True)
        plugins_layout.addWidget(hint)
        for label, plugin_id in self._plugin_entries():
            checkbox = QCheckBox(label)
            checkbox.setChecked(preferences.is_enabled(plugin_id))
            self._plugin_checks[plugin_id] = checkbox
            plugins_layout.addWidget(checkbox)
        plugins_layout.addStretch(1)

        select_all = QPushButton("Enable all controllers")
        select_all.clicked.connect(lambda: self._set_all_controllers(True))
        select_none = QPushButton("Disable all controllers")
        select_none.clicked.connect(lambda: self._set_all_controllers(False))
        controller_buttons = QHBoxLayout()
        controller_buttons.addWidget(select_all)
        controller_buttons.addWidget(select_none)
        controller_buttons.addStretch(1)
        plugins_layout.addLayout(controller_buttons)

        # The plugin list grows with every new controller/software plugin
        # (11 controllers and counting) -- its own scroll area keeps the
        # dialog from growing ever taller as the catalog does, rather than
        # widening/heightening the whole window.
        plugins_scroll = QScrollArea()
        plugins_scroll.setWidget(plugins_page)
        plugins_scroll.setWidgetResizable(True)
        plugins_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        # Tabs, not a fixed side-by-side split: scales better as more
        # settings/plugins are added over time than either a single long
        # vertical stack or a two-column layout whose column widths would
        # need constant rebalancing.
        tabs = QTabWidget()
        self.tabs = tabs
        tabs.addTab(general_tab, "General")
        tabs.addTab(plugins_scroll, "Plugins")
        tabs.addTab(self._build_sync_tab(preferences), "Controller sync")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    _AUTO_PORT_LABEL = "Auto (match controller name)"

    def _build_sync_tab(self, preferences: PluginPreferences) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            "Initialization sets sent by the Sync button (menu bar and Live Monitor), one per "
            "controller. Record one in Controller Setup: name the controller, start learning, "
            "press the controls, then \"Save as controller sync set\"."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._sync_sets: list[ControllerSyncSet] = list(preferences.controller_sync_sets)
        self._sync_table = QTableWidget(0, 3)
        self._sync_table.setHorizontalHeaderLabels(["Controller", "Output port", "Messages"])
        self._sync_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._sync_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._sync_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        # Port names ("PIONEER DDJ-XP2 ...") need room to stay readable.
        self._sync_table.setMinimumWidth(480)
        self._sync_table.verticalHeader().setVisible(False)
        available = list_output_ports()
        for sync_set in self._sync_sets:
            row = self._sync_table.rowCount()
            self._sync_table.insertRow(row)
            self._sync_table.setItem(row, 0, QTableWidgetItem(sync_set.controller))
            port_combo = QComboBox()
            port_combo.addItem(self._AUTO_PORT_LABEL, "")
            for port in dict.fromkeys([*available, sync_set.output_port]):
                if port:
                    port_combo.addItem(port if port in available else f"{port} (not connected)", port)
            port_combo.setCurrentIndex(max(port_combo.findData(sync_set.output_port), 0))
            self._sync_table.setCellWidget(row, 1, port_combo)
            self._sync_table.setItem(row, 2, QTableWidgetItem(str(len(sync_set.messages))))
        layout.addWidget(self._sync_table, 1)
        remove_button = QPushButton("Remove selected set")
        remove_button.clicked.connect(self._remove_selected_sync_set)
        buttons = QHBoxLayout()
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _remove_selected_sync_set(self) -> None:
        rows = sorted({index.row() for index in self._sync_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._sync_table.removeRow(row)
            del self._sync_sets[row]

    def _edited_sync_sets(self) -> list[ControllerSyncSet]:
        edited = []
        for row, sync_set in enumerate(self._sync_sets):
            combo = self._sync_table.cellWidget(row, 1)
            port = combo.currentData() if isinstance(combo, QComboBox) else sync_set.output_port
            edited.append(dataclasses.replace(sync_set, output_port=port or ""))
        return edited

    @staticmethod
    def _plugin_entries() -> list[tuple[str, str]]:
        entries = [
            (f"Controller: {definition.name}", definition.plugin_id or definition.name)
            for definition in catalog.all_controller_definitions()
        ]
        entries.extend(
            (f"Software: {definition.name}", definition.plugin_id)
            for definition in software.all_definitions()
        )
        return entries

    def _set_all_controllers(self, enabled: bool) -> None:
        for plugin_id in self._controller_plugin_ids:
            checkbox = self._plugin_checks.get(plugin_id)
            if checkbox is not None:
                checkbox.setChecked(enabled)

    def _browse_log_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file location",
            self._log_path.text() or str(default_log_path()),
            "Log files (*.log);;All files (*)",
        )
        if path:
            self._log_path.setText(path)

    def _browse_setup_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Controller Setup default file",
            self._setup_file.text(),
            "Controller Setup session or mapping (*.json *.xml *.tsi);;All files (*)",
        )
        if path:
            self._setup_file.setText(path)

    def _save(self) -> None:
        self._preferences.theme = self._theme.currentData()
        self._preferences.detection_policy = self._detection.currentData()
        self._preferences.routing_enabled = self._routing.isChecked()
        self._preferences.trust_external_plugins = self._trust.isChecked()
        self._preferences.auto_start_live_monitor = self._auto_start_live_monitor.isChecked()
        self._preferences.reopen_last_files = self._reopen_last_files.isChecked()
        self._preferences.log_level = self._log_level.currentText()
        self._preferences.log_path = self._log_path.text().strip()
        self._preferences.controller_setup_default_file = self._setup_file.text().strip()
        for plugin_id, checkbox in self._plugin_checks.items():
            self._preferences.set_enabled(plugin_id, checkbox.isChecked())
        self._preferences.controller_sync_sets = self._edited_sync_sets()
        self.accept()


__all__ = ["PreferencesDialog"]
