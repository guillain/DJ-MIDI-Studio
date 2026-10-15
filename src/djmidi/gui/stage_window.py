"""Full-screen Stage Mode window (issue #230).

A separate top-level window, shown full screen, holding only a Controller
Emulator and a compact Live Monitor -- large, high-contrast, Esc to exit.
Session-only: MainWindow creates it from ``View → Stage Mode`` and drops it
when it closes; nothing about it is persisted.

The emulator is an ordinary ``ControllerEmulatorView`` instance, so it
reacts to live MIDI exactly like a Controller Emulator dock (MainWindow
feeds it through the same calls). The compact monitor shows the last few
events as one short line each (``djmidi.stage``), newest first; the full
Live Monitor dock keeps the detailed log.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui import help_texts
from djmidi.gui.controller_emulator import ControllerEmulatorView
from djmidi.gui.help_button import help_button
from djmidi.midi_io import MidiEvent
from djmidi.model import MidiConfig
from djmidi.stage import DEFAULT_MAX_LINES, StageLog, format_stage_line

# High contrast: pure black background, white text, one bright accent for
# the newest event. Set on this window only, so it overrides the app theme
# here without touching the main window. Font sizes are in points so they
# scale with the screen's DPI like the rest of the UI.
STAGE_STYLESHEET = """
QWidget#stageWindow, QWidget#stageWindow QWidget {
    background-color: #000000;
    color: #ffffff;
    font-size: 16pt;
}
QWidget#stageWindow QComboBox, QWidget#stageWindow QPushButton {
    border: 2px solid #ffffff;
    padding: 6px 12px;
}
QWidget#stageWindow QPushButton[compact="true"] {
    font-size: 12pt;
    padding: 0px;
}
QWidget#stageWindow QCheckBox::indicator {
    width: 22px;
    height: 22px;
}
QWidget#stageWindow QLabel#stageTitle {
    font-size: 20pt;
    font-weight: bold;
}
QWidget#stageWindow QLabel#stageLatest {
    color: #ffd400;
    font-size: 30pt;
    font-weight: bold;
}
QWidget#stageWindow QListWidget#stageLog {
    border: 2px solid #ffffff;
    font-size: 20pt;
}
"""

# The compact monitor column never gets narrower than this, so a long
# control name wraps onto two lines rather than being cut to a few letters.
_MONITOR_MIN_WIDTH = 320
# Same for the controller: out of full screen, a window dragged small stops
# while the schematic and its selectors stay usable (issue #282).
_EMULATOR_MIN_SIZE = (420, 320)


class StageWindow(QWidget):
    """The Stage Mode window. Emits ``closed`` once when it closes, whether
    from Esc, its Exit button, or the window manager."""

    closed = Signal()

    def __init__(
        self,
        config_provider: Callable[[], MidiConfig | None],
        initial_controller: str | None = None,
        max_lines: int = DEFAULT_MAX_LINES,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("stageWindow")
        self.setWindowTitle("DJ MIDI Studio — Stage Mode")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STAGE_STYLESHEET)
        self._log = StageLog(max_lines)

        self.emulator_view = ControllerEmulatorView(
            config_provider=config_provider, initial_controller=initial_controller
        )

        title = QLabel("Stage Mode")
        title.setObjectName("stageTitle")
        exit_button = QPushButton("Exit (Esc)")
        exit_button.clicked.connect(self.close)

        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(help_button(self, *help_texts.STAGE_MODE))
        header.addWidget(exit_button)

        monitor_title = QLabel("Live MIDI")
        monitor_title.setObjectName("stageTitle")
        self._latest_label = QLabel("Waiting for MIDI…")
        self._latest_label.setObjectName("stageLatest")
        self._latest_label.setWordWrap(True)
        self._log_list = QListWidget()
        self._log_list.setObjectName("stageLog")
        self._log_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._log_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        # Wrap long control names instead of scrolling sideways -- nobody
        # scrolls a list mid-set.
        self._log_list.setWordWrap(True)
        self._log_list.setSpacing(6)
        self._log_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        monitor = QWidget()
        monitor.setMinimumWidth(_MONITOR_MIN_WIDTH)
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(0, 0, 0, 0)
        monitor_layout.addWidget(monitor_title)
        monitor_layout.addWidget(self._latest_label)
        monitor_layout.addWidget(self._log_list, 1)

        self.emulator_view.setMinimumSize(*_EMULATOR_MIN_SIZE)
        body = QHBoxLayout()
        body.addWidget(self.emulator_view, 2)
        body.addWidget(monitor, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.addLayout(header)
        layout.addLayout(body, 1)

        # A window shortcut rather than keyPressEvent: the emulator's combo
        # or graphics view usually has focus and would swallow the key
        # before it reached this widget.
        self._exit_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._exit_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._exit_shortcut.activated.connect(self.close)

    def add_event(self, event: MidiEvent, hits: list[catalog.ControlInfo]) -> None:
        """Show one live event in the compact monitor."""
        line = format_stage_line(event, hits)
        self._log.add(line)
        self._latest_label.setText(line)
        self._log_list.clear()
        self._log_list.addItems(self._log.lines())

    def log_lines(self) -> list[str]:
        return self._log.lines()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        if event.isAccepted():
            self.closed.emit()
