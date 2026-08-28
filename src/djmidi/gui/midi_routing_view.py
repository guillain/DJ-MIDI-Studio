from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, replace

from PySide6.QtCore import QSettings, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.ableton_link import (
    ABLETON_LINK_CLOCK_SOURCE_NAME,
    AalinkStateProvider,
    LinkBackendUnavailable,
    LinkClockFollower,
)
from djmidi.gui.midi_route_transform_dialog import MidiRouteTransformDialog
from djmidi.midi_clock import MidiClockMirror
from djmidi.midi_io import list_input_ports, list_output_ports
from djmidi.midi_router import MidiRoute, MidiRouter, MidiValueTransform
from djmidi.midi_routing_session import SERATO_CLOCK_INPUT_NAME, MidiRoutingSession

_LOGGER = logging.getLogger(__name__)


def _load_json_list(raw: object) -> list:
    """Best-effort JSON decode of a saved settings value into a list.

    QSettings can hand back `""`/`None` for a never-written key, or (on some
    platforms/backends) an already-decoded value; treat anything that isn't
    a valid JSON list as "nothing saved" rather than raising.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def _transform_to_dict(transform: MidiValueTransform | None) -> dict | None:
    return asdict(transform) if transform is not None else None


def _transform_from_dict(data: object) -> MidiValueTransform | None:
    if not isinstance(data, dict):
        return None
    return MidiValueTransform(
        channel_override=data.get("channel_override"),
        data1_offset=int(data.get("data1_offset", 0) or 0),
        invert_data2=bool(data.get("invert_data2", False)),
    )


def _route_to_dict(route: MidiRoute) -> dict:
    return {
        "source": route.source_port_id,
        "destination": route.destination_port_id,
        "channels": sorted(route.channels),
        "status_nibbles": sorted(route.status_nibbles),
        "allow_sysex": route.allow_sysex,
        "enabled": route.enabled,
        "transform": _transform_to_dict(route.transform),
    }


def _route_from_dict(data: dict) -> MidiRoute:
    return MidiRoute(
        source_port_id=data["source"],
        destination_port_id=data["destination"],
        channels=frozenset(data.get("channels") or ()),
        status_nibbles=frozenset(data.get("status_nibbles") or ()),
        allow_sysex=bool(data.get("allow_sysex", False)),
        enabled=bool(data.get("enabled", True)),
        transform=_transform_from_dict(data.get("transform")),
    )


class MidiRoutingView(QWidget):
    """Safe configuration surface for the MIDI router and Clock mirror."""

    routesChanged = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._router = MidiRouter()
        self._clock: MidiClockMirror | None = None
        self._clocks: list[MidiClockMirror] = []
        self._link_followers: list[LinkClockFollower] = []
        self._routing_enabled = False
        self._clock_status_category: str | None = None
        self._clock_inactive_since: float | None = None
        self._clock_inactive_escalated = False
        self._routing_session = MidiRoutingSession(self._router)
        self._routing_timer = QTimer(self)
        self._routing_timer.setInterval(10)
        self._routing_timer.timeout.connect(self._poll_routing)

        self._source_combo = QComboBox()
        self._destination_combo = QComboBox()
        self._routing_refresh_button = QPushButton("Refresh MIDI ports")
        self._routing_refresh_button.clicked.connect(self.refresh_ports)
        add_button = QPushButton("Add route")
        add_button.clicked.connect(self._add_route)
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self._remove_selected)
        self._edit_transform_button = QPushButton("Edit transform…")
        self._edit_transform_button.setEnabled(False)
        self._edit_transform_button.clicked.connect(self._edit_selected_transform)
        self._routing_button = QPushButton("Start routing")
        self._routing_button.clicked.connect(self._toggle_routing)
        self._routing_button.setEnabled(False)

        route_controls = QGridLayout()
        route_controls.addWidget(QLabel("Source (MIDI in)"), 0, 0)
        route_controls.addWidget(self._source_combo, 0, 1)
        route_controls.addWidget(QLabel("Destination (MIDI out)"), 0, 2)
        route_controls.addWidget(self._destination_combo, 0, 3)
        route_controls.addWidget(add_button, 1, 0)
        route_controls.addWidget(remove_button, 1, 1)
        route_controls.addWidget(self._edit_transform_button, 1, 2)
        route_controls.addWidget(self._routing_refresh_button, 1, 3)
        route_controls.addWidget(self._routing_button, 1, 4)
        route_controls.setColumnStretch(1, 1)
        route_controls.setColumnStretch(3, 1)

        self._routes_table = QTableWidget(0, 4)
        self._routes_table.setHorizontalHeaderLabels(["Source", "Destination", "Transform", "State"])
        self._routes_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._routes_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._routes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._routes_table.itemSelectionChanged.connect(self._on_route_selection_changed)

        routes_box = QGroupBox("One-way MIDI routes")
        routes_box.setObjectName("routingCard")
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
        self._clock_refresh_button = QPushButton("Refresh MIDI ports")
        self._clock_refresh_button.clicked.connect(self.refresh_ports)
        self._clock_routing_button = QPushButton("Start routing")
        self._clock_routing_button.clicked.connect(self._toggle_routing)
        self._clock_routing_button.setEnabled(False)
        clock_controls = QGridLayout()
        clock_controls.addWidget(QLabel("Clock source"), 0, 0)
        clock_controls.addWidget(self._clock_source, 0, 1)
        clock_controls.addWidget(QLabel("Destination (MIDI out)"), 1, 0)
        clock_controls.addWidget(self._clock_destination, 1, 1)
        clock_controls.addWidget(self._clock_enabled, 2, 0, 1, 2)
        clock_controls.addWidget(self._serato_virtual_checkbox, 3, 0, 1, 2)
        clock_controls.addWidget(add_clock_button, 4, 0)
        clock_controls.addWidget(remove_clock_button, 4, 1)
        clock_controls.addWidget(self._clock_refresh_button, 5, 0)
        clock_controls.addWidget(self._clock_routing_button, 5, 1)
        clock_controls.setColumnStretch(1, 1)
        self._clock_panel = QGroupBox("MIDI Clock")
        self._clock_panel.setObjectName("clockCard")
        self._clock_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        clock_layout = QVBoxLayout(self._clock_panel)
        clock_intro = QLabel(
            "Build a Clock route, then start routing to send transport and 24 PPQN ticks."
        )
        clock_intro.setWordWrap(True)
        clock_intro.setStyleSheet("color: #8fa7bd; padding-bottom: 4px;")
        clock_layout.addWidget(clock_intro)
        clock_layout.addLayout(clock_controls)
        self._clock_table = QTableWidget(0, 3)
        self._clock_table.setHorizontalHeaderLabels(["Source", "Destination", "State"])
        self._clock_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._clock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._clock_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        clock_layout.addWidget(self._clock_table)
        clock_layout.addWidget(self._clock_status)

        help_label = QLabel(
            "Routes are configured here but remain inactive until MIDI routing is enabled in Preferences. "
            "Clock synchronization is intentionally opt-in and must be validated per software/version. "
            "Serato DJ Pro does not emit standard MIDI Clock directly. Enable Ableton Link in Serato "
            "and choose 'Ableton Link (DJ MIDI Studio)' to follow Link and generate MIDI Clock here."
        )
        help_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(routes_box)
        layout.addStretch(1)
        self._apply_dj_style()
        self.refresh_ports()

    def _apply_dj_style(self) -> None:
        """Give the routing tools a compact DJ-booth visual identity."""
        self.setObjectName("midiToolsSurface")
        # The Clock card is reparented into its own dock after construction;
        # give it the same visual root so the scoped theme follows it.
        self._clock_panel.setObjectName("midiToolsSurface")
        self._routing_button.setObjectName("primaryAction")
        self._clock_routing_button.setObjectName("clockAction")
        self._clock_status.setObjectName("clockStatus")
        self.setStyleSheet(
            """
            #midiToolsSurface {
                background: #0d121b;
                color: #e8eef7;
            }
            #midiToolsSurface QLabel {
                color: #c9d5e4;
            }
            #midiToolsSurface QGroupBox {
                background: #151e2b;
                border: 1px solid #2b3b53;
                border-radius: 10px;
                margin-top: 12px;
                padding: 12px 10px 10px 10px;
                font-weight: 600;
            }
            #midiToolsSurface QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #8fe8ff;
                background: #0d121b;
            }
            #midiToolsSurface QComboBox,
            #midiToolsSurface QTableWidget,
            #midiToolsSurface QLineEdit,
            #midiToolsSurface QListWidget {
                background: #0e1724;
                color: #e8eef7;
                border: 1px solid #334963;
                border-radius: 6px;
                padding: 5px;
            }
            #midiToolsSurface QComboBox:focus,
            #midiToolsSurface QTableWidget:focus {
                border: 1px solid #00c2e8;
            }
            #midiToolsSurface QComboBox QAbstractItemView {
                background: #0e1724;
                color: #e8eef7;
                border: 1px solid #334963;
                selection-background-color: #d33c72;
                selection-color: #ffffff;
            }
            #midiToolsSurface QHeaderView::section {
                background: #202d42;
                color: #b9c9dc;
                border: 0;
                border-bottom: 1px solid #3a506d;
                padding: 7px;
                font-weight: 600;
            }
            #midiToolsSurface QTableWidget::item:selected {
                background: #284765;
                color: #ffffff;
            }
            #midiToolsSurface QPushButton {
                background: #26364d;
                color: #e8eef7;
                border: 1px solid #405875;
                border-radius: 6px;
                padding: 7px 11px;
                font-weight: 600;
            }
            #midiToolsSurface QPushButton:hover {
                background: #334b68;
                border-color: #00c2e8;
            }
            #midiToolsSurface QPushButton#primaryAction {
                background: #d33c72;
                border-color: #f26395;
            }
            #midiToolsSurface QPushButton#clockAction {
                background: #008eaa;
                border-color: #28d5ef;
            }
            #midiToolsSurface QPushButton#primaryAction:hover,
            #midiToolsSurface QPushButton#clockAction:hover {
                background: #f05a8d;
            }
            #midiToolsSurface QPushButton:disabled {
                background: #1a2432;
                color: #64758b;
                border-color: #273649;
            }
            #midiToolsSurface QCheckBox {
                color: #c9d5e4;
                spacing: 7px;
                padding: 3px 0;
            }
            #midiToolsSurface QCheckBox::indicator:checked {
                background: #00b9d9;
                border: 1px solid #7eefff;
            }
            #midiToolsSurface #clockStatus {
                background: #202d42;
                border-left: 4px solid #00c2e8;
                border-radius: 5px;
                padding: 9px;
            }
            """
        )
        self._clock_panel.setStyleSheet(self.styleSheet())

    def take_clock_panel(self) -> QWidget:
        """Detach and return the Clock controls for the independent Clock dock."""
        self._clock_panel.setParent(None)
        return self._clock_panel

    def set_routing_enabled(self, enabled: bool) -> None:
        """Apply the Preferences safety gate for physical route execution."""
        self._routing_enabled = enabled
        if not enabled:
            self._stop_routing()
        self._routing_button.setEnabled(enabled)
        self._clock_routing_button.setEnabled(enabled)
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
        except Exception as exc:
            _LOGGER.exception("Cannot start MIDI routing")
            QMessageBox.warning(self, "Cannot start MIDI routing", str(exc))
            return
        self._routing_button.setText("Stop routing")
        self._clock_routing_button.setText("Stop routing")
        self._routing_timer.start()
        self._refresh_clock_status()

    def _stop_routing(self) -> None:
        self._routing_timer.stop()
        self._routing_session.stop()
        self._routing_button.setText("Start routing")
        self._clock_routing_button.setText("Start routing")
        self._refresh_clock_status()

    def _poll_routing(self) -> None:
        try:
            self._routing_session.poll()
            self._refresh_clock_status()
        except Exception as exc:
            _LOGGER.exception("MIDI routing stopped after a poll failure")
            self._stop_routing()
            QMessageBox.warning(self, "MIDI routing stopped", str(exc))

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._stop_routing()
        for follower in self._link_followers:
            follower.close()
        self._link_followers.clear()

    @property
    def router(self) -> MidiRouter:
        return self._router

    @property
    def clock_mirror(self) -> MidiClockMirror | None:
        return self._clock

    def save_state(self, settings: QSettings) -> None:
        """Persist routes, Clock configuration, and port selections.

        Nothing here was previously saved: routes/Clock mirrors/Link
        followers only ever lived in memory, so every restart reset the
        MIDI Routing and MIDI Clock docks to empty.
        """
        settings.beginGroup("midiRouting")
        try:
            settings.setValue("sourcePort", self._source_combo.currentText())
            settings.setValue("destinationPort", self._destination_combo.currentText())
            settings.setValue("routes", json.dumps([_route_to_dict(route) for route in self._router.routes]))
            settings.setValue("clockSourcePort", self._clock_source.currentText())
            settings.setValue("clockDestinationPort", self._clock_destination.currentText())
            settings.setValue("clockEnabled", self._clock_enabled.isChecked())
            settings.setValue("serotoVirtualInput", self._serato_virtual_checkbox.isChecked())
            settings.setValue(
                "clocks",
                json.dumps(
                    [
                        {"source": clock.source_port_id, "destinations": list(clock.destination_port_ids)}
                        for clock in self._clocks
                    ]
                ),
            )
            settings.setValue(
                "linkFollowers",
                json.dumps([list(follower.destination_port_ids) for follower in self._link_followers]),
            )
        finally:
            settings.endGroup()

    def restore_state(self, settings: QSettings) -> None:
        """Reload routes/Clock configuration saved by `save_state`.

        Called once at startup, after `refresh_ports()` has already
        populated the combos so a saved selection can actually be found.
        Every saved entry is applied best-effort: a port that no longer
        exists or a Link backend that is no longer available is skipped
        with a warning rather than aborting the whole restore.
        """
        settings.beginGroup("midiRouting")
        try:
            source_port = settings.value("sourcePort", "")
            if source_port:
                self._source_combo.setCurrentText(source_port)
            destination_port = settings.value("destinationPort", "")
            if destination_port:
                self._destination_combo.setCurrentText(destination_port)

            for entry in _load_json_list(settings.value("routes", "")):
                try:
                    self._router.add_route(_route_from_dict(entry))
                except (KeyError, TypeError, ValueError) as exc:
                    _LOGGER.warning("Skipped a saved MIDI route on restore: %s", exc)
            self._refresh_routes_table()

            self._serato_virtual_checkbox.setChecked(
                bool(settings.value("serotoVirtualInput", False, type=bool))
            )

            clock_source = settings.value("clockSourcePort", "")
            if clock_source:
                self._clock_source.setCurrentText(clock_source)
            clock_destination = settings.value("clockDestinationPort", "")
            if clock_destination:
                self._clock_destination.setCurrentText(clock_destination)

            for entry in _load_json_list(settings.value("clocks", "")):
                try:
                    self._clocks.append(MidiClockMirror(entry["source"], list(entry["destinations"])))
                except (KeyError, TypeError, ValueError) as exc:
                    _LOGGER.warning("Skipped a saved Clock route on restore: %s", exc)
            if self._clocks:
                self._clock = self._clocks[0]

            for destinations in _load_json_list(settings.value("linkFollowers", "")):
                try:
                    self._link_followers.append(LinkClockFollower(list(destinations), AalinkStateProvider()))
                except LinkBackendUnavailable as exc:
                    _LOGGER.info("Skipped a saved Ableton Link Clock route on restore: %s", exc)

            self._refresh_clock_table()
            self._update_clock_session()

            self._clock_enabled.blockSignals(True)
            self._clock_enabled.setChecked(bool(settings.value("clockEnabled", False, type=bool)))
            self._clock_enabled.blockSignals(False)
            self._refresh_clock_status()
        finally:
            settings.endGroup()

    def refresh_ports(self) -> None:
        input_names = sorted(set(list_input_ports()))
        output_names = sorted(set(list_output_ports()))
        self._replace_port_combo(self._source_combo, input_names)
        self._replace_port_combo(self._destination_combo, output_names)
        clock_inputs = [*input_names, ABLETON_LINK_CLOCK_SOURCE_NAME]
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

    def _on_route_selection_changed(self) -> None:
        self._edit_transform_button.setEnabled(self._routes_table.currentRow() >= 0)

    def _edit_selected_transform(self) -> None:
        row = self._routes_table.currentRow()
        if row < 0 or row >= len(self._router.routes):
            return
        route = self._router.routes[row]
        dialog = MidiRouteTransformDialog(route.transform, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._router.remove_route(route)
        self._router.add_route(replace(route, transform=dialog.result_transform()))
        self._refresh_routes_table()
        self._routes_table.setCurrentCell(row, 0)
        self.routesChanged.emit()

    @staticmethod
    def _transform_summary(transform: MidiValueTransform | None) -> str:
        if transform is None:
            return "—"
        parts = []
        if transform.channel_override is not None:
            parts.append(f"Ch {transform.channel_override}")
        if transform.data1_offset:
            parts.append(f"{transform.data1_offset:+d}")
        if transform.invert_data2:
            parts.append("invert")
        return ", ".join(parts) or "—"

    def _refresh_routes_table(self) -> None:
        self._routes_table.setRowCount(0)
        for route in self._router.routes:
            row = self._routes_table.rowCount()
            self._routes_table.insertRow(row)
            values = [
                route.source_port_id,
                route.destination_port_id,
                self._transform_summary(route.transform),
                "Enabled" if route.enabled else "Disabled",
            ]
            for column, value in enumerate(values):
                self._routes_table.setItem(row, column, QTableWidgetItem(value))
        self._edit_transform_button.setEnabled(self._routes_table.currentRow() >= 0)

    def _update_clock_policy(self, enabled: bool) -> None:
        if self._routing_session.running:
            self._stop_routing()
        if not enabled:
            self._clock = None
            self._clocks.clear()
            for follower in self._link_followers:
                follower.close()
            self._link_followers.clear()
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
        if any(
            clock.source_port_id == source and destination in clock.destination_port_ids
            for clock in (*self._clocks, *self._link_followers)
        ):
            self._clock_status.setText("This Clock route is already configured")
            return
        if self._routing_session.running:
            self._stop_routing()
        if source == ABLETON_LINK_CLOCK_SOURCE_NAME:
            try:
                follower = LinkClockFollower([destination], AalinkStateProvider())
            except LinkBackendUnavailable as exc:
                _LOGGER.exception("Cannot add Ableton Link Clock route to %s", destination)
                self._clock_status.setText(str(exc))
                return
            _LOGGER.info("Ableton Link Clock route added: %s -> %s", source, destination)
            self._link_followers.append(follower)
        else:
            self._clocks.append(MidiClockMirror(source, [destination]))
            self._clock = self._clocks[0]
        self._refresh_clock_table()
        self._update_clock_session()

    def _remove_clock_route(self) -> None:
        row = self._clock_table.currentRow()
        if row < 0 or row >= len(self._clocks) + len(self._link_followers):
            return
        if self._routing_session.running:
            self._stop_routing()
        if row < len(self._clocks):
            self._clocks.pop(row)
        else:
            follower = self._link_followers.pop(row - len(self._clocks))
            follower.close()
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
        for follower in self._link_followers:
            for destination in follower.destination_port_ids:
                row = self._clock_table.rowCount()
                self._clock_table.insertRow(row)
                for column, value in enumerate((follower.source_port_id, destination, "Enabled")):
                    self._clock_table.setItem(row, column, QTableWidgetItem(value))

    def _update_clock_session(self) -> None:
        virtual_ids = (
            (SERATO_CLOCK_INPUT_NAME,)
            if self._serato_virtual_checkbox.isChecked()
            else ()
        )
        self._routing_session.set_virtual_input_ids(virtual_ids)
        self._routing_session.set_clock_mirrors(self._clocks)
        self._routing_session.set_link_followers(self._link_followers)
        if self._clocks:
            self._refresh_clock_status()
        else:
            self._refresh_clock_status()

    # Sustained Clock inactivity (no ticks despite routing being started) is
    # escalated from WARNING to ERROR after this many seconds so a real
    # troubleshooting session ends up with at least one ERROR line, not just
    # a GUI label nobody was watching at the time.
    _CLOCK_INACTIVE_ERROR_AFTER_S = 8.0

    def _refresh_clock_status(self) -> None:
        """Show configured, waiting, active, or stopped Clock state."""
        self._clock_status.setToolTip("")
        category = "disabled"
        if not self._clock_enabled.isChecked():
            text, color = "Clock mirror disabled", "#666"
        else:
            configured = (*self._clocks, *self._link_followers)
            if not configured:
                text, color = "Clock policy enabled; add a source and destination", "#b26a00"
                category = "unconfigured"
            elif not self._routing_enabled:
                text, color = "Clock configured but routing is disabled in Preferences", "#b26a00"
                category = "routing_disabled"
            elif not self._routing_session.running:
                text, color = "Clock configured; press Start routing", "#b26a00"
                category = "waiting_start"
            else:
                now = time.monotonic()
                active = [clock for clock in self._clocks if clock.clock_active(now)]
                active_link = [follower for follower in self._link_followers if follower.clock_active(now)]
                if active or active_link:
                    sources = ", ".join(sorted({clock.source_port_id for clock in (*active, *active_link)}))
                    text, color = f"CLOCK ACTIVE — receiving ticks from {sources}", "#16803c"
                    category = "active"
                else:
                    sources = ", ".join(sorted({clock.source_port_id for clock in configured}))
                    transport = [clock for clock in self._clocks if clock.message_active(now)]
                    if self._link_followers:
                        text = f"CLOCK INACTIVE — no Link beats received from {sources}"
                        category = "inactive_link"
                        self._clock_status.setToolTip(
                            "Ableton Link is connected but no playing Link transport was detected. "
                            "Enable Link in Ableton Live, join the same Link session, and start playback."
                        )
                    elif transport:
                        text = f"CLOCK INACTIVE — transport received, no Clock ticks from {sources}"
                        category = "inactive_transport"
                    elif any(
                        clock.source_port_id in self._routing_session.input_port_ids
                        for clock in self._clocks
                    ):
                        text = f"CLOCK INACTIVE — source port open, no ticks received from {sources}"
                        category = "inactive_port_open"
                    else:
                        text = f"CLOCK INACTIVE — source port not open: {sources}"
                        category = "inactive_port_closed"
                    color = "#b00020"
                    if SERATO_CLOCK_INPUT_NAME in sources and not self._link_followers:
                        self._clock_status.setToolTip(
                            "Serato diagnostic: start routing, then select this virtual port "
                            "as Serato's MIDI Clock output destination and enable Clock/Sync."
                        )
                    elif not self._link_followers:
                        self._clock_status.setToolTip("")
        self._log_clock_status_transition(category, text)
        self._clock_status.setText(text)
        self._clock_status.setStyleSheet(
            f"color: {color}; font-weight: 600; background: #202d42; "
            f"border-left: 4px solid {color}; border-radius: 5px; padding: 9px;"
        )

    def _log_clock_status_transition(self, category: str, text: str) -> None:
        """Log Clock status changes (not every poll) so a troubleshooting
        session ends up with a readable trail instead of either silence or a
        flood of one line per 10ms poll tick."""
        now = time.monotonic()
        if category.startswith("inactive"):
            if self._clock_inactive_since is None:
                self._clock_inactive_since = now
                self._clock_inactive_escalated = False
            elapsed = now - self._clock_inactive_since
            if elapsed >= self._CLOCK_INACTIVE_ERROR_AFTER_S and not self._clock_inactive_escalated:
                self._clock_inactive_escalated = True
                _LOGGER.error(
                    "Clock still inactive after %.1fs (%s): %s",
                    elapsed,
                    category,
                    text,
                )
            elif category != self._clock_status_category:
                _LOGGER.warning("Clock status: %s", text)
        else:
            self._clock_inactive_since = None
            self._clock_inactive_escalated = False
            if category != self._clock_status_category:
                if category == "active":
                    _LOGGER.info("Clock status: %s", text)
                else:
                    _LOGGER.debug("Clock status: %s", text)
        self._clock_status_category = category


__all__ = ["MidiRoutingView"]
