from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi.catalog._registry import ControlInfo
from djmidi.gui.port_list_utils import refresh_selectable_port_list
from djmidi.midi_io import list_output_ports
from djmidi.session_player import _parse_int, play_control_info_entries


class MetronomeView(QWidget):
    """Loop-oriented MIDI session player driven by the current Controller Setup session."""

    def __init__(
        self,
        all_rows_provider: Callable[[], list[ControlInfo]],
        selected_rows_provider: Callable[[], list[ControlInfo]],
        session_name_provider: Callable[[], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._all_rows_provider = all_rows_provider
        self._selected_rows_provider = selected_rows_provider
        self._session_name_provider = session_name_provider
        self._loop_scope = "selected"

        self._session_summary = QLabel()
        self._session_summary.setWordWrap(True)
        refresh_summary_button = QPushButton("Refresh session summary")
        refresh_summary_button.clicked.connect(self.refresh_session_summary)

        source_box = QGroupBox("Session source")
        source_layout = QVBoxLayout(source_box)
        source_layout.addWidget(self._session_summary)
        source_layout.addWidget(refresh_summary_button)

        self._output_port_list = QListWidget()
        self._output_port_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        refresh_output_button = QPushButton("Refresh output ports")
        refresh_output_button.clicked.connect(self._refresh_output_ports)

        output_box = QGroupBox("Output")
        output_layout = QVBoxLayout(output_box)
        output_layout.addWidget(self._output_port_list)
        output_layout.addWidget(refresh_output_button)

        self._value_edit = QLineEdit("127")
        self._hz_edit = QLineEdit("2.0")
        self._status = QLabel("Ready.")
        self._status.setWordWrap(True)

        play_selected_button = QPushButton("Play selected setup row(s) once")
        play_selected_button.clicked.connect(self._on_play_selected_once_clicked)
        play_all_button = QPushButton("Play all setup rows once")
        play_all_button.clicked.connect(self._on_play_all_once_clicked)
        start_selected_button = QPushButton("Start loop (selected setup rows)")
        start_selected_button.clicked.connect(lambda: self._start_loop("selected"))
        start_all_button = QPushButton("Start loop (all setup rows)")
        start_all_button.clicked.connect(lambda: self._start_loop("all"))
        stop_button = QPushButton("Stop loop")
        stop_button.clicked.connect(self._stop_loop)

        transport_box = QGroupBox("Transport")
        transport_layout = QVBoxLayout(transport_box)
        transport_layout.addWidget(QLabel("Value / velocity (0-127)"))
        transport_layout.addWidget(self._value_edit)
        transport_layout.addWidget(QLabel("Loop frequency (Hz)"))
        transport_layout.addWidget(self._hz_edit)
        transport_layout.addWidget(play_selected_button)
        transport_layout.addWidget(play_all_button)
        transport_layout.addWidget(start_selected_button)
        transport_layout.addWidget(start_all_button)
        transport_layout.addWidget(stop_button)
        transport_layout.addWidget(self._status)
        transport_layout.addStretch(1)

        top_row = QHBoxLayout()
        top_row.addWidget(source_box, 1)
        top_row.addWidget(output_box, 1)
        top_row.addWidget(transport_box, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addStretch(1)

        self._loop_timer = QTimer(self)
        self._loop_timer.timeout.connect(self._on_loop_tick)

        self._refresh_output_ports()
        self.refresh_session_summary()

    def refresh_session_summary(self) -> None:
        session_name = self._session_name_provider().strip() or "(unnamed setup session)"
        all_rows = len(self._all_rows_provider())
        selected_rows = len(self._selected_rows_provider())
        self._session_summary.setText(
            f"Current setup session: {session_name}\n"
            f"All rows: {all_rows}\n"
            f"Selected rows in Controller Setup: {selected_rows}"
        )

    def _refresh_output_ports(self) -> None:
        refresh_selectable_port_list(self._output_port_list, list_output_ports)

    def _selected_output_port(self) -> str:
        item = self._output_port_list.currentItem()
        if item is None:
            raise ValueError("No output port selected")
        return item.text()

    def _entries_for_scope(self, scope: str) -> list[ControlInfo]:
        if scope == "selected":
            return self._selected_rows_provider()
        return self._all_rows_provider()

    def _play_scope_once(self, scope: str) -> tuple[int, int]:
        entries = self._entries_for_scope(scope)
        if not entries:
            return 0, 0
        value = _parse_int(self._value_edit.text(), "Value", 0, 127)
        stats = play_control_info_entries(self._selected_output_port(), entries, value)
        return stats.sent_messages, stats.skipped_entries

    def _on_play_selected_once_clicked(self) -> None:
        try:
            sent, skipped = self._play_scope_once("selected")
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to play rows", str(exc))
            return
        self._status.setText(f"Played selected rows once: {sent} MIDI message(s), {skipped} skipped.")
        self.refresh_session_summary()

    def _on_play_all_once_clicked(self) -> None:
        try:
            sent, skipped = self._play_scope_once("all")
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to play rows", str(exc))
            return
        self._status.setText(f"Played all rows once: {sent} MIDI message(s), {skipped} skipped.")
        self.refresh_session_summary()

    def _start_loop(self, scope: str) -> None:
        entries = self._entries_for_scope(scope)
        if not entries:
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
        self._status.setText(f"Loop started for {scope} rows at {hz:.2f} Hz.")
        self.refresh_session_summary()

    def _stop_loop(self) -> None:
        self._loop_timer.stop()
        self._status.setText("Loop stopped.")

    def _on_loop_tick(self) -> None:
        try:
            sent, skipped = self._play_scope_once(self._loop_scope)
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            self._loop_timer.stop()
            QMessageBox.critical(self, "Loop stopped", str(exc))
            return
        self._status.setText(f"Loop tick ({self._loop_scope}): {sent} MIDI message(s), {skipped} skipped.")

    def shutdown(self) -> None:
        if self._loop_timer.isActive():
            self._loop_timer.stop()


__all__ = ["MetronomeView"]
