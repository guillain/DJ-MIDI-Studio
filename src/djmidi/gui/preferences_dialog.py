from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from djmidi import catalog, software
from djmidi.logging_config import default_log_path
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

        policy_box = QGroupBox("Integration policy")
        policy_layout = QFormLayout(policy_box)
        policy_layout.addRow("Detection:", detection)
        policy_layout.addRow("Log level:", log_level)
        policy_layout.addRow("Log file path:", log_path_row)
        policy_layout.addRow(routing)
        policy_layout.addRow(trust)

        controller_ids = {
            definition.plugin_id or definition.name
            for definition in catalog.all_controller_definitions()
        }
        self._controller_plugin_ids = controller_ids

        plugins_box = QGroupBox("Enabled plugins")
        plugins_layout = QVBoxLayout(plugins_box)
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

        select_all = QPushButton("Enable all controllers")
        select_all.clicked.connect(lambda: self._set_all_controllers(True))
        select_none = QPushButton("Disable all controllers")
        select_none.clicked.connect(lambda: self._set_all_controllers(False))
        controller_buttons = QHBoxLayout()
        controller_buttons.addWidget(select_all)
        controller_buttons.addWidget(select_none)
        controller_buttons.addStretch(1)
        plugins_layout.addLayout(controller_buttons)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(policy_box)
        layout.addWidget(plugins_box)
        layout.addWidget(buttons)

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

    def _save(self) -> None:
        self._preferences.detection_policy = self._detection.currentData()
        self._preferences.routing_enabled = self._routing.isChecked()
        self._preferences.trust_external_plugins = self._trust.isChecked()
        self._preferences.log_level = self._log_level.currentText()
        self._preferences.log_path = self._log_path.text().strip()
        for plugin_id, checkbox in self._plugin_checks.items():
            self._preferences.set_enabled(plugin_id, checkbox.isChecked())
        self.accept()


__all__ = ["PreferencesDialog"]
