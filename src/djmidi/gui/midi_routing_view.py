from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.catalog._registry import ControlInfo
from djmidi.gui.port_list_utils import refresh_selectable_port_list
from djmidi.midi_clock import MidiClockMirror
from djmidi.midi_io import list_input_ports, list_output_ports
from djmidi.midi_router import MidiRoute, MidiRouter
from djmidi.midi_routing_session import SERATO_CLOCK_INPUT_NAME, MidiRoutingSession
from djmidi.session_player import _parse_int, play_control_info_entries


class MidiRoutingView(QWidget):
    """Safe configuration surface for the MIDI router and Clock mirror."""

    routesChanged = Signal()

    def __init__(
        self,
        all_rows_provider: Callable[[], list[ControlInfo]] | None = None,
        selected_rows_provider: Callable[[], list[ControlInfo]] | None = None,
        session_name_provider: Callable[[], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._router = MidiRouter()
        self._clock: MidiClockMirror | None = None
        self._clocks: list[MidiClockMirror] = []
        self._routing_enabled = False
        self._routing_session = MidiRoutingSession(self._router)
        self._all_rows_provider = all_rows_provider or list
        self._selected_rows_provider = selected_rows_provider or list
        self._session_name_provider = session_name_provider or (lambda: "")
        self._loop_scope = "selected"
        self._routing_timer = QTimer(self)
        self._routing_timer.setInterval(10)
        self._routing_timer.timeout.connect(self._poll_routing)

        self._source_combo = QComboBox()
        self._destination_combo = QComboBox()
        refresh_button = QPushButton("Refresh MIDI ports")
        refresh_button.clicked.connect(self.refresh_ports)
        add_button = QPushButton("Add route")
        add_button.clicked.connect(self._add_route)
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self._remove_selected)
        self._routing_button = QPushButton("Start routing")
        self._routing_button.clicked.connect(self._toggle_routing)
        self._routing_button.setEnabled(False)

        route_controls = QHBoxLayout()
        route_controls.addWidget(QLabel("Source (MIDI in):"))
        route_controls.addWidget(self._source_combo)
        route_controls.addWidget(QLabel("Destination (MIDI out):"))
        route_controls.addWidget(self._destination_combo)
        route_controls.addWidget(add_button)
        route_controls.addWidget(remove_button)
        route_controls.addWidget(refresh_button)
        route_controls.addWidget(self._routing_button)

        self._routes_table = QTableWidget(0, 3)
        self._routes_table.setHorizontalHeaderLabels(["Source", "Destination", "State"])
        self._routes_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._routes_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        routes_box = QGroupBox("One-way MIDI routes")
        routes_layout = QVBoxLayout(routes_box)
        routes_layout.addLayout(route_controls)
        routes_layout.addWidget(self._routes_table)

        self._clock_source = QComboBox()
        self._clock_destination = QComboBox()
        self._clock_enabled = QCheckBox("Enable Clock mirror policy")
        self._clock_enabled.toggled.connect(self._update_clock_policy)
        self._serato_virtual_checkbox = QCheckBox("Create virtual input for Serato Clock")
        self._serato_virtual_checkbox.toggled.connect(self._toggle_serato_virtual_input)
        self._clock_status = QLabel("Clock mirror disabled")
        self._clock_status.setStyleSheet("color: #666;")
        add_clock_button = QPushButton("Add Clock route")
        add_clock_button.clicked.connect(self._add_clock_route)
        remove_clock_button = QPushButton("Remove selected")
        remove_clock_button.clicked.connect(self._remove_clock_route)
        clock_controls = QHBoxLayout()
        clock_controls.addWidget(QLabel("Clock source (MIDI in):"))
        clock_controls.addWidget(self._clock_source)
        clock_controls.addWidget(QLabel("Clock destination (MIDI out):"))
        clock_controls.addWidget(self._clock_destination)
        clock_controls.addWidget(self._clock_enabled)
        clock_controls.addWidget(self._serato_virtual_checkbox)
        clock_controls.addWidget(add_clock_button)
        clock_controls.addWidget(remove_clock_button)
        clock_box = QGroupBox("MIDI Clock")
        clock_layout = QVBoxLayout(clock_box)
        clock_layout.addLayout(clock_controls)
        self._clock_table = QTableWidget(0, 3)
        self._clock_table.setHorizontalHeaderLabels(["Source", "Destination", "State"])
        self._clock_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._clock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        clock_layout.addWidget(self._clock_table)
        clock_layout.addWidget(self._clock_status)

        help_label = QLabel(
            "Routes are configured here but remain inactive until MIDI routing is enabled in Preferences. "
            "Clock synchronization is intentionally opt-in and must be validated per software/version. "
            "Serato DJ Pro does not emit standard MIDI Clock directly: its virtual Serato Clock input "
            "is useful only when an external Link-to-MIDI or Clock bridge sends ticks into it."
        )
        help_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(routes_box)
        layout.addWidget(clock_box)
        layout.addWidget(self._build_setup_playback_box())
        layout.addStretch(1)

    def set_routing_enabled(self, enabled: bool) -> None:
        """Apply the Preferences safety gate for physical route execution."""
        self._routing_enabled = enabled
        if not enabled:
            self._stop_routing()
        self._routing_button.setEnabled(enabled)
        if not enabled:
            self._routing_button.setToolTip("Enable MIDI routing in Preferences first")
        else:
            self._routing_button.setToolTip("")
        self._refresh_clock_status()

    def _toggle_routing(self) -> None:
        if not self._routing_enabled:
            return
        if self._routing_session.running:
            self._stop_routing()
            return
        try:
            self._routing_session.start()
        except Exception as exc:  # noqa: BLE001 - surface port failures in the GUI
            QMessageBox.warning(self, "Cannot start MIDI routing", str(exc))
            return
        self._routing_button.setText("Stop routing")
        self._routing_timer.start()
        self._refresh_clock_status()

    def _stop_routing(self) -> None:
        self._routing_timer.stop()
        self._routing_session.stop()
        self._routing_button.setText("Start routing")
        self._refresh_clock_status()

    def _poll_routing(self) -> None:
        try:
            self._routing_session.poll()
            self._refresh_clock_status()
        except Exception as exc:  # noqa: BLE001 - stop unsafe hardware execution
            self._stop_routing()
            QMessageBox.warning(self, "MIDI routing stopped", str(exc))

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._stop_loop()
        self._stop_routing()

    def _build_setup_playback_box(self) -> QGroupBox:
        box = QGroupBox("Controller Setup playback")
        layout = QHBoxLayout(box)
        source = QVBoxLayout()
        self._session_summary = QLabel()
        self._session_summary.setWordWrap(True)
        refresh = QPushButton("Refresh session summary")
        refresh.clicked.connect(self.refresh_session_summary)
        source.addWidget(self._session_summary)
        source.addWidget(refresh)
        output = QVBoxLayout()
        self._output_port_list = QListWidget()
        self._output_port_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        refresh_output = QPushButton("Refresh output ports")
        refresh_output.clicked.connect(self._refresh_output_ports)
        output.addWidget(self._output_port_list)
        output.addWidget(refresh_output)
        transport = QVBoxLayout()
        self._value_edit = QLineEdit("127")
        self._hz_edit = QLineEdit("2.0")
        self._playback_status = QLabel("Ready.")
        self._playback_status.setWordWrap(True)
        transport.addWidget(QLabel("Value / velocity (0-127)"))
        transport.addWidget(self._value_edit)
        transport.addWidget(QLabel("Loop frequency (Hz)"))
        transport.addWidget(self._hz_edit)
        for label, callback in (
            ("Play selected setup row(s) once", self._on_play_selected_once_clicked),
            ("Play all setup rows once", self._on_play_all_once_clicked),
            ("Start loop (selected setup rows)", lambda: self._start_loop("selected")),
            ("Start loop (all setup rows)", lambda: self._start_loop("all")),
            ("Stop loop", self._stop_loop),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            transport.addWidget(button)
        transport.addWidget(self._playback_status)
        layout.addLayout(source, 1)
        layout.addLayout(output, 1)
        layout.addLayout(transport, 1)
        self._loop_timer = QTimer(self)
        self._loop_timer.timeout.connect(self._on_loop_tick)
        self.refresh_session_summary()
        return box

    def refresh_session_summary(self) -> None:
        name = self._session_name_provider().strip() or "(unnamed setup session)"
        self._session_summary.setText(
            f"Current setup session: {name}\n"
            f"All rows: {len(self._all_rows_provider())}\n"
            f"Selected rows in Controller Setup: {len(self._selected_rows_provider())}"
        )

    def _refresh_output_ports(self) -> None:
        refresh_selectable_port_list(self._output_port_list, list_output_ports)

    def _selected_output_port(self) -> str:
        item = self._output_port_list.currentItem()
        if item is None:
            raise ValueError("No output port selected")
        return item.text()

    def _entries_for_scope(self, scope: str) -> list[ControlInfo]:
        return self._selected_rows_provider() if scope == "selected" else self._all_rows_provider()

    def _play_scope_once(self, scope: str) -> tuple[int, int]:
        entries = self._entries_for_scope(scope)
        if not entries:
            return 0, 0
        value = _parse_int(self._value_edit.text(), "Value", 0, 127)
        stats = play_control_info_entries(self._selected_output_port(), entries, value)
        return stats.sent_messages, stats.skipped_entries

    def _on_play_selected_once_clicked(self) -> None:
        self._play_once("selected")

    def _on_play_all_once_clicked(self) -> None:
        self._play_once("all")

    def _play_once(self, scope: str) -> None:
        try:
            sent, skipped = self._play_scope_once(scope)
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to play rows", str(exc))
            return
        self._playback_status.setText(f"Played {scope} rows once: {sent} MIDI message(s), {skipped} skipped.")
        self.refresh_session_summary()

    def _start_loop(self, scope: str) -> None:
        if not self._entries_for_scope(scope):
            QMessageBox.warning(self, "No rows to loop", "The current Controller Setup session has no rows for that scope.")
            return
        try:
            hz = float(self._hz_edit.text().strip())
        except ValueError:
            QMessageBox.critical(self, "Invalid frequency", "Loop frequency must be a number.")
            return
        if hz <= 0:
            QMessageBox.critical(self, "Invalid frequency", "Loop frequency must be greater than 0.")
            return
        self._loop_scope = scope
        self._loop_timer.setInterval(max(1, int(1000.0 / hz)))
        self._loop_timer.start()
        self._playback_status.setText(f"Loop started for {scope} rows at {hz:.2f} Hz.")

    def _stop_loop(self) -> None:
        if hasattr(self, "_loop_timer"):
            self._loop_timer.stop()
        if hasattr(self, "_playback_status"):
            self._playback_status.setText("Loop stopped.")

    def _on_loop_tick(self) -> None:
        try:
            sent, skipped = self._play_scope_once(self._loop_scope)
        except Exception as exc:  # noqa: BLE001 - stop unsafe playback
            self._loop_timer.stop()
            QMessageBox.critical(self, "Loop stopped", str(exc))
            return
        self._playback_status.setText(f"Loop tick ({self._loop_scope}): {sent} MIDI message(s), {skipped} skipped.")

    @property
    def router(self) -> MidiRouter:
        return self._router

    @property
    def clock_mirror(self) -> MidiClockMirror | None:
        return self._clock

    def refresh_ports(self) -> None:
        input_names = sorted(set(list_input_ports()))
        output_names = sorted(set(list_output_ports()))
        self._replace_port_combo(self._source_combo, input_names)
        self._replace_port_combo(self._destination_combo, output_names)
        clock_inputs = input_names
        if self._serato_virtual_checkbox.isChecked():
            clock_inputs = [*clock_inputs, SERATO_CLOCK_INPUT_NAME]
        self._replace_port_combo(self._clock_source, clock_inputs)
        self._replace_port_combo(self._clock_destination, output_names)

    @staticmethod
    def _replace_port_combo(combo: QComboBox, names: list[str]) -> None:
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(names)
        combo.setCurrentText(current)
        combo.blockSignals(False)

    def _add_route(self) -> None:
        source = self._source_combo.currentText()
        destination = self._destination_combo.currentText()
        try:
            self._router.add_route(MidiRoute(source, destination))
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot add route", str(exc))
            return
        self._refresh_routes_table()
        self.routesChanged.emit()

    def _remove_selected(self) -> None:
        row = self._routes_table.currentRow()
        if row < 0 or row >= len(self._router.routes):
            return
        self._router.remove_route(self._router.routes[row])
        self._refresh_routes_table()
        self.routesChanged.emit()

    def _refresh_routes_table(self) -> None:
        self._routes_table.setRowCount(0)
        for route in self._router.routes:
            row = self._routes_table.rowCount()
            self._routes_table.insertRow(row)
            values = [route.source_port_id, route.destination_port_id, "Enabled" if route.enabled else "Disabled"]
            for column, value in enumerate(values):
                self._routes_table.setItem(row, column, QTableWidgetItem(value))

    def _update_clock_policy(self, enabled: bool) -> None:
        if self._routing_session.running:
            self._stop_routing()
        if not enabled:
            self._clock = None
            self._clocks.clear()
            self._refresh_clock_table()
            self._routing_session.set_clock_mirrors(())
            self._clock_status.setText("Clock mirror disabled")
            self._refresh_clock_status()
            return
        if self._clocks:
            self._update_clock_session()
            return
        self._add_clock_route()

    def _toggle_serato_virtual_input(self, enabled: bool) -> None:
        if self._routing_session.running:
            self._stop_routing()
        if enabled:
            if self._clock_source.findText(SERATO_CLOCK_INPUT_NAME) < 0:
                self._clock_source.addItem(SERATO_CLOCK_INPUT_NAME)
            self._clock_source.setCurrentText(SERATO_CLOCK_INPUT_NAME)
            self._clock_status.setText(
                "Virtual input ready; Serato alone will not emit MIDI Clock — use a Link/Clock bridge"
            )
        else:
            for index in range(self._clock_source.count() - 1, -1, -1):
                if self._clock_source.itemText(index) == SERATO_CLOCK_INPUT_NAME:
                    self._clock_source.removeItem(index)
            self._clocks[:] = [
                clock for clock in self._clocks if clock.source_port_id != SERATO_CLOCK_INPUT_NAME
            ]
            self._clock = self._clocks[0] if self._clocks else None
            self._refresh_clock_table()
        self._update_clock_session()

    def _add_clock_route(self) -> None:
        if not self._clock_enabled.isChecked():
            return
        source = self._clock_source.currentText()
        destination = self._clock_destination.currentText()
        if not source or not destination or source == destination:
            self._clock_enabled.blockSignals(True)
            self._clock_enabled.setChecked(False)
            self._clock_enabled.blockSignals(False)
            self._clock_status.setText("Select different Clock source and destination ports")
            return
        if any(clock.source_port_id == source and destination in clock.destination_port_ids for clock in self._clocks):
            self._clock_status.setText("This Clock route is already configured")
            return
        if self._routing_session.running:
            self._stop_routing()
        self._clocks.append(MidiClockMirror(source, [destination]))
        self._clock = self._clocks[0]
        self._refresh_clock_table()
        self._update_clock_session()

    def _remove_clock_route(self) -> None:
        row = self._clock_table.currentRow()
        if row < 0 or row >= len(self._clocks):
            return
        if self._routing_session.running:
            self._stop_routing()
        self._clocks.pop(row)
        self._clock = self._clocks[0] if self._clocks else None
        self._refresh_clock_table()
        self._update_clock_session()

    def _refresh_clock_table(self) -> None:
        self._clock_table.setRowCount(0)
        for clock in self._clocks:
            for destination in clock.destination_port_ids:
                row = self._clock_table.rowCount()
                self._clock_table.insertRow(row)
                for column, value in enumerate((clock.source_port_id, destination, "Enabled")):
                    self._clock_table.setItem(row, column, QTableWidgetItem(value))

    def _update_clock_session(self) -> None:
        virtual_ids = (
            (SERATO_CLOCK_INPUT_NAME,)
            if self._serato_virtual_checkbox.isChecked()
            else ()
        )
        self._routing_session.set_virtual_input_ids(virtual_ids)
        self._routing_session.set_clock_mirrors(self._clocks)
        if self._clocks:
            self._refresh_clock_status()
        else:
            self._refresh_clock_status()

    def _refresh_clock_status(self) -> None:
        """Show configured, waiting, active, or stopped Clock state."""
        self._clock_status.setToolTip("")
        if not self._clock_enabled.isChecked():
            text, color = "Clock mirror disabled", "#666"
        elif not self._clocks:
            text, color = "Clock policy enabled; add a source and destination", "#b26a00"
        elif not self._routing_enabled:
            text, color = "Clock configured but routing is disabled in Preferences", "#b26a00"
        elif not self._routing_session.running:
            text, color = "Clock configured; press Start routing", "#b26a00"
        else:
            now = time.monotonic()
            active = [clock for clock in self._clocks if clock.clock_active(now)]
            if active:
                sources = ", ".join(sorted({clock.source_port_id for clock in active}))
                text, color = f"CLOCK ACTIVE — receiving ticks from {sources}", "#16803c"
            else:
                sources = ", ".join(sorted({clock.source_port_id for clock in self._clocks}))
                transport = [clock for clock in self._clocks if clock.message_active(now)]
                if transport:
                    text = f"CLOCK INACTIVE — transport received, no Clock ticks from {sources}"
                elif any(
                    clock.source_port_id in self._routing_session.input_port_ids
                    for clock in self._clocks
                ):
                    text = f"CLOCK INACTIVE — source port open, no ticks received from {sources}"
                else:
                    text = f"CLOCK INACTIVE — source port not open: {sources}"
                color = "#b00020"
                if SERATO_CLOCK_INPUT_NAME in sources:
                    self._clock_status.setToolTip(
                        "Serato diagnostic: start routing, then select this virtual port "
                        "as Serato's MIDI Clock output destination and enable Clock/Sync."
                    )
                else:
                    self._clock_status.setToolTip("")
                self._clock_status.setText(text)
                self._clock_status.setStyleSheet(f"color: {color}; font-weight: 600;")
                return
        self._clock_status.setText(text)
        self._clock_status.setStyleSheet(f"color: {color}; font-weight: 600;")


__all__ = ["MidiRoutingView"]
