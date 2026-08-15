from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
)

from djmidi import catalog, software
from djmidi.plugins import PluginPreferences


class PreferencesDialog(QDialog):
    """Safe, explicit preferences for plugins and integration policies."""

    def __init__(self, preferences: PluginPreferences, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DJ MIDI Studio Preferences")
        self._preferences = preferences
        self._plugin_checks: dict[str, QCheckBox] = {}

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

        policy_box = QGroupBox("Integration policy")
        policy_layout = QFormLayout(policy_box)
        policy_layout.addRow("Detection:", detection)
        policy_layout.addRow("Log level:", log_level)
        policy_layout.addRow(routing)
        policy_layout.addRow(trust)

        plugins_box = QGroupBox("Enabled plugins")
        plugins_layout = QVBoxLayout(plugins_box)
        for label, plugin_id in self._plugin_entries():
            checkbox = QCheckBox(label)
            checkbox.setChecked(preferences.is_enabled(plugin_id))
            self._plugin_checks[plugin_id] = checkbox
            plugins_layout.addWidget(checkbox)

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

    def _save(self) -> None:
        self._preferences.detection_policy = self._detection.currentData()
        self._preferences.routing_enabled = self._routing.isChecked()
        self._preferences.trust_external_plugins = self._trust.isChecked()
        self._preferences.log_level = self._log_level.currentText()
        for plugin_id, checkbox in self._plugin_checks.items():
            self._preferences.set_enabled(plugin_id, checkbox.isChecked())
        self.accept()


__all__ = ["PreferencesDialog"]
