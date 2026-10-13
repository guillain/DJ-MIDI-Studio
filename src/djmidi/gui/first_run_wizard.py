"""First-run setup wizard (issue #251): controllers, a Serato mapping, a sync set.

A thin ``QWizard`` over ``djmidi.first_run``: it detects connected controllers
from MIDI port names, lists Serato's standard MIDI folder (read-only), and
returns a ``FirstRunChoices`` that ``MainWindow`` applies once the wizard is
accepted. It never opens a MIDI port, sends MIDI or writes a file itself.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from djmidi.file_locations import software_mapping_dirs
from djmidi.first_run import (
    ControllerDetection,
    FirstRunChoices,
    detect_connected_controllers,
    find_serato_mappings,
)

_PATH_ROLE = Qt.ItemDataRole.UserRole


def _wrapped(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


class _ControllersPage(QWizardPage):
    def __init__(self, port_provider: Callable[[], list[str]]) -> None:
        super().__init__()
        self.setTitle("Your controllers")
        self.setSubTitle("Connected MIDI controllers recognized by their port name.")
        self._port_provider = port_provider
        self.controller_list = QListWidget()
        self.status_label = _wrapped("")
        self.rescan_button = QPushButton("Rescan")
        self.rescan_button.setToolTip("Look again after plugging a controller in.")
        self.rescan_button.clicked.connect(self.rescan)
        layout = QVBoxLayout(self)
        layout.addWidget(_wrapped("Select the profile to show on the Dashboard. Every detected profile stays available in the other tabs."))
        layout.addWidget(self.controller_list)
        layout.addWidget(self.status_label)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.rescan_button)
        layout.addLayout(row)
        self.detection = ControllerDetection()
        self.rescan()

    def rescan(self) -> None:
        try:
            ports = list(self._port_provider())
        except Exception:  # noqa: BLE001 - no MIDI backend must not break the wizard
            ports = []
        self.detection = detect_connected_controllers(ports)
        self.controller_list.clear()
        for detected in self.detection.controllers:
            item = QListWidgetItem(f"{detected.controller}  —  {', '.join(detected.ports)}")
            item.setData(_PATH_ROLE, detected.controller)
            item.setToolTip(detected.reason)
            self.controller_list.addItem(item)
        if self.detection.controllers:
            self.controller_list.setCurrentRow(0)
        notes = []
        if not ports:
            notes.append("No MIDI controller is connected. Plug one in and click <b>Rescan</b>, or continue.")
        elif not self.detection.controllers:
            notes.append("No connected port matches a controller profile.")
        if self.detection.unmatched_ports:
            notes.append(
                "Not recognized: " + ", ".join(self.detection.unmatched_ports)
                + ". <b>Controller Setup</b> can build a profile for it by learning its buttons."
            )
        self.status_label.setText("<br>".join(notes))

    def selected_controller(self) -> str | None:
        item = self.controller_list.currentItem()
        return item.data(_PATH_ROLE) if item is not None else None


class _MappingPage(QWizardPage):
    def __init__(self, home: Path | None) -> None:
        super().__init__()
        self.setTitle("Your Serato mapping")
        folder = software_mapping_dirs("serato", home)[0]
        self.setSubTitle("Open a MIDI mapping from Serato's MIDI folder to see and edit it.")
        self.mapping_list = QListWidget()
        none_item = QListWidgetItem("Don't open a mapping now")
        none_item.setData(_PATH_ROLE, None)
        self.mapping_list.addItem(none_item)
        self.candidates = find_serato_mappings(home)
        for candidate in self.candidates:
            item = QListWidgetItem(candidate.path.name)
            item.setData(_PATH_ROLE, str(candidate.path))
            item.setToolTip(str(candidate.path))
            self.mapping_list.addItem(item)
        # The newest mapping is the likely one; "Don't open" stays one click away.
        self.mapping_list.setCurrentRow(1 if self.candidates else 0)
        if self.candidates:
            note = f"Found in <i>{folder}</i>. Opening only reads the file; nothing is saved unless you save."
        else:
            note = f"No mapping found in <i>{folder}</i>. Use <b>File → Open</b> later to open one from anywhere."
        layout = QVBoxLayout(self)
        layout.addWidget(self.mapping_list)
        layout.addWidget(_wrapped(note))

    def selected_mapping(self) -> Path | None:
        item = self.mapping_list.currentItem()
        value = item.data(_PATH_ROLE) if item is not None else None
        return Path(value) if value else None


class _SyncPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Controller sync set")
        self.setSubTitle("Messages sent to your controllers at launch, e.g. to set pad modes or LEDs.")
        self.record_checkbox = QCheckBox("Start recording a sync set when this wizard closes")
        layout = QVBoxLayout(self)
        layout.addWidget(
            _wrapped(
                "When recording starts, press the controls to send at initialization, then click "
                "<b>■ Stop</b> next to <b>⟳ Sync</b> in the top-right corner. You can do this any time "
                "later with <b>● Rec</b>."
            )
        )
        layout.addWidget(self.record_checkbox)
        layout.addStretch(1)


class FirstRunWizard(QWizard):
    """Skippable first-launch setup; ``choices()`` holds the result."""

    def __init__(
        self,
        port_provider: Callable[[], list[str]],
        home: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to DJ MIDI Studio")
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setButtonText(QWizard.WizardButton.CancelButton, "Skip")
        self.setMinimumSize(560, 420)
        welcome = QWizardPage()
        welcome.setTitle("Welcome")
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.addWidget(
            _wrapped(
                "This short setup finds your controllers, offers to open your Serato MIDI mapping and "
                "to record a controller sync set.<br><br>Every step is optional: click <b>Skip</b> to "
                "close it. You can run it again from <b>Help → First-Run Setup…</b>."
            )
        )
        welcome_layout.addStretch(1)
        self.controllers_page = _ControllersPage(port_provider)
        self.mapping_page = _MappingPage(home)
        self.sync_page = _SyncPage()
        for page in (welcome, self.controllers_page, self.mapping_page, self.sync_page):
            self.addPage(page)

    def choices(self) -> FirstRunChoices:
        return FirstRunChoices(
            controller=self.controllers_page.selected_controller(),
            mapping=self.mapping_page.selected_mapping(),
            record_sync_set=self.sync_page.record_checkbox.isChecked(),
        )
