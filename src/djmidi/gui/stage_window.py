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

Above it, the set prepared in Music Library → Set (issue #366): position,
current and next track with BPM / key / energy, and whether the mix into
the next one is compatible. ◀ / ▶ (or PageUp / PageDown, what a presenter
remote sends) move through it; the app can't tell which track the DJ
software is playing, so moving on is the DJ's click.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui import help_texts
from djmidi.gui.controller_emulator import ControllerEmulatorView
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.gui.window_size import keep_wrapped_text_visible
from djmidi.library.set_prep import STATUS_INCOMPATIBLE, STATUS_OK, SetTrack, Transition
from djmidi.midi_io import MidiEvent
from djmidi.model import MidiConfig
from djmidi.stage import (
    DEFAULT_MAX_LINES,
    StageLog,
    format_stage_line,
    stage_set_view,
    suggestion_line,
)

# The prepared set's tracks and transitions, read again on every move.
_LOGGER = logging.getLogger(__name__)
SetProvider = Callable[[], tuple[Sequence[SetTrack], Sequence[Transition]]]
# (current track, the set's paths) -> library tracks to suggest after it.
SuggestionProvider = Callable[[SetTrack, set[str]], Sequence[SetTrack]]

# ON/OFF and the raw trigger come from Qt-free djmidi.stage (issue #337).
_stage_translate = translator("Stage")

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
QWidget#stageWindow QLabel#stageCurrent {
    font-size: 28pt;
    font-weight: bold;
}
QWidget#stageWindow QLabel#stageTransition[status="ok"] {
    color: #3ee07a;
}
QWidget#stageWindow QLabel#stageTransition[status="incompatible"] {
    color: #ff5a4f;
    font-weight: bold;
}
QWidget#stageWindow QLabel#stageTransition[status="unknown"] {
    color: #bbbbbb;
}
QWidget#stageWindow QLabel#stageSuggestions {
    color: #bbbbbb;
    font-size: 15pt;
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
# The set panel scrolls below this height instead of growing the window.
_SET_MIN_HEIGHT = 120


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
        set_provider: SetProvider | None = None,
        set_index: int = 0,
        suggestion_provider: SuggestionProvider | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("stageWindow")
        self.setWindowTitle(self.tr("DJ MIDI Studio — Stage Mode"))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STAGE_STYLESHEET)
        self._log = StageLog(max_lines)

        self.emulator_view = ControllerEmulatorView(
            config_provider=config_provider, initial_controller=initial_controller
        )

        title = QLabel(self.tr("Stage Mode"))
        title.setObjectName("stageTitle")
        exit_button = QPushButton(self.tr("Exit (Esc)"))
        exit_button.clicked.connect(self.close)

        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(help_button(self, *help_texts.STAGE_MODE))
        header.addWidget(exit_button)

        self._set_provider = set_provider
        self.set_index = set_index
        self._set_title = QLabel()
        self._set_title.setObjectName("stageTitle")
        self._set_current = QLabel()
        self._set_current.setObjectName("stageCurrent")
        self._set_current.setWordWrap(True)
        self._set_details = QLabel()
        self._set_details.setWordWrap(True)
        self._set_next = QLabel()
        self._set_next.setWordWrap(True)
        self._set_transition = QLabel()
        self._set_transition.setObjectName("stageTransition")
        self._set_transition.setWordWrap(True)
        self._suggestion_provider = suggestion_provider
        self._set_suggestions = QLabel()
        self._set_suggestions.setObjectName("stageSuggestions")
        self._set_suggestions.setWordWrap(True)
        self._set_previous_button = QPushButton(self.tr("◀ Previous"))
        self._set_previous_button.clicked.connect(lambda: self.move_in_set(-1))
        self._set_next_button = QPushButton(self.tr("Next ▶"))
        self._set_next_button.clicked.connect(lambda: self.move_in_set(1))
        set_buttons = QHBoxLayout()
        set_buttons.addWidget(self._set_previous_button)
        set_buttons.addWidget(self._set_next_button)
        self.set_panel = QWidget()
        set_layout = QVBoxLayout(self.set_panel)
        set_layout.setContentsMargins(0, 0, 0, 12)
        for widget in (self._set_title, self._set_current, self._set_details, self._set_next, self._set_transition):
            set_layout.addWidget(widget)
        set_layout.addLayout(set_buttons)
        set_layout.addWidget(self._set_suggestions)

        monitor_title = QLabel(self.tr("Live MIDI"))
        monitor_title.setObjectName("stageTitle")
        self._latest_label = QLabel(self.tr("Waiting for MIDI…"))
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
        # Scrolls rather than squeezing the live monitor or clipping a long
        # title in a small window (issue #19's rule).
        self._set_scroll = QScrollArea()
        self._set_scroll.setWidget(self.set_panel)
        self._set_scroll.setWidgetResizable(True)
        self._set_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._set_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._set_scroll.setMinimumHeight(_SET_MIN_HEIGHT)
        monitor_layout.addWidget(self._set_scroll)
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
        self._set_shortcuts = []
        for key, step in ((Qt.Key.Key_PageDown, 1), (Qt.Key.Key_PageUp, -1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda step=step: self.move_in_set(step))
            self._set_shortcuts.append(shortcut)
        self._set_scroll.setVisible(set_provider is not None)
        self.refresh_set()
        keep_wrapped_text_visible(self)

    # --- the prepared set (issue #366) -----------------------------------------

    def _set(self) -> tuple[Sequence[SetTrack], Sequence[Transition]]:
        return self._set_provider() if self._set_provider is not None else ((), ())

    def refresh_set(self) -> None:
        tracks, transitions = self._set()
        if tracks:
            self.set_index = max(0, min(self.set_index, len(tracks) - 1))
        view = stage_set_view(tracks, transitions, self.set_index, _stage_translate)
        self._set_previous_button.setEnabled(view is not None and self.set_index > 0)
        self._set_next_button.setEnabled(view is not None and self.set_index < len(tracks) - 1)
        if view is None:
            self._set_title.setText(self.tr("Set"))
            self._set_current.setText("")
            self._set_details.setText(self.tr("No set prepared: build one in Music Library → Set."))
            for label in (self._set_next, self._set_transition, self._set_suggestions):
                label.setText("")
            self._set_suggestions.setVisible(False)
            return
        self._set_title.setText(view.position)
        self._set_current.setText(view.current)
        self._set_details.setText(view.current_details)
        self._set_next.setText(view.next)
        self._set_transition.setText(view.transition)
        status = {STATUS_OK: "ok", STATUS_INCOMPATIBLE: "incompatible"}.get(view.status, "unknown")
        self._set_transition.setProperty("status", status)
        self._set_transition.style().unpolish(self._set_transition)
        self._set_transition.style().polish(self._set_transition)
        self._show_suggestions(tracks[self.set_index], {track.path for track in tracks})

    def _show_suggestions(self, current: SetTrack, set_paths: set[str]) -> None:
        """Compatible library tracks after the current one, in case the
        night leaves the prepared set (phase 5 item 3)."""
        if self._suggestion_provider is None:
            self._set_suggestions.setVisible(False)
            return
        try:
            suggestions = list(self._suggestion_provider(current, set_paths))
        except Exception:
            _LOGGER.warning("Could not compute Stage Mode suggestions", exc_info=True)
            suggestions = []
        if not current.bpm or not current.camelot_key:
            text = self.tr("No suggestions: this track has no BPM or key tag.")
        elif not suggestions:
            text = self.tr("No other compatible track in the library.")
        else:
            lines = [self.tr("Off the plan, these mix well:")]
            lines += [f"• {suggestion_line(track, _stage_translate)}" for track in suggestions]
            text = "\n".join(lines)
        self.set_suggestions_text = text
        self._set_suggestions.setText(text)
        self._set_suggestions.setVisible(True)

    def move_in_set(self, step: int) -> int:
        """Moves the current track by `step`; returns the new index."""
        tracks, _transitions = self._set()
        if tracks:
            self.set_index = max(0, min(self.set_index + step, len(tracks) - 1))
        self.refresh_set()
        return self.set_index

    def add_event(self, event: MidiEvent, hits: list[catalog.ControlInfo]) -> None:
        """Show one live event in the compact monitor."""
        line = format_stage_line(event, hits, _stage_translate)
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
