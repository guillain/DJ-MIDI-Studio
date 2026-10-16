from __future__ import annotations

import dataclasses

from PySide6.QtCore import Signal
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
from djmidi.gui.sync_set_editor import SyncSetEditorDialog
from djmidi.i18n import LANGUAGE_CHOICES
from djmidi.logging_config import default_log_path
from djmidi.midi_io import list_output_ports
from djmidi.plugins import PluginPreferences

# Controller sync tab columns: Controller, Scene, Output port, Messages.
_PORT_COLUMN = 2
_MESSAGES_COLUMN = 3


class PreferencesDialog(QDialog):
    """Safe, explicit preferences for plugins and integration policies."""

    # Workspace backup/restore (issue #187), handled by MainWindow.
    backupRequested = Signal()
    restoreRequested = Signal()

    def __init__(self, preferences: PluginPreferences, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("DJ MIDI Studio Preferences"))
        self._preferences = preferences
        self._plugin_checks: dict[str, QCheckBox] = {}
        self._controller_plugin_ids: set[str] = set()

        detection = QComboBox()
        detection.addItem(self.tr("Ask before enabling"), "ask")
        detection.addItem(self.tr("Suggest detected integration"), "suggest")
        detection.setCurrentIndex(max(detection.findData(preferences.detection_policy), 0))
        self._detection = detection

        routing = QCheckBox(self.tr("Enable MIDI routing policies"))
        routing.setChecked(preferences.routing_enabled)
        self._routing = routing
        trust = QCheckBox(self.tr("Trust external plugins"))
        trust.setChecked(preferences.trust_external_plugins)
        self._trust = trust
        auto_start_live_monitor = QCheckBox(self.tr("Auto-start Live Monitor when a mapping is loaded"))
        auto_start_live_monitor.setChecked(preferences.auto_start_live_monitor)
        auto_start_live_monitor.setToolTip(
            self.tr(
                "Automatically listen on every available MIDI input when a mapping is loaded, so "
                "By Channel/Deck/Controller reflect live controller presses without opening Live "
                "Monitor and clicking Start monitoring. Turn off to require that manual step."
            )
        )
        self._auto_start_live_monitor = auto_start_live_monitor
        reopen_last_files = QCheckBox(self.tr("Reopen my last mapping and Controller Setup draft at launch"))
        reopen_last_files.setChecked(preferences.reopen_last_files)
        reopen_last_files.setToolTip(
            self.tr(
                "Load the mapping you had open last (with the same DJ software, without asking again) and "
                "the Controller Setup draft you saved or opened last, so you pick up where you left off."
            )
        )
        self._reopen_last_files = reopen_last_files
        auto_sync_on_startup = QCheckBox(self.tr("Sync controllers at launch"))
        auto_sync_on_startup.setChecked(preferences.auto_sync_on_startup)
        auto_sync_on_startup.setToolTip(
            self.tr(
                "Send each connected controller its recorded initialization set (● Rec / Controller "
                "Setup) when the app starts, as if you had clicked ⟳ Sync."
            )
        )
        self._auto_sync_on_startup = auto_sync_on_startup
        auto_sync_on_plug_in = QCheckBox(self.tr("Sync a controller when it is plugged in"))
        auto_sync_on_plug_in.setChecked(preferences.auto_sync_on_plug_in)
        auto_sync_on_plug_in.setToolTip(
            self.tr(
                "Watch for controllers being connected and send each one its recorded initialization "
                "set once, as soon as it appears. A controller that stays connected is not re-sent; "
                "unplugging and replugging it sends the set again."
            )
        )
        self._auto_sync_on_plug_in = auto_sync_on_plug_in
        sync_on_scene_switch = QCheckBox(self.tr("Sync when switching scene"))
        sync_on_scene_switch.setChecked(preferences.sync_on_scene_switch)
        sync_on_scene_switch.setToolTip(
            self.tr(
                "Send each connected controller its set for the new scene as soon as you pick another "
                "scene beside ⟳ Sync. Off: switching scenes sends nothing until you click ⟳ Sync."
            )
        )
        self._sync_on_scene_switch = sync_on_scene_switch
        check_for_updates = QCheckBox(self.tr("Check for a new version at launch"))
        check_for_updates.setChecked(preferences.check_for_updates)
        check_for_updates.setToolTip(
            self.tr(
                "Once a day at most, ask GitHub whether a newer DJ MIDI Studio release exists and show "
                "a notice in the status bar. Nothing is downloaded or installed; offline is silent."
            )
        )
        self._check_for_updates = check_for_updates
        workspace_row = QWidget()
        workspace_rows = QVBoxLayout(workspace_row)
        workspace_rows.setContentsMargins(0, 0, 0, 0)
        workspace_layout = QHBoxLayout()
        # A read-only field on its own line, buttons below: as a label beside
        # the buttons, a long path set the dialog's minimum width (1118 px in
        # English, 1243 in French, past a 1000 px screen; issue #290).
        workspace_label = QLineEdit(str(user_paths.workspace_dir()))
        workspace_label.setReadOnly(True)
        workspace_label.setObjectName("workspacePath")
        workspace_label.setCursorPosition(0)
        workspace_label.setToolTip(
            self.tr(
                "Your controller profiles, sync sets, Controller Setup drafts, saved logs and exports. "
                "Your Serato / Traktor mappings stay where your DJ software keeps them."
            )
        )
        open_workspace = QPushButton(self.tr("Open folder"))
        open_workspace.clicked.connect(lambda: reveal_in_file_manager(user_paths.ensure_workspace()))
        workspace_rows.addWidget(workspace_label)
        workspace_rows.addLayout(workspace_layout)
        workspace_layout.addWidget(open_workspace)
        backup_workspace = QPushButton(self.tr("Back up..."))
        backup_workspace.setToolTip(self.tr("Save your files and preferences in one zip (File → Back Up Workspace)."))
        backup_workspace.clicked.connect(self.backupRequested.emit)
        restore_workspace = QPushButton(self.tr("Restore..."))
        restore_workspace.setToolTip(self.tr("Restore a workspace backup, after confirming what it overwrites."))
        restore_workspace.clicked.connect(self.restoreRequested.emit)
        workspace_layout.addWidget(backup_workspace)
        workspace_layout.addWidget(restore_workspace)
        workspace_layout.addStretch(1)
        self._backup_button = backup_workspace
        self._restore_button = restore_workspace
        theme = QComboBox()
        theme.addItem(self.tr("Follow system"), "system")
        theme.addItem(self.tr("Light"), "light")
        theme.addItem(self.tr("Dark"), "dark")
        theme.setCurrentIndex(max(theme.findData(preferences.theme), 0))
        self._theme = theme
        # Issue #263: language names stay in their own language ("Français"),
        # only "System" is translated; applied at the next launch.
        language = QComboBox()
        for value, label in LANGUAGE_CHOICES:
            language.addItem(self.tr("System") if value == "system" else label, value)
        language.setCurrentIndex(max(language.findData(preferences.language), 0))
        language.setToolTip(self.tr("Interface language. Takes effect the next time DJ MIDI Studio starts."))
        self._language = language

        log_level = QComboBox()
        log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        log_level.setCurrentText(preferences.log_level)
        self._log_level = log_level
        
        log_path = QLineEdit()
        log_path.setText(preferences.log_path)
        log_path.setPlaceholderText(str(default_log_path()))
        self._log_path = log_path
        browse_button = QPushButton(self.tr("Browse..."))
        browse_button.clicked.connect(self._browse_log_path)
        log_path_row = QHBoxLayout()
        log_path_row.addWidget(log_path, 1)
        log_path_row.addWidget(browse_button)

        setup_file = QLineEdit()
        setup_file.setText(preferences.controller_setup_default_file)
        setup_file.setPlaceholderText(self.tr("None — start with an empty draft"))
        setup_file.setToolTip(
            self.tr(
                "Session JSON, Serato XML or Traktor TSI loaded into Controller Setup the first time "
                "that tab is shown, when its draft is still empty."
            )
        )
        self._setup_file = setup_file
        setup_browse = QPushButton(self.tr("Browse..."))
        setup_browse.clicked.connect(self._browse_setup_file)
        setup_file_row = QHBoxLayout()
        setup_file_row.addWidget(setup_file, 1)
        setup_file_row.addWidget(setup_browse)

        general_tab = QWidget()
        policy_layout = QFormLayout(general_tab)
        policy_layout.addRow(self.tr("Theme:"), theme)
        policy_layout.addRow(self.tr("Language:"), language)
        policy_layout.addRow(self.tr("Detection:"), detection)
        policy_layout.addRow(self.tr("Log level:"), log_level)
        policy_layout.addRow(self.tr("Log file path:"), log_path_row)
        policy_layout.addRow(self.tr("Controller Setup default file:"), setup_file_row)
        policy_layout.addRow(routing)
        policy_layout.addRow(trust)
        policy_layout.addRow(auto_start_live_monitor)
        policy_layout.addRow(reopen_last_files)
        policy_layout.addRow(auto_sync_on_startup)
        policy_layout.addRow(auto_sync_on_plug_in)
        policy_layout.addRow(sync_on_scene_switch)
        policy_layout.addRow(check_for_updates)
        policy_layout.addRow(self.tr("Your files folder:"), workspace_row)

        controller_ids = {
            definition.plugin_id or definition.name
            for definition in catalog.all_controller_definitions()
        }
        self._controller_plugin_ids = controller_ids

        plugins_page = QWidget()
        plugins_layout = QVBoxLayout(plugins_page)
        hint = QLabel(
            self.tr(
                "Disabled controllers are hidden from the mapping tabs, the Dashboard, "
                "and the Controller Images selector. Use View → Show all controllers "
                "to see every registered controller without changing these choices."
            )
        )
        hint.setWordWrap(True)
        plugins_layout.addWidget(hint)
        for label, plugin_id in self._plugin_entries():
            checkbox = QCheckBox(label)
            checkbox.setChecked(preferences.is_enabled(plugin_id))
            self._plugin_checks[plugin_id] = checkbox
            plugins_layout.addWidget(checkbox)
        plugins_layout.addStretch(1)

        select_all = QPushButton(self.tr("Enable all controllers"))
        select_all.clicked.connect(lambda: self._set_all_controllers(True))
        select_none = QPushButton(self.tr("Disable all controllers"))
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
        # Each tab keeps its English title as data: MainWindow opens one by
        # that key, which must not depend on the interface language.
        for page, key, title in (
            (general_tab, "General", self.tr("General")),
            (plugins_scroll, "Plugins", self.tr("Plugins")),
            (self._build_sync_tab(preferences), "Controller sync", self.tr("Controller sync")),
        ):
            tabs.tabBar().setTabData(tabs.addTab(page, title), key)

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
            self.tr(
                "Initialization sets sent by the Sync button (menu bar and Live Monitor), one per "
                "controller and scene. ⟳ Sync sends each controller its set for the scene chosen "
                "beside it in the menu bar, or its Default set when it has none for that scene. "
                "Record one with ● Rec (into the active scene), or in Controller Setup: name the "
                "controller, start learning, press the controls, then \"Save as controller sync set\"."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._sync_sets: list[ControllerSyncSet] = list(preferences.controller_sync_sets)
        self._sync_table = QTableWidget(0, 4)
        self._sync_table.setHorizontalHeaderLabels(
            [self.tr("Controller"), self.tr("Scene"), self.tr("Output port"), self.tr("Messages")]
        )
        self._sync_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._sync_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._sync_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_PORT_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_MESSAGES_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        # Port names ("PIONEER DDJ-XP2 ...") need room to stay readable.
        self._sync_table.setMinimumWidth(480)
        self._sync_table.verticalHeader().setVisible(False)
        available = list_output_ports()
        for sync_set in self._sync_sets:
            row = self._sync_table.rowCount()
            self._sync_table.insertRow(row)
            self._sync_table.setItem(row, 0, QTableWidgetItem(sync_set.controller))
            self._sync_table.setItem(row, 1, QTableWidgetItem(sync_set.scene))
            port_combo = QComboBox()
            port_combo.addItem(self.tr("Auto (match controller name)"), "")
            for port in dict.fromkeys([*available, sync_set.output_port]):
                if port:
                    port_combo.addItem(port if port in available else f"{port} (not connected)", port)
            port_combo.setCurrentIndex(max(port_combo.findData(sync_set.output_port), 0))
            self._sync_table.setCellWidget(row, _PORT_COLUMN, port_combo)
            self._sync_table.setItem(row, _MESSAGES_COLUMN, QTableWidgetItem(str(len(sync_set.messages))))
        self._sync_table.cellDoubleClicked.connect(lambda row, _column: self._edit_sync_set(row))
        layout.addWidget(self._sync_table, 1)
        edit_button = QPushButton(self.tr("Edit messages…"))
        edit_button.setToolTip(self.tr("List, edit, delete or reorder the selected set's messages"))
        edit_button.clicked.connect(self._edit_selected_sync_set)
        remove_button = QPushButton(self.tr("Remove selected set"))
        remove_button.clicked.connect(self._remove_selected_sync_set)
        buttons = QHBoxLayout()
        buttons.addWidget(edit_button)
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _remove_selected_sync_set(self) -> None:
        rows = sorted({index.row() for index in self._sync_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._sync_table.removeRow(row)
            del self._sync_sets[row]

    def _edit_selected_sync_set(self) -> None:
        rows = sorted({index.row() for index in self._sync_table.selectedIndexes()})
        if rows:
            self._edit_sync_set(rows[0])

    def _edit_sync_set(self, row: int) -> None:
        """Opens the message editor for one set. Its result only replaces the
        set in this dialog; Preferences' own Save persists it, Cancel drops it."""
        if not 0 <= row < len(self._sync_sets):
            return
        # Test sends follow the port currently chosen in the combo.
        current = self._edited_sync_sets()[row]
        editor = SyncSetEditorDialog(current, list_output_ports(), parent=self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        self._sync_sets[row] = dataclasses.replace(self._sync_sets[row], messages=editor.edited_sync_set().messages)
        self._sync_table.setItem(row, _MESSAGES_COLUMN, QTableWidgetItem(str(len(self._sync_sets[row].messages))))

    def _edited_sync_sets(self) -> list[ControllerSyncSet]:
        edited = []
        for row, sync_set in enumerate(self._sync_sets):
            combo = self._sync_table.cellWidget(row, _PORT_COLUMN)
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
        self._preferences.language = self._language.currentData()
        self._preferences.detection_policy = self._detection.currentData()
        self._preferences.routing_enabled = self._routing.isChecked()
        self._preferences.trust_external_plugins = self._trust.isChecked()
        self._preferences.auto_start_live_monitor = self._auto_start_live_monitor.isChecked()
        self._preferences.reopen_last_files = self._reopen_last_files.isChecked()
        self._preferences.auto_sync_on_startup = self._auto_sync_on_startup.isChecked()
        self._preferences.auto_sync_on_plug_in = self._auto_sync_on_plug_in.isChecked()
        self._preferences.sync_on_scene_switch = self._sync_on_scene_switch.isChecked()
        self._preferences.check_for_updates = self._check_for_updates.isChecked()
        self._preferences.log_level = self._log_level.currentText()
        self._preferences.log_path = self._log_path.text().strip()
        self._preferences.controller_setup_default_file = self._setup_file.text().strip()
        for plugin_id, checkbox in self._plugin_checks.items():
            self._preferences.set_enabled(plugin_id, checkbox.isChecked())
        self._preferences.controller_sync_sets = self._edited_sync_sets()
        self.accept()


__all__ = ["PreferencesDialog"]
