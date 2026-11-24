"""Tests → Serato MIDI Learn…: teach Serato the notes the app sends on a
virtual bus, one function at a time (Qt-free steps in ``serato_learn.py``).

The window sends nothing until the DJ asks: Send starts a countdown, leaving
time to click the function in Serato, then one Note On/Off goes to the bus and
the window watches the Live Monitor for it coming back (an IAC bus echoes)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from djmidi import midi_io
from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import SERATO_LEARN
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.serato_learn import (
    COUNTDOWN_S,
    NOTE_LENGTH_MS,
    STEPS,
    default_port,
    is_echo,
)

Sender = Callable[..., None]  # midi_io.send_midi_message's keyword arguments
ECHO_WAIT_MS = 1000
_LOGGER = logging.getLogger(__name__)

_translate = translator("SeratoLearn")


class SeratoLearnDialog(QDialog):
    def __init__(
        self,
        outputs: list[str],
        parent=None,
        send: Sender | None = None,
        ensure_listening: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Serato MIDI Learn"))
        self._send = send or midi_io.send_midi_message
        self._ensure_listening = ensure_listening
        self.index = 0
        self.remaining = 0
        self.waiting_echo = False
        self.heard: set[int] = set()
        self.sent: set[int] = set()

        intro = QLabel(
            self.tr(
                "Macros that drive Serato through a virtual bus only work once Serato knows their notes. "
                "In Serato: enable the bus in Setup → MIDI, then switch MIDI mode on (the MIDI button at the "
                "top). Here, click Send, then click the function in Serato before the countdown ends and "
                "stay in Serato. When every step is done, save the MIDI preset in Serato."
            )
        )
        intro.setWordWrap(True)
        self.port_combo = QComboBox()
        self.port_combo.addItems(outputs)
        port = default_port(outputs)
        if port:
            self.port_combo.setCurrentText(port)
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel(self.tr("Bus:")))
        port_row.addWidget(self.port_combo, 1)

        self.step_list = QListWidget()
        usable_minimum(self.step_list, 220, 200)
        self.step_list.currentRowChanged.connect(self._on_row_changed)
        self.title = QLabel("")
        font = self.title.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setWordWrap(True)
        self.instruction = QLabel("")
        self.instruction.setWordWrap(True)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.send_button = QPushButton(self.tr("Send"))
        self.send_button.setDefault(True)
        self.send_button.setToolTip(self.tr("Starts the countdown, then sends this step's note to the bus"))
        self.send_button.clicked.connect(self.start_countdown)
        self.back_button = QPushButton(self.tr("Back"))
        self.back_button.setAutoDefault(False)
        self.back_button.clicked.connect(lambda: self.select(self.index - 1))
        self.next_button = QPushButton(self.tr("Next"))
        self.next_button.setAutoDefault(False)
        self.next_button.clicked.connect(lambda: self.select(self.index + 1))
        buttons = QHBoxLayout()
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        buttons.addStretch(1)

        detail = QVBoxLayout()
        detail.addWidget(self.title)
        detail.addWidget(self.instruction)
        detail.addLayout(buttons)
        detail.addWidget(self.status)
        detail.addStretch(1)
        body = QHBoxLayout()
        body.addWidget(self.step_list)
        body.addLayout(detail, 1)

        close_button = QPushButton(self.tr("Close"))
        close_button.setAutoDefault(False)
        close_button.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *SERATO_LEARN))
        bottom.addStretch(1)
        bottom.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(port_row)
        layout.addLayout(body, 1)
        layout.addLayout(bottom)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._echo_timer = QTimer(self)
        self._echo_timer.setSingleShot(True)
        self._echo_timer.timeout.connect(self._echo_missed)

        for step in STEPS:
            self.step_list.addItem(step.label(_translate))
        self.select(0)
        fit_to_screen(self, 760, 520)
        keep_wrapped_text_visible(self)

    # --- steps ------------------------------------------------------------------

    @property
    def step(self):
        return STEPS[self.index]

    def select(self, index: int) -> None:
        index = max(0, min(index, len(STEPS) - 1))
        if self.step_list.currentRow() != index:
            self.step_list.setCurrentRow(index)  # → _on_row_changed
        else:
            self._on_row_changed(index)

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        self._cancel()
        self.index = row
        step = self.step
        name = step.label(_translate)
        self.title.setText(self.tr("Step {number} of {count}: {name}").format(
            number=row + 1, count=len(STEPS), name=name))
        self.instruction.setText(
            self.tr(
                "Click Send, then within {seconds} seconds click {name} in Serato and stay there. "
                "The note (channel {channel}, note {note}) leaves on its own."
            ).format(seconds=COUNTDOWN_S, name=name, channel=step.channel, note=step.note)
        )
        self.back_button.setEnabled(row > 0)
        self.next_button.setEnabled(row < len(STEPS) - 1)
        self.send_button.setEnabled(bool(self.port_combo.currentText()))
        if not self.port_combo.currentText():
            self.status.setText(self.tr("No MIDI output: turn the IAC bus on in Audio MIDI Setup, then reopen."))
        else:
            self.status.setText("")

    def _refresh_marks(self) -> None:
        for row, step in enumerate(STEPS):
            mark = "✓ " if row in self.heard else "• " if row in self.sent else ""
            self.step_list.item(row).setText(mark + step.label(_translate))

    # --- sending ----------------------------------------------------------------

    def start_countdown(self) -> None:
        if not self.port_combo.currentText():
            return
        if self._ensure_listening is not None:
            self._ensure_listening()
        self.remaining = COUNTDOWN_S
        self.send_button.setEnabled(False)
        self._show_countdown()
        self._timer.start()

    def _show_countdown(self) -> None:
        self.status.setText(self.tr("Click {name} in Serato now: the note leaves in {seconds} s").format(
            name=self.step.label(_translate), seconds=self.remaining))

    def _tick(self) -> None:
        self.remaining -= 1
        if self.remaining > 0:
            self._show_countdown()
            return
        self._timer.stop()
        self.send_now()

    def send_now(self) -> bool:
        """Sends this step's Note On, then its Note Off; False when the bus refused."""
        step, port = self.step, self.port_combo.currentText()
        try:
            self._send(output_port_name=port, event_type="Note On", channel_1_based=step.channel,
                       data1=step.note, data2=127)
        except Exception as error:  # noqa: BLE001 -- shown, nothing else to do
            self.status.setText(self.tr("Could not send to {port}: {error}").format(port=port, error=error))
            self.send_button.setEnabled(True)
            return False
        self.sent.add(self.index)
        self.waiting_echo = True
        self._echo_timer.start(ECHO_WAIT_MS)
        QTimer.singleShot(NOTE_LENGTH_MS, lambda s=step, p=port: self._note_off(s, p))
        self.status.setText(self.tr("Sent: channel {channel}, note {note}. Listening for it on the bus…").format(
            channel=step.channel, note=step.note))
        self._refresh_marks()
        return True

    def _note_off(self, step, port: str) -> None:
        try:
            self._send(output_port_name=port, event_type="Note Off", channel_1_based=step.channel,
                       data1=step.note, data2=0)
        except Exception:
            _LOGGER.warning("Serato learn: Note Off to %r failed", port, exc_info=True)

    def feed_event(self, event) -> bool:
        """Every live event while the window is open; True when it is the
        note just sent, coming back through the bus."""
        if not self.waiting_echo or not is_echo(self.step, event, self.port_combo.currentText()):
            return False
        self._echo_timer.stop()
        self.waiting_echo = False
        self.heard.add(self.index)
        self._refresh_marks()
        done = self.index == len(STEPS) - 1
        message = self.tr("Received on the bus ✓ — Serato got it too if it was in MIDI mode.")
        if done:
            message += " " + self.tr("All steps sent: save the MIDI preset in Serato.")
            self.send_button.setEnabled(True)
            self.status.setText(message)
        else:
            self.select(self.index + 1)
            self.status.setText(message)
        return True

    def _echo_missed(self) -> None:
        self.waiting_echo = False
        self.send_button.setEnabled(True)
        self.status.setText(
            self.tr(
                "Sent, but not seen coming back on the bus. Check the bus is on in Audio MIDI Setup and that "
                "the Live Monitor listens to it; Serato may still have learned it."
            )
        )

    def _cancel(self) -> None:
        self._timer.stop()
        self._echo_timer.stop()
        self.waiting_echo = False

    def done(self, result: int) -> None:
        self._cancel()
        super().done(result)
