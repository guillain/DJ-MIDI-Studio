from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.midi_clock import MidiClockMirror
from djmidi.midi_io import list_input_ports, list_output_ports
from djmidi.midi_router import MidiRoute, MidiRouter
from djmidi.midi_routing_session import SERATO_CLOCK_INPUT_NAME, MidiRoutingSession


class MidiRoutingView(QWidget):
    """Safe configuration surface for the MIDI router and Clock mirror."""

    routesChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._router = MidiRouter()
        self._clock: MidiClockMirror | None = None
        self._clocks: list[MidiClockMirror] = []
        self._routing_enabled = False
        self._routing_session = MidiRoutingSession(self._router)
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
        route_controls.addWidget(QLabel("Source:"))
        route_controls.addWidget(self._source_combo)
        route_controls.addWidget(QLabel("Destination:"))
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
        add_clock_button = QPushButton("Add Clock route")
        add_clock_button.clicked.connect(self._add_clock_route)
        remove_clock_button = QPushButton("Remove selected")
        remove_clock_button.clicked.connect(self._remove_clock_route)
        clock_controls = QHBoxLayout()
        clock_controls.addWidget(QLabel("Clock source:"))
        clock_controls.addWidget(self._clock_source)
        clock_controls.addWidget(QLabel("Clock destination:"))
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
            "Clock synchronization is intentionally opt-in and must be validated per software/version."
        )
        help_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(routes_box)
        layout.addWidget(clock_box)
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

    def _stop_routing(self) -> None:
        self._routing_timer.stop()
        self._routing_session.stop()
        self._routing_button.setText("Start routing")

    def _poll_routing(self) -> None:
        try:
            self._routing_session.poll()
        except Exception as exc:  # noqa: BLE001 - stop unsafe hardware execution
            self._stop_routing()
            QMessageBox.warning(self, "MIDI routing stopped", str(exc))

    def closeEvent(self, event) -> None:
        self._stop_routing()
        super().closeEvent(event)

    @property
    def router(self) -> MidiRouter:
        return self._router

    @property
    def clock_mirror(self) -> MidiClockMirror | None:
        return self._clock

    def refresh_ports(self) -> None:
        names = sorted(set(list_input_ports()) | set(list_output_ports()))
        for combo in (self._source_combo, self._destination_combo, self._clock_source, self._clock_destination):
            current = combo.currentText()
            combo_names = names
            if combo is self._clock_source and self._serato_virtual_checkbox.isChecked():
                combo_names = [*names, SERATO_CLOCK_INPUT_NAME]
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(combo_names)
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
                "Virtual Serato Clock input ready; select it as Serato's MIDI Clock destination"
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
            self._clock_status.setText(f"{len(self._clocks)} Clock route(s) ready")
        else:
            self._clock_status.setText("Clock mirror enabled; add a source and destination")


__all__ = ["MidiRoutingView"]
