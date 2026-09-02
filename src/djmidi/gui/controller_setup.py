"""Controller Setup tab: builds a brand-new catalog/<slug>.py module for a
controller with no official MIDI docs yet, by either learning MIDI events
live (pressing buttons on the physical device, via the same polled
midi_io.MidiMonitor infrastructure as the Live Monitor tab) or importing an
existing Serato XML config's set of unique (channel, event_type, control)
triggers as a starting point. The in-progress draft can be saved/loaded as
its own session file (distinct from importing a Serato XML). "Apply now"
registers the draft into the live catalog registry immediately (in-memory
only, replacing any prior same-name registration) so it shows up right away
in this session's Layout/By Controller/Controller Images tabs — see
MainWindow._on_controller_applied, which refreshes those views' controller
combos and, if a config is loaded, rebuilds the By Controller tree. Export
writes the persisted catalog/<slug>.py module in the same hand-written style
as ddj_xp2.py/xdj_xz.py. Neither action ever edits catalog/__init__.py — the
one remaining import line for a *future* app launch to pick the controller up
automatically is left as an explicit manual step (see that module's
docstring), same as adding any hand-written controller.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from pathlib import Path
from typing import cast

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.catalog._registry import (
    ControlInfo,
    NoteOrCC,
    _event_kind,
    register,
)
from djmidi.catalog.codegen import (
    build_definition,
    find_trigger_conflicts,
    generate_module_source,
)
from djmidi.catalog.community import (
    build_submission_payload,
    payload_json,
    submission_issue_url,
    summarise_source,
)
from djmidi.gui.controller_submission_dialog import ControllerSubmissionDialog
from djmidi.gui.port_list_utils import (
    refresh_checked_port_list,
    refresh_selectable_port_list,
)
from djmidi.midi_io import (
    MidiEvent,
    MidiMonitor,
    list_input_ports,
    list_output_ports,
    send_midi_message,
)
from djmidi.model import MidiConfig
from djmidi.parser import parse_file
from djmidi.session_player import (
    _parse_int,
    play_control_info_entries,
    replay_midi_events,
)

_LOGGER = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 30

_CAPTURE_HELP = (
    "Press discrete buttons/pads one at a time. Continuous controls (faders, TRIM/EQ knobs, "
    "jog wheels, touch strips/encoders) will be captured too but aren't in scope for this "
    "catalog — delete those rows before exporting."
)
_IMPORT_HELP = (
    "Only the raw (channel, type, control) trigger is imported — Serato function names aren't "
    "physical control names, so Section/Name must still be filled in by hand for each imported row."
)
_APPLY_HELP = (
    "Apply now registers this draft in the running app so it shows up in the Layout, By "
    "Controller, and Controller Images tabs — in-memory only, lost on restart. \"Generate "
    "catalog module…\" writes the permanent catalog/<slug>.py. \"Submit to community catalog…\" "
    "opens a pre-filled GitHub issue with the profile JSON so it can be reviewed and shipped as "
    "a built-in (reference images are not included)."
)

_DDJ_XP2_PAD_MODE_NOTES = {1: 27, 2: 30, 3: 32, 4: 34}


def _slugify(name: str) -> str:
    lowered = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if not slug:
        return ""
    if not slug[0].isalpha():
        slug = f"_{slug}"
    return slug


class ControllerSetupView(QWidget):
    controllerApplied = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._monitor = MidiMonitor()
        self._rows: list[ControlInfo] = []
        self._recorded_events: list[MidiEvent] = []
        self._replay_generation = 0
        self._sources: list[str] = []
        self._devices: list[str] = []
        self._controller_name = ""
        # Absolute path to a user-supplied reference image (issue #16); shown in
        # the Controller Images tab once the draft is applied, persisted in the
        # session JSON, and emitted as reference_image by "Generate catalog
        # module…". "" means none attached.
        self._reference_image = ""
        self._dirty = False
        self._rebuilding = False
        self._learning = False
        self._applied_names: set[str] = set()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Controller name, e.g. Behringer CMD LC-1")
        self._name_edit.setMinimumHeight(30)
        self._name_edit.textChanged.connect(self._on_name_changed)
        name_label = QLabel("Controller name:")
        name_label.setStyleSheet("QLabel { font-weight: bold; }")
        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_row.addWidget(name_label)
        name_row.addWidget(self._name_edit, 1)

        new_button = QPushButton(self._get_icon("new"), "")
        new_button.setToolTip("New session")
        new_button.clicked.connect(self._on_new_session_clicked)
        load_button = QPushButton(self._get_icon("open"), "")
        load_button.setToolTip("Load session…")
        load_button.clicked.connect(self._on_load_session_clicked)
        save_button = QPushButton(self._get_icon("save"), "")
        save_button.setToolTip("Save session…")
        save_button.clicked.connect(self._on_save_session_clicked)
        clear_button = QPushButton(self._get_icon("clear"), "")
        clear_button.setToolTip("Clear captured rows")
        clear_button.clicked.connect(self._on_clear_rows_clicked)

        self._port_list = QListWidget()
        self._port_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # QListWidget.sizeHint() ignores setMinimumHeight (it returns a fixed
        # ~192px regardless), which was inflating this whole panel row far
        # beyond its actual content; capping the height pins both ends.
        self._port_list.setMinimumHeight(70)
        self._port_list.setMaximumHeight(90)
        refresh_button = QPushButton(self._get_icon("refresh"), "")
        refresh_button.setToolTip("Refresh ports")
        refresh_button.clicked.connect(self._refresh_ports)
        self._learn_button = QPushButton(self._get_icon("start"), "")
        self._learn_button.setToolTip("Start learning")
        self._learn_button.clicked.connect(self._toggle_learning)
        self._learn_status = QLabel("Stopped")
        self._learn_status.setStyleSheet(
            "QLabel {"
            " font-weight: bold; padding: 6px 10px; margin-top: 4px;"
            " background: #202d42; border: 1px solid #3a506d; border-radius: 4px;"
            " }"
        )
        capture_help_button = self._help_button("MIDI input (learn from controller)", _CAPTURE_HELP)
        capture_box, capture_layout = self._titled_panel(
            "MIDI input", [refresh_button, self._learn_button, capture_help_button]
        )
        capture_layout.addWidget(self._port_list)
        capture_layout.addSpacing(6)
        capture_layout.addWidget(self._learn_status)

        import_button = QPushButton(self._get_icon("import"), "")
        import_button.setToolTip("Import from Serato XML…")
        import_button.clicked.connect(self._on_import_xml_clicked)
        self._attach_image_button = QPushButton(self._get_icon("image"), "")
        self._attach_image_button.setToolTip("Attach reference image…")
        self._attach_image_button.clicked.connect(self._on_attach_image_clicked)
        import_help_button = self._help_button("Import", _IMPORT_HELP)
        self._image_label = QLabel("No reference image")
        self._image_label.setWordWrap(True)
        self._image_label.setStyleSheet("QLabel { color: #8fa7bd; border: none; }")

        self._output_port_list = QListWidget()
        self._output_port_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        refresh_output_button = QPushButton(self._get_icon("refresh"), "Refresh output ports")
        refresh_output_button.clicked.connect(self._refresh_output_ports)

        self._send_type_edit = QLineEdit("note_on")
        self._send_channel_edit = QLineEdit("1")
        self._send_data1_edit = QLineEdit("27")
        self._send_data2_edit = QLineEdit("127")
        self._send_delay_ms_edit = QLineEdit("80")
        for field in (
            self._send_type_edit,
            self._send_channel_edit,
            self._send_data1_edit,
            self._send_data2_edit,
            self._send_delay_ms_edit,
        ):
            field.setMinimumHeight(28)
        send_once_button = QPushButton(self._get_icon("start"), "Send once")
        send_once_button.clicked.connect(self._on_send_output_once_clicked)
        send_double_button = QPushButton(self._get_icon("start"), "Send double-click (NOTE)")
        send_double_button.clicked.connect(self._on_send_output_double_clicked)
        send_selected_button = QPushButton(self._get_icon("start"), "Play selected session row(s)")
        send_selected_button.clicked.connect(self._on_send_selected_rows_clicked)
        send_all_button = QPushButton(self._get_icon("start"), "Play all session rows")
        send_all_button.clicked.connect(self._on_send_all_rows_clicked)
        replay_button = QPushButton(self._get_icon("refresh"), "Replay recorded session")
        replay_button.clicked.connect(self._on_replay_recorded_session_clicked)

        self._send_status = QLabel("No MIDI output sent yet.")

        output_box = QGroupBox("MIDI Output")
        output_box.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 12px; }")
        output_layout = QHBoxLayout(output_box)
        output_layout.setContentsMargins(10, 12, 10, 10)
        output_layout.setSpacing(15)

        output_ports = QVBoxLayout()
        output_ports.setSpacing(6)
        output_ports_label = QLabel("Available output ports")
        output_ports_label.setStyleSheet("QLabel { font-weight: bold; }")
        output_ports.addWidget(output_ports_label)
        self._output_port_list.setMinimumWidth(220)
        self._output_port_list.setMinimumHeight(130)
        output_ports.addWidget(self._output_port_list, 1)
        refresh_output_button.setMinimumHeight(28)
        output_ports.addWidget(refresh_output_button)
        output_layout.addLayout(output_ports, 1)

        output_controls = QVBoxLayout()
        output_controls.setSpacing(8)
        output_controls_label = QLabel("Message and playback controls")
        output_controls_label.setStyleSheet("QLabel { font-weight: bold; }")
        output_controls.addWidget(output_controls_label)

        send_form = QFormLayout()
        send_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        send_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        send_form.setHorizontalSpacing(10)
        send_form.setVerticalSpacing(10)
        send_form.addRow("Type", self._send_type_edit)
        send_form.addRow("Channel", self._send_channel_edit)
        send_form.addRow("Data1", self._send_data1_edit)
        send_form.addRow("Value", self._send_data2_edit)
        send_form.addRow("Delay (ms)", self._send_delay_ms_edit)
        message_column = QVBoxLayout()
        message_column.setSpacing(6)
        message_column.addWidget(self._column_label("Send message"))
        message_column.addLayout(send_form)
        message_column.addStretch(1)

        action_grid = QVBoxLayout()
        action_grid.setSpacing(8)
        for button in (send_once_button, send_double_button, send_selected_button, send_all_button, replay_button):
            button.setMinimumHeight(28)
            action_grid.addWidget(button)
        action_grid.addStretch(1)
        actions_column = QVBoxLayout()
        actions_column.setSpacing(6)
        actions_column.addWidget(self._column_label("Playback"))
        actions_column.addLayout(action_grid)

        pad_grid = QGridLayout()
        pad_grid.setHorizontalSpacing(6)
        pad_grid.setVerticalSpacing(6)
        for index, mode in enumerate(range(1, 9)):
            button = QPushButton(f"PAD {mode}")
            button.setMinimumWidth(90)
            button.setMinimumHeight(28)
            button.clicked.connect(lambda _checked=False, m=mode: self._on_send_ddj_xp2_pad_mode(m))
            pad_grid.addWidget(button, index // 2, index % 2)
        pads_column = QVBoxLayout()
        pads_column.setSpacing(6)
        pads_column.addWidget(self._column_label("Pad modes (DDJ-XP2)"))
        pads_column.addLayout(pad_grid)
        pads_column.addStretch(1)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(20)
        controls_row.addLayout(message_column, 1)
        controls_row.addLayout(actions_column, 1)
        controls_row.addLayout(pads_column, 1)
        output_controls.addLayout(controls_row)

        output_controls.addSpacing(6)
        self._send_status.setStyleSheet("QLabel { padding: 6px; border-radius: 3px; }")
        output_controls.addWidget(self._send_status)
        output_layout.addLayout(output_controls, 2)

        check_button = QPushButton(self._get_icon("refresh"), "")
        check_button.setToolTip("Check for conflicts")
        check_button.clicked.connect(self._on_check_conflicts_clicked)
        self._apply_button = QPushButton(self._get_icon("apply"), "")
        self._apply_button.setToolTip("Apply now (this session)")
        self._apply_button.clicked.connect(self._on_apply_clicked)
        export_button = QPushButton(self._get_icon("export"), "")
        export_button.setToolTip("Generate catalog module…")
        export_button.clicked.connect(self._on_export_clicked)
        submit_button = QPushButton(self._get_icon("submit"), "")
        submit_button.setToolTip("Submit to community catalog…")
        submit_button.clicked.connect(self._on_submit_clicked)
        apply_help_button = self._help_button("Apply / Export", _APPLY_HELP)

        # Session, Import and Apply/Export are merged into one "Draft" panel: a
        # single horizontal toolbar of icon actions with a separator between
        # each group.
        draft_box, draft_layout = self._titled_panel("Draft", [])
        draft_layout.addLayout(
            self._toolbar_row(
                [
                    ("Session", [new_button, load_button, save_button, clear_button]),
                    ("Import", [import_button, self._attach_image_button, import_help_button]),
                    (
                        "Apply / Export",
                        [check_button, self._apply_button, export_button, submit_button, apply_help_button],
                    ),
                ]
            )
        )
        draft_layout.addWidget(self._image_label)

        # "MIDI input" (learn) sits at the start of the same row as "MIDI
        # Output"; top-aligned so it stays as tall as its own content instead
        # of stretching to the (taller) MIDI Output panel.
        io_row = QHBoxLayout()
        io_row.setSpacing(12)
        io_row.addWidget(capture_box, 1, Qt.AlignmentFlag.AlignTop)
        io_row.addWidget(output_box, 3)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(["Section", "Name", "Type", "Channel(s)", "Data1", "Source", "Device"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setMinimumHeight(160)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.cellChanged.connect(self._on_cell_changed)

        delete_button = QPushButton(self._get_icon("delete"), "Delete selected row(s)")
        delete_button.setMinimumHeight(28)
        delete_button.clicked.connect(self._on_delete_selected_clicked)
        add_button = QPushButton(self._get_icon("add"), "Add row")
        add_button.setMinimumHeight(28)
        add_button.clicked.connect(self._on_add_row_clicked)
        bulk_section_button = QPushButton(self._get_icon("apply"), "Set section for selected rows…")
        bulk_section_button.setMinimumHeight(28)
        bulk_section_button.setToolTip("Assign one Section name to every selected row")
        bulk_section_button.clicked.connect(self._on_bulk_set_section_clicked)
        bulk_name_button = QPushButton(self._get_icon("apply"), "Set name for selected rows…")
        bulk_name_button.setMinimumHeight(28)
        bulk_name_button.setToolTip("Assign a Name to every selected row, optionally auto-numbered (PAD 1, PAD 2, …)")
        bulk_name_button.clicked.connect(self._on_bulk_set_name_clicked)
        row_buttons = QHBoxLayout()
        row_buttons.setSpacing(8)
        row_buttons.addWidget(delete_button)
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(bulk_section_button)
        row_buttons.addWidget(bulk_name_button)
        row_buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(name_row)
        layout.addWidget(draft_box, 0)
        layout.addLayout(io_row, 0)
        layout.addWidget(self._table, 1)
        layout.addLayout(row_buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        self._refresh_ports()
        self._refresh_output_ports()

    def _get_icon(self, icon_type: str) -> QIcon:
        """Get a standard Qt icon by type name."""
        style = self.style()
        icon_map = {
            "new": QStyle.StandardPixmap.SP_FileDialogNewFolder,
            "open": QStyle.StandardPixmap.SP_DialogOpenButton,
            "save": QStyle.StandardPixmap.SP_DialogSaveButton,
            "delete": QStyle.StandardPixmap.SP_TrashIcon,
            "add": QStyle.StandardPixmap.SP_FileIcon,
            "refresh": QStyle.StandardPixmap.SP_BrowserReload,
            "start": QStyle.StandardPixmap.SP_MediaPlay,
            "stop": QStyle.StandardPixmap.SP_MediaStop,
            "clear": QStyle.StandardPixmap.SP_DialogResetButton,
            "apply": QStyle.StandardPixmap.SP_DialogApplyButton,
            "export": QStyle.StandardPixmap.SP_DialogSaveButton,
            "import": QStyle.StandardPixmap.SP_ArrowDown,
            "help": QStyle.StandardPixmap.SP_MessageBoxQuestion,
            "image": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "submit": QStyle.StandardPixmap.SP_ArrowUp,
        }
        return style.standardIcon(icon_map.get(icon_type, QStyle.StandardPixmap.SP_FileIcon))

    def _help_button(self, title: str, text: str) -> QPushButton:
        button = QPushButton(self._get_icon("help"), "")
        button.setToolTip(f"{title} help")
        button.clicked.connect(lambda: QMessageBox.information(self, title, text))
        return button

    def _titled_panel(self, title: str, header_buttons: list[QPushButton]) -> tuple[QFrame, QVBoxLayout]:
        """A QGroupBox-styled panel with icon-only action buttons in its title
        row instead of stacked full-width buttons in its body — QGroupBox's
        native title bar can't host widgets, so this is a plain QFrame styled
        to match (see theme.py's QGroupBox rule)."""
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #151e2b; border: 1px solid #2b3b53; border-radius: 9px; }"
        )
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        title_label = QLabel(title)
        title_label.setStyleSheet("QLabel { font-weight: bold; color: #8fe8ff; border: none; }")
        header.addWidget(title_label)
        header.addStretch(1)
        for button in header_buttons:
            button.setFixedSize(28, 28)
            header.addWidget(button)
        outer.addLayout(header)

        body = QVBoxLayout()
        body.setSpacing(6)
        outer.addLayout(body)
        return frame, body

    @staticmethod
    def _icon_button_grid(buttons: list[QPushButton], columns: int = 2) -> QGridLayout:
        """A compact 2-column grid of 28x28 icon buttons, so the Session,
        Import, and Apply/Export panels all place their actions the same way
        (in the panel body, not crammed into the title bar)."""
        grid = QGridLayout()
        grid.setSpacing(6)
        for index, button in enumerate(buttons):
            button.setFixedSize(28, 28)
            grid.addWidget(button, index // columns, index % columns)
        grid.setColumnStretch(columns, 1)
        return grid

    @classmethod
    def _toolbar_row(cls, groups: list[tuple[str, list[QPushButton]]]) -> QHBoxLayout:
        """One horizontal strip: each group is a caption followed by its
        28x28 icon buttons, and the groups are spread across the full width
        (first flush left, last flush right)."""
        row = QHBoxLayout()
        row.setSpacing(6)
        for index, (caption, buttons) in enumerate(groups):
            if index:
                row.addStretch(1)
            label = cls._column_label(caption)
            row.addWidget(label)
            row.addSpacing(2)
            for button in buttons:
                button.setFixedSize(28, 28)
                row.addWidget(button)
        return row

    @staticmethod
    def _column_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("QLabel { font-weight: bold; color: #8fa7bd; font-size: 11px; }")
        return label

    # -- controller name -------------------------------------------------

    def _on_name_changed(self, text: str) -> None:
        self._controller_name = text.strip()
        self._rows = [dataclasses.replace(row, controller=self._controller_name) for row in self._rows]
        self._mark_dirty()

    def _slug(self) -> str:
        return _slugify(self._controller_name)

    # -- dedup / row mutation ---------------------------------------------

    def _existing_keys(self) -> set[tuple[str, str, str]]:
        keys: set[tuple[str, str, str]] = set()
        for entry in self._rows:
            for channel in entry.channels:
                keys.add((channel, entry.note_or_cc, entry.data1))
        return keys

    def _maybe_add_row(self, channel: str, kind: str, data1: str, source: str, device: str = "") -> bool:
        if (channel, kind, data1) in self._existing_keys():
            return False
        typed_kind = cast(NoteOrCC, kind)
        entry = ControlInfo(self._controller_name, "", "", typed_kind, (channel,), data1)
        self._rows.append(entry)
        self._sources.append(source)
        self._devices.append(device)
        self._append_row_to_table(entry, source, device)
        self._mark_dirty()
        return True

    def _mark_dirty(self) -> None:
        self._dirty = True

    # -- table <-> rows ----------------------------------------------------

    def _rebuild_table(self) -> None:
        self._rebuilding = True
        self._table.setRowCount(0)
        self._rebuilding = False
        for entry, source, device in zip(self._rows, self._sources, self._devices):
            self._append_row_to_table(entry, source, device)

    def _append_row_to_table(self, entry: ControlInfo, source: str, device: str = "") -> None:
        self._rebuilding = True
        row = self._table.rowCount()
        self._table.insertRow(row)
        values = [entry.section, entry.name, entry.note_or_cc, ", ".join(entry.channels), entry.data1, source, device]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in (5, 6):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, col, item)
        self._rebuilding = False
        self._table.setCurrentCell(row, 1)

    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._rebuilding or column in (5, 6) or row >= len(self._rows):
            return
        section = self._table.item(row, 0).text().strip()
        name = self._table.item(row, 1).text().strip()
        note_or_cc = self._table.item(row, 2).text().strip().upper()
        channels = tuple(c.strip() for c in self._table.item(row, 3).text().split(",") if c.strip())
        data1 = self._table.item(row, 4).text().strip()
        typed_kind = cast(NoteOrCC, note_or_cc)
        self._rows[row] = ControlInfo(self._controller_name, section, name, typed_kind, channels, data1)
        self._mark_dirty()

    def _on_delete_selected_clicked(self) -> None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            del self._rows[row]
            del self._sources[row]
            del self._devices[row]
        self._rebuild_table()
        self._mark_dirty()

    def _on_add_row_clicked(self) -> None:
        entry = ControlInfo(self._controller_name, "", "", "NOTE", ("1",), "0")
        self._rows.append(entry)
        self._sources.append("manual")
        self._devices.append("")
        self._append_row_to_table(entry, "manual", "")
        self._mark_dirty()

    # -- bulk Section / Name assignment -----------------------------------

    def _selected_table_rows(self) -> list[int]:
        """Distinct selected row indices, in ascending order. Unlike
        _selected_row_indices() this does NOT fall back to "all rows" when
        nothing is selected — a bulk edit with no selection is a no-op."""
        return sorted(
            {index.row() for index in self._table.selectedIndexes() if 0 <= index.row() < len(self._rows)}
        )

    def _apply_bulk_edit(self, indices: list[int], mutate) -> None:
        """Replace each selected row with mutate(rank, row) (rank is the 0-based
        position within the selection), then resync the table, mark the draft
        dirty, restore the selection, and re-run the trigger conflict check
        since a bad bulk edit can collide (section, name) pairs."""
        for rank, row_index in enumerate(indices):
            self._rows[row_index] = mutate(rank, self._rows[row_index])
        self._rebuild_table()
        self._mark_dirty()
        selection_model = self._table.selectionModel()
        selection_model.clearSelection()
        flags = (
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        )
        for row_index in indices:
            selection_model.select(self._table.model().index(row_index, 0), flags)
        conflicts = find_trigger_conflicts(self._rows)
        if conflicts:
            _LOGGER.warning(
                "Bulk edit on %r produced %d trigger conflict(s): %s",
                self._controller_name,
                len(conflicts),
                conflicts,
            )
            QMessageBox.warning(
                self,
                "Bulk edit created conflicts",
                "The bulk edit left colliding triggers:\n\n" + "\n".join(conflicts),
            )

    def _on_bulk_set_section_clicked(self) -> None:
        indices = self._selected_table_rows()
        if not indices:
            QMessageBox.information(self, "No rows selected", "Select one or more rows first.")
            return
        text, ok = QInputDialog.getText(
            self, "Set section", f"Section name for {len(indices)} selected row(s):"
        )
        section = text.strip()
        if not ok or not section:
            return
        self._apply_bulk_edit(indices, lambda _rank, row: dataclasses.replace(row, section=section))

    def _on_bulk_set_name_clicked(self) -> None:
        indices = self._selected_table_rows()
        if not indices:
            QMessageBox.information(self, "No rows selected", "Select one or more rows first.")
            return
        text, ok = QInputDialog.getText(
            self, "Set name", f"Name for {len(indices)} selected row(s):"
        )
        base = text.strip()
        if not ok or not base:
            return
        auto_number = False
        if len(indices) > 1:
            reply = QMessageBox.question(
                self,
                "Auto-number?",
                f"Number the name across the selected rows ('{base} 1', '{base} 2', …)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            auto_number = reply == QMessageBox.StandardButton.Yes

        def mutate(rank: int, row: ControlInfo) -> ControlInfo:
            name = f"{base} {rank + 1}" if auto_number else base
            return dataclasses.replace(row, name=name)

        self._apply_bulk_edit(indices, mutate)

    # -- session lifecycle --------------------------------------------------

    def _confirm(self, text: str) -> bool:
        reply = QMessageBox.question(self, "Confirm", text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes

    def _reset(self, *, clear_name: bool) -> None:
        self._stop_replay()
        self._rows = []
        self._recorded_events = []
        self._sources = []
        self._devices = []
        self._reference_image = ""
        self._update_image_label()
        if clear_name:
            self._controller_name = ""
            self._name_edit.setText("")
            # This draft's identity ends here — any name(s) it applied earlier
            # must not grant a future, unrelated draft permission to silently
            # re-replace them (see _on_apply_clicked's hard-block).
            self._applied_names = set()
        self._rebuild_table()
        self._dirty = False

    def _on_new_session_clicked(self) -> None:
        if self._dirty and not self._confirm("This will discard the current unsaved draft. Continue?"):
            return
        self._reset(clear_name=True)

    def _on_clear_rows_clicked(self) -> None:
        if self._dirty and not self._confirm("This will discard the current unsaved rows (keeping the controller name). Continue?"):
            return
        self._reset(clear_name=False)

    # -- capture (learn mode) ------------------------------------------------

    def _refresh_ports(self) -> None:
        refresh_checked_port_list(self._port_list, list_input_ports)

    def _refresh_output_ports(self) -> None:
        refresh_selectable_port_list(self._output_port_list, list_output_ports)

    def _selected_output_port(self) -> str:
        item = self._output_port_list.currentItem()
        if item is None:
            raise ValueError("No output port selected")
        return item.text()

    def _send_note_click(self, *, note: int, double_click: bool) -> None:
        port = self._selected_output_port()
        channel = _parse_int(self._send_channel_edit.text(), "Channel", 1, 16)
        velocity = _parse_int(self._send_data2_edit.text(), "Data2", 0, 127)
        delay_ms = _parse_int(self._send_delay_ms_edit.text(), "Double-click delay", 0, 5_000)

        def do_click() -> None:
            send_midi_message(
                output_port_name=port,
                event_type="note_on",
                channel_1_based=channel,
                data1=note,
                data2=velocity,
            )
            send_midi_message(
                output_port_name=port,
                event_type="note_off",
                channel_1_based=channel,
                data1=note,
                data2=0,
            )

        do_click()
        if double_click:
            QTimer.singleShot(delay_ms, do_click)

    def _on_send_output_once_clicked(self) -> None:
        try:
            send_midi_message(
                output_port_name=self._selected_output_port(),
                event_type=self._send_type_edit.text(),
                channel_1_based=_parse_int(self._send_channel_edit.text(), "Channel", 1, 16),
                data1=_parse_int(self._send_data1_edit.text(), "Data1", 0, 127),
                data2=_parse_int(self._send_data2_edit.text(), "Data2", 0, 127),
            )
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to send MIDI", str(exc))
            return
        self._send_status.setText("MIDI message sent.")

    def _on_send_output_double_clicked(self) -> None:
        try:
            note = _parse_int(self._send_data1_edit.text(), "Data1", 0, 127)
            self._send_note_click(note=note, double_click=True)
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to send MIDI", str(exc))
            return
        self._send_status.setText("Double-click MIDI sequence sent.")

    def _on_send_ddj_xp2_pad_mode(self, mode: int) -> None:
        if mode not in (1, 2, 3, 4, 5, 6, 7, 8):
            QMessageBox.critical(self, "Unsupported mode", f"Unsupported DDJ-XP2 pad mode: {mode}")
            return
        if mode <= 4:
            note = _DDJ_XP2_PAD_MODE_NOTES[mode]
            double_click = False
        else:
            note = _DDJ_XP2_PAD_MODE_NOTES[mode - 4]
            double_click = True
        self._send_data1_edit.setText(str(note))
        try:
            self._send_note_click(note=note, double_click=double_click)
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to send MIDI", str(exc))
            return
        self._send_status.setText(f"Sent DDJ-XP2 PAD MODE {mode} trigger.")

    def _selected_row_indices(self) -> list[int]:
        selected = sorted({index.row() for index in self._table.selectedIndexes()})
        if selected:
            return selected
        return list(range(len(self._rows)))

    def session_rows(self) -> list[ControlInfo]:
        return list(self._rows)

    def recorded_session_events(self) -> list[MidiEvent]:
        return list(self._recorded_events)

    def selected_session_rows(self) -> list[ControlInfo]:
        return [self._rows[i] for i in self._selected_row_indices() if 0 <= i < len(self._rows)]

    def session_controller_name(self) -> str:
        return self._controller_name

    def _play_session_rows_once(self, row_indices: list[int]) -> tuple[int, int]:
        value = _parse_int(self._send_data2_edit.text(), "Data2", 0, 127)
        entries = [self._rows[i] for i in row_indices if 0 <= i < len(self._rows)]
        skipped = len(row_indices) - len(entries)
        stats = play_control_info_entries(
            self._selected_output_port(),
            entries,
            value,
            sender=send_midi_message,
        )
        return stats.sent_messages, stats.skipped_entries + skipped

    def _on_send_selected_rows_clicked(self) -> None:
        try:
            sent, skipped = self._play_session_rows_once(self._selected_row_indices())
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to play rows", str(exc))
            return
        self._send_status.setText(f"Played selected rows: {sent} MIDI message(s), {skipped} row(s) skipped.")

    def _on_send_all_rows_clicked(self) -> None:
        try:
            sent, skipped = self._play_session_rows_once(list(range(len(self._rows))))
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to play rows", str(exc))
            return
        self._send_status.setText(f"Played all rows: {sent} MIDI message(s), {skipped} row(s) skipped.")

    def _stop_replay(self) -> None:
        self._replay_generation += 1

    def _on_replay_recorded_session_clicked(self) -> None:
        if not self._recorded_events:
            QMessageBox.warning(self, "No recording", "No MIDI event has been recorded in this session.")
            return
        try:
            port = self._selected_output_port()
        except Exception as exc:  # noqa: BLE001 - show user-facing error
            QMessageBox.critical(self, "Failed to replay session", str(exc))
            return

        events = list(self._recorded_events)
        self._replay_generation += 1
        generation = self._replay_generation

        def schedule(index: int, previous_timestamp: float) -> None:
            if generation != self._replay_generation:
                return
            if index >= len(events):
                self._send_status.setText(f"Recorded session replayed: {len(events)} event(s).")
                return
            event = events[index]
            delay_ms = max(0, int((event.timestamp - previous_timestamp) * 1000))

            def send_and_continue() -> None:
                if generation != self._replay_generation:
                    return
                replay_midi_events(port, [event], sender=send_midi_message)
                schedule(index + 1, event.timestamp)

            QTimer.singleShot(delay_ms, send_and_continue)

        self._send_status.setText(f"Replaying recorded session ({len(events)} event(s))…")
        schedule(0, events[0].timestamp)

    def _is_checked(self, row: int) -> bool:
        return self._port_list.item(row).checkState() == Qt.CheckState.Checked

    def _toggle_learning(self) -> None:
        if self._learning:
            self._stop_learning()
        else:
            self._start_learning()

    def _start_learning(self) -> None:
        selected = [self._port_list.item(i).text() for i in range(self._port_list.count()) if self._is_checked(i)]
        try:
            for name in selected:
                self._monitor.open_input(name)
        except Exception as exc:  # noqa: BLE001 - surface device-open failures without partial learning
            self._monitor.close_all()
            self._learn_status.setText("Stopped")
            self._learn_button.setIcon(self._get_icon("start"))
            self._learn_button.setToolTip("Start learning")
            QMessageBox.warning(self, "Cannot start MIDI learning", str(exc))
            return
        self._learning = True
        self._learn_button.setIcon(self._get_icon("stop"))
        self._learn_button.setToolTip("Stop learning")
        self._learn_status.setText(f"Listening ({len(selected)} input(s))")
        _LOGGER.info("Controller Setup learning started: inputs=%s", selected)
        self._timer.start()

    def _stop_learning(self) -> None:
        self._timer.stop()
        self._monitor.close_all()
        self._learning = False
        self._learn_button.setIcon(self._get_icon("start"))
        self._learn_button.setToolTip("Start learning")
        self._learn_status.setText("Stopped")
        _LOGGER.info("Controller Setup learning stopped (%d row(s) captured)", len(self._rows))

    def _poll(self) -> None:
        for event in self._monitor.poll():
            self._recorded_events.append(event)
            kind = _event_kind(event.event_type)
            if kind is None:
                continue
            self._maybe_add_row(event.channel, kind, event.data1, "learned", event.port)

    # -- import from Serato XML ----------------------------------------------

    def _import_config(self, config: MidiConfig, device: str = "") -> int:
        added = 0
        for control in config.controls:
            kind = _event_kind(control.event_type)
            if kind is None:
                continue
            if self._maybe_add_row(control.channel, kind, control.control, "xml-import", device):
                added += 1
        return added

    def _on_import_xml_clicked(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Import Serato MIDI config", "", "XML files (*.xml)")
        if not path_str:
            return
        try:
            config = parse_file(path_str)
        except Exception as exc:
            _LOGGER.exception("Failed to import Serato XML %s into Controller Setup", path_str)
            QMessageBox.critical(self, "Failed to import file", str(exc))
            return
        added = self._import_config(config, Path(path_str).name)
        _LOGGER.info("Imported %d new trigger(s) from %s into Controller Setup", added, path_str)
        QMessageBox.information(self, "Import complete", f"Added {added} new trigger(s) (others already present were skipped).")

    # -- reference image ----------------------------------------------------

    def _update_image_label(self) -> None:
        if self._reference_image:
            self._image_label.setText(f"Reference image: {Path(self._reference_image).name}")
        else:
            self._image_label.setText("No reference image")

    def set_reference_image(self, path: str) -> None:
        self._reference_image = path.strip()
        self._update_image_label()
        self._mark_dirty()

    def _on_attach_image_clicked(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Attach controller reference image", "", "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if not path_str:
            # Cancelling with an image already attached is the way to remove it.
            if self._reference_image and self._confirm("Remove the attached reference image?"):
                self.set_reference_image("")
            return
        self.set_reference_image(path_str)
        _LOGGER.info("Attached reference image %s to Controller Setup draft %r", path_str, self._controller_name)
        QMessageBox.information(
            self,
            "Reference image attached",
            "The image is referenced by its path on this machine — it is not copied into the "
            "project. It shows in the Controller Images tab after \"Apply now\", and is saved in "
            "the session JSON. \"Generate catalog module…\" writes reference_image=<filename>; place "
            "a copy at assets/controllers/<filename> if you want it bundled (respecting its "
            "licence — user-supplied images are your responsibility).",
        )

    # -- session save / load --------------------------------------------------

    def _rows_to_session_dict(self) -> dict:
        return {
            "version": 1,
            "controller_name": self._controller_name,
            "reference_image": self._reference_image,
            "recorded_events": [
                {
                    "direction": event.direction,
                    "channel": event.channel,
                    "event_type": event.event_type,
                    "data1": event.data1,
                    "data2": event.data2,
                    "timestamp": event.timestamp,
                    "port": event.port,
                }
                for event in self._recorded_events
            ],
            "rows": [
                {
                    "section": entry.section,
                    "name": entry.name,
                    "note_or_cc": entry.note_or_cc,
                    "channels": list(entry.channels),
                    "data1": entry.data1,
                    "source": source,
                    "device": device,
                }
                for entry, source, device in zip(self._rows, self._sources, self._devices)
            ],
        }

    def _save_session(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self._rows_to_session_dict(), indent=2))
        self._dirty = False

    def _load_session(self, path: str | Path) -> None:
        data = json.loads(Path(path).read_text())
        if data.get("version") != 1:
            raise ValueError(f"Unsupported session version: {data.get('version')!r}")
        name = data["controller_name"]
        recorded_events = [MidiEvent(**raw) for raw in data.get("recorded_events", [])]
        rows = []
        sources = []
        devices = []
        for raw in data["rows"]:
            rows.append(
                ControlInfo(name, raw["section"], raw["name"], raw["note_or_cc"], tuple(raw["channels"]), raw["data1"])
            )
            sources.append(raw.get("source", "manual"))
            devices.append(raw.get("device", ""))
        self._stop_replay()
        self._controller_name = name
        self._name_edit.setText(name)
        self._reference_image = data.get("reference_image", "")
        self._update_image_label()
        self._rows = rows
        self._recorded_events = recorded_events
        self._sources = sources
        self._devices = devices
        # A loaded session is a different draft as far as this run is concerned
        # (the JSON format doesn't record what this process previously applied),
        # so it must not inherit another draft's "already applied" permission —
        # see _on_apply_clicked's hard-block and _reset's matching reset.
        self._applied_names = set()
        self._rebuild_table()
        self._dirty = False

    def _on_save_session_clicked(self) -> None:
        default_name = f"{self._slug() or 'controller'}.json"
        path_str, _ = QFileDialog.getSaveFileName(self, "Save controller setup session", default_name, "JSON files (*.json)")
        if not path_str:
            return
        try:
            self._save_session(path_str)
        except OSError as exc:
            _LOGGER.exception("Failed to save Controller Setup session to %s", path_str)
            QMessageBox.critical(self, "Failed to save session", str(exc))
            return
        _LOGGER.info("Saved Controller Setup session to %s (%d row(s))", path_str, len(self._rows))

    def _on_load_session_clicked(self) -> None:
        if self._dirty and not self._confirm("This will discard the current unsaved draft. Continue?"):
            return
        path_str, _ = QFileDialog.getOpenFileName(self, "Load controller setup session", "", "JSON files (*.json)")
        if not path_str:
            return
        try:
            self._load_session(path_str)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            _LOGGER.exception("Failed to load Controller Setup session from %s", path_str)
            QMessageBox.critical(self, "Failed to load session", str(exc))
            return
        _LOGGER.info("Loaded Controller Setup session from %s (%d row(s))", path_str, len(self._rows))

    # -- validation / export ---------------------------------------------------

    def _validate(self) -> list[str]:
        errors: list[str] = []
        if not self._slug():
            errors.append("Controller name must contain at least one letter or digit.")
        if not self._rows:
            errors.append("No rows captured yet.")

        def _bad_rows(predicate) -> list[int]:
            return [i + 1 for i, entry in enumerate(self._rows) if predicate(entry)]

        missing_name = _bad_rows(lambda e: not e.name.strip())
        if missing_name:
            errors.append(f"Rows missing a Name: {missing_name}")
        missing_section = _bad_rows(lambda e: not e.section.strip())
        if missing_section:
            errors.append(f"Rows missing a Section: {missing_section}")
        bad_kind = _bad_rows(lambda e: e.note_or_cc not in ("NOTE", "CC"))
        if bad_kind:
            errors.append(f"Rows with invalid Type (must be NOTE or CC): {bad_kind}")
        bad_channels = _bad_rows(lambda e: not e.channels or any(not c.strip() for c in e.channels))
        if bad_channels:
            errors.append(f"Rows missing a Channel: {bad_channels}")

        bad_data1 = []
        for i, entry in enumerate(self._rows):
            try:
                value = int(entry.data1)
            except ValueError:
                bad_data1.append(i + 1)
            else:
                if not 0 <= value <= 127:
                    bad_data1.append(i + 1)
        if bad_data1:
            errors.append(f"Rows with invalid Data1 (must be an integer 0-127): {bad_data1}")

        errors.extend(find_trigger_conflicts(self._rows))
        return errors

    def _build_definition_with_image(self):
        """The ControllerDefinition a draft turns into, with the attached
        reference image reduced to its basename (see `_reference_image`).
        Shared by module export and community submission so both derive from
        the exact same transformation "Apply now" uses."""
        image_name = Path(self._reference_image).name if self._reference_image else None
        return build_definition(self._controller_name, self._rows, image_name)

    def _export_module(self, path: str | Path) -> None:
        definition = self._build_definition_with_image()
        source = generate_module_source(
            self._controller_name, definition.static_entries, definition.reference_image
        )
        Path(path).write_text(source)

    def _on_submit_clicked(self) -> None:
        errors = self._validate()
        if errors:
            QMessageBox.warning(self, "Cannot submit yet", "\n".join(errors))
            return
        dialog = ControllerSubmissionDialog(summarise_source(self._sources), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = build_submission_payload(self._build_definition_with_image(), dialog.metadata())
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(payload_json(payload))
        url, inlined = submission_issue_url(payload)
        opened = QDesktopServices.openUrl(QUrl(url))
        _LOGGER.info(
            "Controller Setup submission for %r: browser_opened=%s json_inlined=%s entries=%d",
            self._controller_name,
            opened,
            inlined,
            len(payload["static_entries"]),
        )
        if not opened:
            QMessageBox.warning(
                self,
                "Couldn't open the browser",
                "The submission page couldn't be opened automatically. The profile JSON is on "
                "your clipboard — open a new issue on the project repository and paste it there.",
            )
            return
        tail = (
            "The profile JSON is already filled in on that page."
            if inlined
            else "The profile JSON was copied to your clipboard — paste it into the code block."
        )
        QMessageBox.information(
            self,
            "Submission opened",
            "A pre-filled GitHub issue opened in your browser. "
            + tail
            + "\n\nReview it before submitting. Reference images are not included in a submission.",
        )

    def _on_check_conflicts_clicked(self) -> None:
        errors = self._validate()
        if errors:
            _LOGGER.warning("Controller Setup conflict check for %r found %d issue(s): %s", self._controller_name, len(errors), errors)
            QMessageBox.warning(self, "Conflicts found", "\n".join(errors))
        else:
            _LOGGER.info("Controller Setup conflict check for %r: no issues", self._controller_name)
            QMessageBox.information(self, "No conflicts", "No missing fields or conflicting triggers found — draft looks stable.")

    def _apply(self) -> None:
        register(
            build_definition(self._controller_name, self._rows, self._reference_image or None),
            replace=True,
        )
        self._applied_names.add(self._controller_name)
        self.controllerApplied.emit(self._controller_name)

    def _on_apply_clicked(self) -> None:
        errors = self._validate()
        if errors:
            QMessageBox.warning(self, "Cannot apply yet", "\n".join(errors))
            return
        if self._controller_name in catalog.CONTROLLER_NAMES and self._controller_name not in self._applied_names:
            # Blocks silently clobbering a pre-existing controller (DDJ-XP2, XDJ-XZ, or
            # anything applied by a *different* draft) — this is in-memory only, so the
            # hand-written module on disk is untouched, but a running session that
            # replaces e.g. DDJ-XP2's full ~45-entry definition with a 4-row draft would
            # silently break every other tab that resolves triggers through it until the
            # app is restarted. Only a name this same draft already applied can be re-applied.
            _LOGGER.error(
                "Refused to apply Controller Setup draft %r: name collides with an already-loaded controller",
                self._controller_name,
            )
            QMessageBox.critical(
                self,
                "Cannot apply",
                f"'{self._controller_name}' is already a loaded controller (built-in or applied by "
                "another draft). Applying would replace its full definition in memory for the rest of "
                "this session — every tab using it would show only this draft's rows until you restart "
                "the app. Pick a different controller name for this new draft.",
            )
            return
        try:
            self._apply()
        except Exception as exc:
            _LOGGER.exception("Failed to apply Controller Setup draft %r", self._controller_name)
            QMessageBox.critical(self, "Failed to apply", f"{type(exc).__name__}: {exc}")
            return
        QMessageBox.information(
            self,
            "Applied",
            f"'{self._controller_name}' is now active in this session's Layout, By Controller, and "
            "Controller Images tabs. This lasts only for the current run — use \"Generate catalog "
            "module…\" and add its import to catalog/__init__.py to make it permanent.",
        )

    def _on_export_clicked(self) -> None:
        errors = self._validate()
        if errors:
            QMessageBox.warning(self, "Cannot export yet", "\n".join(errors))
            return
        if self._controller_name in catalog.CONTROLLER_NAMES and not self._confirm(
            f"'{self._controller_name}' is already a registered controller name. Export anyway?"
        ):
            return
        default_path = str(Path("src") / "djmidi" / "catalog" / f"{self._slug()}.py")
        path_str, _ = QFileDialog.getSaveFileName(self, "Generate catalog module", default_path, "Python files (*.py)")
        if not path_str:
            return
        if Path(path_str).exists() and not self._confirm(f"{path_str} already exists. Overwrite?"):
            return
        try:
            self._export_module(path_str)
        except OSError as exc:
            _LOGGER.exception("Failed to write generated catalog module to %s", path_str)
            QMessageBox.critical(self, "Failed to write file", str(exc))
            return
        _LOGGER.info("Generated catalog module for %r at %s", self._controller_name, path_str)
        slug = Path(path_str).stem
        message = (
            f"Wrote {path_str}.\n\nOne manual step remains: add '{slug}' to the import block in "
            "catalog/__init__.py (kept alphabetical, matching the existing style) so it's picked up."
        )
        if self._reference_image:
            image_name = Path(self._reference_image).name
            message += (
                f"\n\nThe module references reference_image='{image_name}'. Copy your image to "
                f"assets/controllers/{image_name} for it to show in the Controller Images tab on a "
                "future launch (user-supplied images are your responsibility re: licensing)."
            )
        QMessageBox.information(self, "Catalog module generated", message)

    # -- lifecycle -------------------------------------------------------------

    def shutdown(self) -> None:
        """Releases MIDI ports and cancels replay when the app is closing."""
        self._stop_replay()
        if self._learning:
            self._stop_learning()


__all__ = ["ControllerSetupView"]
