"""View → MIDI Latency Test… (issue #255): the GUI around ``djmidi.midi_latency``.

Pick an output and an input port, send N pings and read min / median / max /
jitter. The timing loop runs on a worker thread (a Qt timer would add its own
millisecond-plus granularity to every measurement); results come back through
a queue the dialog drains on a short timer, so no Qt object is touched off the
main thread. The ports and the thread start are injectable for tests.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import MIDI_LATENCY
from djmidi.gui.window_size import fit_to_screen, keep_wrapped_text_visible
from djmidi.midi_io import list_input_ports, list_output_ports
from djmidi.midi_latency import (
    ECHO_WARNING,
    MAX_PINGS,
    LatencyConfig,
    LatencyProbe,
    LatencyStats,
    PingResult,
    ReceiveFn,
    SendFn,
    format_stats,
    open_port_pair,
    run_probe,
)

_LOGGER = logging.getLogger(__name__)

PortPairFactory = Callable[[str, str], AbstractContextManager[tuple[SendFn, ReceiveFn]]]
ThreadStarter = Callable[[Callable[[], None]], None]


def _start_daemon_thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name="midi-latency", daemon=True).start()


def default_input_for(output: str, inputs: list[str]) -> str | None:
    """The input to preselect for ``output``: the port of the same name (an
    IAC bus or a virtual cable lists both sides under one name), if any."""
    return output if output in inputs else None


_MIN_WIDTH = 460


class MidiLatencyDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        port_pair_factory: PortPairFactory = open_port_pair,
        start_thread: ThreadStarter = _start_daemon_thread,
        list_outputs: Callable[[], list[str]] = list_output_ports,
        list_inputs: Callable[[], list[str]] = list_input_ports,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("MIDI Latency Test"))
        fit_to_screen(self, 560, 560)
        # Wide enough that the echo warning wraps on a few lines, keeping the
        # minimum height within a 900x600 screen (issue #282).
        self.setMinimumWidth(_MIN_WIDTH)
        self._port_pair_factory = port_pair_factory
        self._start_thread = start_thread
        self._list_outputs = list_outputs
        self._list_inputs = list_inputs
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._stop = threading.Event()
        self._running = False
        self.results: list[PingResult] = []
        self.last_stats: LatencyStats | None = None

        warning = QLabel("<b>{}</b> {}".format(self.tr("Needs an echo."), ECHO_WARNING))
        warning.setWordWrap(True)
        warning.setObjectName("latencyEchoWarning")

        self.output_combo = QComboBox()
        self.input_combo = QComboBox()
        self.output_combo.currentTextChanged.connect(self._on_output_changed)
        refresh = QPushButton("⟳")
        refresh.setProperty("compact", True)
        refresh.setFixedSize(26, 26)
        refresh.setToolTip(self.tr("Refresh the MIDI port lists"))
        refresh.clicked.connect(self.refresh_ports)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_combo, 1)
        output_row.addWidget(refresh)

        defaults = LatencyConfig()
        self.count_spin = self._spin(1, MAX_PINGS, defaults.count)
        self.channel_spin = self._spin(1, 16, defaults.channel)
        self.note_spin = self._spin(0, 127, defaults.note)
        self.interval_spin = self._spin(0, 10_000, int(defaults.interval_ms), " ms")
        self.timeout_spin = self._spin(1, 10_000, int(defaults.timeout_ms), " ms")
        self.match_velocity_check = QCheckBox(self.tr("Reply must carry the ping's velocity"))
        self.match_velocity_check.setChecked(defaults.match_velocity)
        self.match_velocity_check.setToolTip(
            self.tr(
                "Each ping uses its own velocity so a late echo is never counted for the next "
                "ping. Untick for a device that echoes a different velocity."
            )
        )

        form = QFormLayout()
        form.addRow(self.tr("Send to (output)"), output_row)
        form.addRow(self.tr("Listen on (input)"), self.input_combo)
        # Paired on rows: one spin box per row needed 617 px of height on
        # macOS, more than a 900x600 screen (issue #290).
        form.addRow(
            self.tr("Pings"),
            self._pair(self.count_spin, (self.tr("Channel"), self.channel_spin), (self.tr("Note"), self.note_spin)),
        )
        form.addRow(self.tr("Interval"), self._pair(self.interval_spin, (self.tr("Timeout"), self.timeout_spin)))
        form.addRow("", self.match_velocity_check)

        self.summary_label = QLabel(self.tr("Not run yet."))
        self.summary_label.setWordWrap(True)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        self.start_button = QPushButton(self.tr("Start"))
        self.start_button.clicked.connect(self._on_start_stop)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *MIDI_LATENCY))
        bottom.addWidget(self.start_button)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addLayout(form)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.log_view, 1)
        layout.addLayout(bottom)
        keep_wrapped_text_visible(self)

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.drain_results)
        self.refresh_ports()

    @staticmethod
    def _spin(low: int, high: int, value: int, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    @staticmethod
    def _pair(first: QWidget, *labelled: tuple[str, QWidget]) -> QWidget:
        """``first`` followed by more labelled fields on the same form row."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(first)
        for text, field in labelled:
            label = QLabel(text)
            label.setBuddy(field)
            layout.addSpacing(8)
            layout.addWidget(label)
            layout.addWidget(field)
        layout.addStretch(1)
        return row

    @property
    def running(self) -> bool:
        return self._running

    def refresh_ports(self) -> None:
        outputs, inputs = self._list_outputs(), self._list_inputs()
        current_out, current_in = self.output_combo.currentText(), self.input_combo.currentText()
        self.input_combo.clear()
        self.input_combo.addItems(inputs)
        self.output_combo.blockSignals(True)
        self.output_combo.clear()
        self.output_combo.addItems(outputs)
        self.output_combo.blockSignals(False)
        if current_out in outputs:
            self.output_combo.setCurrentText(current_out)
        if current_in in inputs:
            self.input_combo.setCurrentText(current_in)
        else:
            self._on_output_changed(self.output_combo.currentText())
        self._update_enabled()

    def _on_output_changed(self, output: str) -> None:
        inputs = [self.input_combo.itemText(i) for i in range(self.input_combo.count())]
        match = default_input_for(output, inputs)
        if match is not None:
            self.input_combo.setCurrentText(match)

    def config(self) -> LatencyConfig:
        return LatencyConfig(
            count=self.count_spin.value(),
            channel=self.channel_spin.value(),
            note=self.note_spin.value(),
            interval_ms=float(self.interval_spin.value()),
            timeout_ms=float(self.timeout_spin.value()),
            match_velocity=self.match_velocity_check.isChecked(),
        )

    def _update_enabled(self) -> None:
        has_ports = bool(self.output_combo.currentText()) and bool(self.input_combo.currentText())
        self.start_button.setEnabled(self._running or has_ports)
        self.start_button.setText(self.tr("Stop") if self._running else self.tr("Start"))
        for widget in (
            self.output_combo,
            self.input_combo,
            self.count_spin,
            self.channel_spin,
            self.note_spin,
            self.interval_spin,
            self.timeout_spin,
            self.match_velocity_check,
        ):
            widget.setEnabled(not self._running)

    def _on_start_stop(self) -> None:
        if self._running:
            self._stop.set()
            self.summary_label.setText(self.tr("Stopping…"))
            return
        self.start()

    def start(self) -> None:
        output, input_name = self.output_combo.currentText(), self.input_combo.currentText()
        if not output or not input_name or self._running:
            return
        config = self.config()
        self.results = []
        self.last_stats = None
        self.log_view.clear()
        self._stop = threading.Event()
        stop = self._stop
        events = self._queue = queue.Queue()
        factory = self._port_pair_factory
        self._running = True
        self.summary_label.setText(self.tr("Pinging {output} → {input}…").format(output=output, input=input_name))
        self._update_enabled()

        def work() -> None:
            try:
                with factory(output, input_name) as (send, receive):
                    probe = LatencyProbe(send, receive, config)
                    stats = run_probe(
                        probe,
                        should_stop=stop.is_set,
                        on_result=lambda result: events.put(("result", result)),
                    )
                events.put(("done", stats))
            except Exception as exc:
                _LOGGER.warning("MIDI latency test failed", exc_info=True)
                events.put(("error", exc))

        self._timer.start()
        self._start_thread(work)

    def drain_results(self) -> None:
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            if kind == "result":
                assert isinstance(payload, PingResult)
                self.results.append(payload)
                rtt = self.tr("timed out") if payload.rtt_ms is None else f"{payload.rtt_ms:.2f} ms"
                self.log_view.appendPlainText(self.tr("Ping {number}: {rtt}").format(number=payload.index + 1, rtt=rtt))
            elif kind == "done":
                assert isinstance(payload, LatencyStats)
                self.last_stats = payload
                self._finish(format_stats(payload) if payload.sent else self.tr("Stopped before any ping finished."))
            elif kind == "error":
                self._finish(self.tr("Could not run the test: {error}").format(error=payload))

    def _finish(self, text: str) -> None:
        self._timer.stop()
        self._running = False
        self.summary_label.setText(text)
        self._update_enabled()

    def done(self, result: int) -> None:
        self._stop.set()
        super().done(result)


__all__ = ["MidiLatencyDialog", "default_input_for"]
