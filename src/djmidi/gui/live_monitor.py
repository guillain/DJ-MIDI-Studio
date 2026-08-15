"""Live Monitor tab: watches real MIDI traffic (polled, see midi_io.py) and
shows it as a log, resolving each event through the same catalog.py lookup
used everywhere else, plus the loaded config's Serato function if one
matches. Doesn't have its own Layout view — it drives the three existing
ControllerLayoutViews via MainWindow.highlight_live_event()."""

from __future__ import annotations

import csv
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui.mapping_group import build_mapping_groups
from djmidi.gui.port_list_utils import refresh_checked_port_list
from djmidi.midi_io import MidiEvent, MidiMonitor, list_input_ports
from djmidi.model import MidiConfig

_MAX_ROWS = 500
_POLL_INTERVAL_MS = 30

_VIRTUAL_MONITOR_HELP = (
    "Creates a virtual MIDI destination named "
    f"'{MidiMonitor.VIRTUAL_MONITOR_NAME}'. CoreMIDI won't let this app silently see what "
    "Serato sends to a real hardware output, so to monitor that direction you must "
    "manually add this virtual port as an *additional* MIDI output in Serato's own "
    "MIDI setup (alongside your real controller)."
)


class LiveMonitorView(QWidget):
    eventReceived = Signal(object)  # MidiEvent

    def __init__(self, on_event: Callable[[MidiEvent], None] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._monitor = MidiMonitor()
        self._config: MidiConfig | None = None
        self._function_lookup: dict[tuple[str, str, str], list[str]] = {}
        self._events: list[MidiEvent] = []
        self._running = False

        if on_event is not None:
            self.eventReceived.connect(on_event)

        self._port_list = QListWidget()
        self._port_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        refresh_button = QPushButton("Refresh ports")
        refresh_button.clicked.connect(self._refresh_ports)
        ports_box = QGroupBox("Input sources (check to monitor)")
        ports_layout = QVBoxLayout(ports_box)
        ports_layout.addWidget(self._port_list)
        ports_layout.addWidget(refresh_button)

        self._virtual_checkbox = QCheckBox("Create virtual monitor destination (for Serato output)")
        virtual_help = QLabel(_VIRTUAL_MONITOR_HELP)
        virtual_help.setWordWrap(True)
        self._start_button = QPushButton("Start monitoring")
        self._start_button.clicked.connect(self._toggle_running)
        self._status_label = QLabel("Stopped")
        clear_button = QPushButton("Clear log")
        clear_button.clicked.connect(self._clear_log)
        save_button = QPushButton("Save log…")
        save_button.clicked.connect(self._save_log)

        controls_box = QGroupBox("Monitor")
        controls_layout = QVBoxLayout(controls_box)
        controls_layout.addWidget(self._virtual_checkbox)
        controls_layout.addWidget(virtual_help)
        controls_layout.addWidget(self._start_button)
        controls_layout.addWidget(self._status_label)
        controls_layout.addWidget(clear_button)
        controls_layout.addWidget(save_button)
        controls_layout.addStretch(1)

        top_row = QHBoxLayout()
        top_row.addWidget(ports_box, 1)
        top_row.addWidget(controls_box, 1)

        self._log = QTableWidget(0, 7)
        self._log.setHorizontalHeaderLabels(["Time", "Dir", "Channel", "Type", "Data1", "Data2", "Physical / Serato"])
        self._log.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self._log)

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        self._refresh_ports()

    def set_config(self, config: MidiConfig | None) -> None:
        self._config = config
        self._function_lookup = {}
        if config is not None:
            for group in build_mapping_groups(config):
                key = (group.channel, group.event_type, group.control_no)
                self._function_lookup.setdefault(key, []).append(
                    f"deck {group.deck_id} slot {group.slot_id}: {group.tag} [{group.event}]"
                )

    def _refresh_ports(self) -> None:
        refresh_checked_port_list(self._port_list, list_input_ports)

    def _is_checked(self, row: int) -> bool:
        return self._port_list.item(row).checkState() == Qt.CheckState.Checked

    def _toggle_running(self) -> None:
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        selected = [self._port_list.item(i).text() for i in range(self._port_list.count()) if self._is_checked(i)]
        for name in selected:
            self._monitor.open_input(name)
        if self._virtual_checkbox.isChecked():
            self._monitor.open_virtual_monitor()
        self._running = True
        self._start_button.setText("Stop monitoring")
        self._status_label.setText(f"Running ({len(selected)} input(s){', virtual monitor' if self._virtual_checkbox.isChecked() else ''})")
        self._timer.start()

    def _stop(self) -> None:
        self._timer.stop()
        self._monitor.close_all()
        self._running = False
        self._start_button.setText("Start monitoring")
        self._status_label.setText("Stopped")

    def _poll(self) -> None:
        for event in self._monitor.poll():
            self._events.append(event)
            while len(self._events) > _MAX_ROWS:
                self._events.pop(0)
            self._append_event(event)
            self.eventReceived.emit(event)

    def _append_event(self, event: MidiEvent) -> None:
        hits = catalog.lookup(event.channel, event.event_type, event.data1)
        physical = "; ".join(f"{h.controller}: {h.name}" for h in hits)
        functions = self._function_lookup.get((event.channel, event.event_type, event.data1), [])
        detail = " | ".join(part for part in (physical, "; ".join(functions)) if part) or "(unknown)"

        row = self._log.rowCount()
        self._log.insertRow(row)
        values = [
            time.strftime("%H:%M:%S", time.localtime()),
            event.direction.upper(),
            event.channel,
            event.event_type,
            event.data1,
            event.data2,
            detail,
        ]
        for col, value in enumerate(values):
            self._log.setItem(row, col, QTableWidgetItem(value))
        self._log.scrollToBottom()

        while self._log.rowCount() > _MAX_ROWS:
            self._log.removeRow(0)

    def _clear_log(self) -> None:
        self._events.clear()
        self._log.setRowCount(0)

    def _save_log(self) -> None:
        if not self._events:
            self._status_label.setText("No MIDI events to save.")
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save Live Monitor log",
            "midi-monitor-log.csv",
            "CSV files (*.csv)",
        )
        if not path_str:
            return
        try:
            with Path(path_str).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Timestamp", "Direction", "Port", "Channel", "Type", "Data1", "Data2"])
                for event in self._events:
                    writer.writerow([
                        event.timestamp,
                        event.direction,
                        event.port,
                        event.channel,
                        event.event_type,
                        event.data1,
                        event.data2,
                    ])
        except OSError as exc:
            self._status_label.setText(f"Failed to save log: {exc}")
            return
        self._status_label.setText(f"Saved {len(self._events)} MIDI event(s).")

    def shutdown(self) -> None:
        """Releases MIDI ports; call when the app is closing."""
        if self._running:
            self._stop()


__all__ = ["LiveMonitorView"]
