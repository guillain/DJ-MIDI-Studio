"""Live Monitor tab: watches real MIDI traffic (polled, see midi_io.py) and
shows it as a log, resolving each event through the same catalog.py lookup
used everywhere else, plus the loaded config's Serato function if one
matches. An input whose trigger fires two or more different functions on the
same deck of the loaded mapping (validator.find_deck_conflicts) is flagged in
its log row and counted. Doesn't have its own Layout view — it drives the three existing
ControllerLayoutViews via MainWindow.highlight_live_event()."""

from __future__ import annotations

import csv
import logging
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog, user_paths
from djmidi.gui import help_texts
from djmidi.gui.help_button import help_row
from djmidi.gui.mapping_group import build_mapping_groups
from djmidi.gui.port_list_utils import refresh_checked_port_list
from djmidi.gui.scroll_utils import AutoSizeScrollArea
from djmidi.midi_io import MidiEvent, MidiMonitor, list_input_ports
from djmidi.model import MidiConfig
from djmidi.validator import DeckConflict, TriggerKey, find_deck_conflicts

_MAX_ROWS = 500
_POLL_INTERVAL_MS = 30
# Amber, readable on both light and dark themes behind default text.
_CONFLICT_BRUSH = QBrush(QColor(255, 176, 32, 90))

_VIRTUAL_MONITOR_HELP = QT_TRANSLATE_NOOP(
    "LiveMonitorView",
    "Creates a virtual MIDI destination named '{name}'. CoreMIDI won't let this app silently see what "
    "Serato sends to a real hardware output, so to monitor that direction you must "
    "manually add this virtual port as an *additional* MIDI output in Serato's own "
    "MIDI setup (alongside your real controller).",
)

_LOGGER = logging.getLogger(__name__)


class LiveMonitorView(QWidget):
    eventReceived = Signal(object)  # MidiEvent
    portNamesChanged = Signal(list)
    # self.tr("Sync controllers") clicked; MainWindow owns the stored sync sets.
    syncRequested = Signal()

    def __init__(self, on_event: Callable[[MidiEvent], None] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._monitor = MidiMonitor()
        self._config: MidiConfig | None = None
        self._function_lookup: dict[tuple[str, str, str], list[str]] = {}
        self._conflicts: dict[TriggerKey, list[DeckConflict]] = {}
        self._conflict_hits = 0
        self._conflict_triggers: set[TriggerKey] = set()
        self._events: list[MidiEvent] = []
        self._running = False
        # Set while the menu bar's ● Rec records (issue #307): Start/Stop and
        # the port choice are frozen, and an auto-start is deferred to unlock.
        self._lock_reason: str | None = None
        self._auto_start_pending = False

        if on_event is not None:
            self.eventReceived.connect(on_event)

        self._port_list = QListWidget()
        self._port_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        refresh_button = QPushButton(self.tr("Refresh ports"))
        refresh_button.clicked.connect(self._refresh_ports)
        select_all_button = QPushButton(self.tr("Select all sources"))
        select_all_button.clicked.connect(self._select_all_sources)
        self._ports_box = ports_box = QGroupBox(self.tr("Input sources (check to monitor)"))
        ports_layout = QVBoxLayout(ports_box)
        ports_layout.addWidget(self._port_list)
        ports_layout.addWidget(refresh_button)
        ports_layout.addWidget(select_all_button)

        self._virtual_checkbox = QCheckBox(self.tr("Create virtual monitor destination (for Serato output)"))
        virtual_help = QLabel(self.tr(_VIRTUAL_MONITOR_HELP).format(name=MidiMonitor.VIRTUAL_MONITOR_NAME))
        virtual_help.setWordWrap(True)
        self._start_button = QPushButton(self.tr("Start monitoring"))
        self._start_button.clicked.connect(self._toggle_running)
        self._status_label = QLabel(self.tr("Stopped"))
        self._conflict_label = QLabel()
        self._conflict_label.setWordWrap(True)
        self._conflict_label.setToolTip(
            self.tr(
                "Live inputs that fire two or more different functions on the same deck "
                "in the loaded mapping. Serato's identical repeated triggers are not conflicts."
            )
        )
        self._update_conflict_label()
        clear_button = QPushButton(self.tr("Clear log"))
        clear_button.clicked.connect(self._clear_log)
        save_button = QPushButton(self.tr("Save log…"))
        save_button.clicked.connect(self._save_log)
        self._sync_button = QPushButton(self.tr("Sync controllers"))
        self._sync_button.setToolTip(
            self.tr(
                "Send each controller its recorded initialization set "
                "(recorded with ● Rec or in Controller Setup, listed in Preferences → Controller sync)."
            )
        )
        self._sync_button.clicked.connect(self.syncRequested)

        controls_box = QGroupBox(self.tr("Monitor"))
        controls_layout = QVBoxLayout(controls_box)
        controls_layout.addLayout(help_row(self, *help_texts.LIVE_MONITOR))
        controls_layout.addWidget(self._virtual_checkbox)
        controls_layout.addWidget(virtual_help)
        controls_layout.addWidget(self._start_button)
        controls_layout.addWidget(self._status_label)
        controls_layout.addWidget(self._conflict_label)
        controls_layout.addWidget(clear_button)
        controls_layout.addWidget(save_button)
        controls_layout.addWidget(self._sync_button)
        controls_layout.addStretch(1)

        top_row = QHBoxLayout()
        top_row.addWidget(ports_box, 1)
        top_row.addWidget(controls_box, 1)

        self._log = QTableWidget(0, 8)
        self._log.setHorizontalHeaderLabels(
            [
                self.tr("Time"),
                self.tr("Dir"),
                self.tr("Source device"),
                self.tr("Channel"),
                self.tr("Type"),
                self.tr("Data1"),
                self.tr("Data2"),
                self.tr("Physical / Serato"),
            ]
        )
        self._log.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log.setColumnWidth(2, 180)
        self._log.horizontalHeader().setStretchLastSection(True)

        # top_row ("Input sources" + self.tr("Monitor")) had no scroll protection --
        # found while widening the issue #19 clipping audit: at a narrow
        # enough docked width, this dock's real minimum width exceeds the
        # window, and QMainWindow lets this dock's geometry extend past the
        # window's right edge rather than shrink below its floor, silently
        # clipping this dock's own title bar (Undock/Close) along with it.
        # Same fix as Controller Setup's header region: wrap only top_row,
        # not self._log too -- a QTableWidget is already its own
        # QAbstractScrollArea (internal scrollbars handle any column
        # overflow on its own), so it doesn't need -- and, per the Draft
        # panel fix's own lesson, must NOT get -- a second, outer
        # QScrollArea: nesting one changes how the layout negotiates space
        # and can make things worse, not better. AutoSizeScrollArea (not a
        # plain QScrollArea) for the same reason as that fix: self._log has
        # stretch=1 below, so a plain QScrollArea's sizeHint (which doesn't
        # track its content) would starve top_row of room even on a window
        # plenty tall enough for both.
        top_row_container = QWidget()
        top_row_container.setLayout(top_row)
        top_scroll = AutoSizeScrollArea()
        top_scroll.setWidgetResizable(True)
        top_scroll.setFrameShape(QFrame.Shape.NoFrame)
        top_scroll.setWidget(top_row_container)

        layout = QVBoxLayout(self)
        layout.addWidget(top_scroll, 0)
        layout.addWidget(self._log, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        self._refresh_ports()

    def set_config(self, config: MidiConfig | None) -> None:
        self._config = config
        self._function_lookup = {}
        self._conflicts = find_deck_conflicts(config) if config is not None else {}
        self._reset_conflict_count()
        if config is not None:
            for group in build_mapping_groups(config):
                key = (group.channel, group.event_type, group.control_no)
                self._function_lookup.setdefault(key, []).append(
                    self.tr("deck {deck} slot {slot}: {tag} [{event}]").format(
                        deck=group.deck_id, slot=group.slot_id, tag=group.tag, event=group.event
                    )
                )

    def _refresh_ports(self) -> None:
        refresh_checked_port_list(self._port_list, list_input_ports)
        self.portNamesChanged.emit(self.input_port_names())

    def input_port_names(self) -> list[str]:
        return [
            self._port_list.item(row).text()
            for row in range(self._port_list.count())
        ]

    def _select_all_sources(self) -> None:
        """Checks every currently available MIDI input source."""
        for row in range(self._port_list.count()):
            self._port_list.item(row).setCheckState(Qt.CheckState.Checked)

    def _is_checked(self, row: int) -> bool:
        return self._port_list.item(row).checkState() == Qt.CheckState.Checked

    def _toggle_running(self) -> None:
        if self._lock_reason is not None:
            return
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        selected = [self._port_list.item(i).text() for i in range(self._port_list.count()) if self._is_checked(i)]
        try:
            for name in selected:
                self._monitor.open_input(name)
            if self._virtual_checkbox.isChecked():
                self._monitor.open_virtual_monitor()
        except Exception as exc:  # noqa: BLE001 - surface device-open failures without a partial monitor
            self._monitor.close_all()
            self._status_label.setText(self.tr("Stopped"))
            self._start_button.setText(self.tr("Start monitoring"))
            QMessageBox.warning(self, self.tr("Cannot start monitoring"), str(exc))
            return
        self._running = True
        self._start_button.setText(self.tr("Stop monitoring"))
        status = (
            self.tr("Running ({count} input(s), virtual monitor)")
            if self._virtual_checkbox.isChecked()
            else self.tr("Running ({count} input(s))")
        )
        self._status_label.setText(status.format(count=len(selected)))
        _LOGGER.info(
            "Live Monitor started: inputs=%s, virtual_monitor=%s", selected, self._virtual_checkbox.isChecked()
        )
        self._timer.start()

    def _stop(self) -> None:
        self._timer.stop()
        self._monitor.close_all()
        self._running = False
        self._start_button.setText(self.tr("Start monitoring"))
        self._status_label.setText(self.tr("Stopped"))
        _LOGGER.info("Live Monitor stopped")

    def _poll(self) -> None:
        for event in self._monitor.poll():
            self._events.append(event)
            while len(self._events) > _MAX_ROWS:
                self._events.pop(0)
            self._append_event(event)
            self.eventReceived.emit(event)

    def _append_event(self, event: MidiEvent) -> None:
        hits = catalog.lookup(event.channel, event.event_type, event.data1)
        if event.port:
            # catalog.lookup() is intentionally controller-agnostic because a
            # config does not identify the hardware that sent an event.  The
            # live monitor does know the source port, so avoid showing a
            # matching control from another controller (e.g. DDJ-1000 when a
            # DDJ-XP2 sent the event).
            source = event.port.casefold()
            hits = [hit for hit in hits if hit.controller.casefold() in source]
        physical = "; ".join(h.name for h in hits)
        trigger = (event.channel, event.event_type, event.data1)
        functions = self._function_lookup.get(trigger, [])
        conflicts = self._conflicts.get(trigger, []) if event.direction == "in" else []
        conflict_text = ""
        if conflicts:
            conflict_text = self.tr("CONFLICT ") + "; ".join(c.describe() for c in conflicts)
            self._count_conflict(event, trigger)
        detail = " | ".join(part for part in (conflict_text, physical, "; ".join(functions)) if part) or self.tr("(unknown)")

        row = self._log.rowCount()
        self._log.insertRow(row)
        values = [
            time.strftime("%H:%M:%S", time.localtime()),
            event.direction.upper(),
            event.port or self.tr("(unknown)"),
            event.channel,
            event.event_type,
            event.data1,
            event.data2,
            detail,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if conflicts:
                item.setBackground(_CONFLICT_BRUSH)
                item.setToolTip(conflict_text)
            self._log.setItem(row, col, item)
        self._log.scrollToBottom()

        while self._log.rowCount() > _MAX_ROWS:
            self._log.removeRow(0)

    def _count_conflict(self, event: MidiEvent, trigger: TriggerKey) -> None:
        # A Note On with velocity 0 is a release: still flagged in its row, but
        # not counted again, so one press = one conflict hit.
        if event.event_type == "Note On" and event.data2 == "0":
            return
        self._conflict_hits += 1
        self._conflict_triggers.add(trigger)
        self._update_conflict_label()

    def _reset_conflict_count(self) -> None:
        self._conflict_hits = 0
        self._conflict_triggers = set()
        self._update_conflict_label()

    def _update_conflict_label(self) -> None:
        if not self._conflicts:
            self._conflict_label.setText(self.tr("Conflicts: none in the loaded mapping"))
            return
        self._conflict_label.setText(
            self.tr(
                "Conflicts: {hits} live hit(s) on {triggers} trigger(s) "
                "({conflicts} conflicting trigger(s) in the mapping)"
            ).format(hits=self._conflict_hits, triggers=len(self._conflict_triggers), conflicts=len(self._conflicts))
        )

    def conflict_counts(self) -> tuple[int, int]:
        """(live conflicting hits, distinct conflicting triggers hit) since the
        last Clear log or mapping load."""
        return self._conflict_hits, len(self._conflict_triggers)

    def _clear_log(self) -> None:
        self._events.clear()
        self._log.setRowCount(0)
        self._reset_conflict_count()

    def _save_log(self) -> None:
        if not self._events:
            self._status_label.setText(self.tr("No MIDI events to save."))
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Live Monitor log"),
            str(user_paths.subfolder(user_paths.LOGS) / "midi-monitor-log.csv"),
            self.tr("CSV files (*.csv)"),
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
            _LOGGER.exception("Failed to save Live Monitor CSV log")
            self._status_label.setText(self.tr("Failed to save log: {error}").format(error=exc))
            return
        _LOGGER.info("Saved %d MIDI event(s) to CSV", len(self._events))
        self._status_label.setText(self.tr("Saved {count} MIDI event(s).").format(count=len(self._events)))

    @property
    def is_running(self) -> bool:
        return self._running

    def listening_input_ports(self) -> list[str]:
        """Input ports this monitor holds open right now (none when stopped).
        Another listener (the menu bar's ● Rec) reads these through
        ``eventReceived`` instead of opening them a second time, which
        Windows refuses: a MIDI input there has one client only."""
        return self._monitor.input_names if self._running else []

    def ensure_monitoring_started(self) -> None:
        """Best-effort auto-start used when a mapping is loaded, so the By
        Channel/Deck/Controller layouts reflect live controller presses
        without a manual self.tr("Start monitoring") click (View menu -> "Auto-start
        Live Monitor on load", see MainWindow._load_tree).

        Never overrides an already-running session (a user who already
        picked specific ports here keeps that selection), and never pops a
        dialog for a busy/unavailable port the way the self.tr("Start monitoring")
        button does -- this runs silently in the background, so one port
        that fails to open (e.g. already claimed by another app) is just
        skipped and logged, instead of aborting monitoring on every port."""
        if self._running:
            return
        if self._lock_reason is not None:
            self._auto_start_pending = True
            return
        self._refresh_ports()
        self._select_all_sources()
        opened: list[str] = []
        for i in range(self._port_list.count()):
            if not self._is_checked(i):
                continue
            name = self._port_list.item(i).text()
            try:
                self._monitor.open_input(name)
                opened.append(name)
            except Exception:  # best-effort: one busy port shouldn't block the rest
                _LOGGER.warning("Live Monitor auto-start: could not open MIDI input %r", name, exc_info=True)
        if not opened:
            return
        self._running = True
        self._start_button.setText(self.tr("Stop monitoring"))
        self._status_label.setText(self.tr("Running ({count} input(s), auto-started)").format(count=len(opened)))
        _LOGGER.info("Live Monitor auto-started on mapping load: inputs=%s", opened)
        self._timer.start()

    @property
    def is_locked(self) -> bool:
        return self._lock_reason is not None

    def set_locked(self, reason: str | None) -> None:
        """Freezes Start/Stop and the input choice while another listener
        depends on the ports this monitor holds (issue #307: ● Rec reads the
        Live Monitor's ports from its stream and opens the others itself, so
        stopping it would silently drop those ports from the recording and
        starting it would try to open ports ● Rec holds -- refused on Windows).
        ``reason`` becomes the controls' tooltip; ``None`` unlocks, running
        any auto-start (mapping load) requested meanwhile."""
        self._lock_reason = reason
        locked = reason is not None
        for widget in (self._start_button, self._ports_box, self._virtual_checkbox):
            widget.setEnabled(not locked)
            widget.setToolTip(reason or "")
        if not locked and self._auto_start_pending:
            self._auto_start_pending = False
            self.ensure_monitoring_started()

    def shutdown(self) -> None:
        """Releases MIDI ports; call when the app is closing."""
        if self._running:
            self._stop()


__all__ = ["LiveMonitorView"]
