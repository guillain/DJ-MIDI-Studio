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
import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
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

from seratomidiconf import catalog
from seratomidiconf.catalog._registry import ControlInfo, _event_kind, register
from seratomidiconf.catalog.codegen import (
    build_definition,
    find_trigger_conflicts,
    generate_module_source,
    merge_by_channel,
)
from seratomidiconf.gui.port_list_utils import refresh_checked_port_list
from seratomidiconf.midi_io import MidiMonitor, list_input_ports
from seratomidiconf.model import MidiConfig
from seratomidiconf.parser import parse_file

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
    "Registers this draft in the running app so it shows up now in the Layout, By Controller, and "
    "Controller Images tabs. In-memory only — it's lost on restart. \"Generate catalog module…\" "
    "below is what makes it permanent."
)


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
        self._sources: list[str] = []
        self._devices: list[str] = []
        self._controller_name = ""
        self._dirty = False
        self._rebuilding = False
        self._learning = False
        self._applied_names: set[str] = set()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Controller name, e.g. Behringer CMD LC-1")
        self._name_edit.textChanged.connect(self._on_name_changed)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Controller name:"))
        name_row.addWidget(self._name_edit, 1)

        session_box = QGroupBox("Session")
        session_layout = QVBoxLayout(session_box)
        new_button = QPushButton("New session")
        new_button.clicked.connect(self._on_new_session_clicked)
        load_button = QPushButton("Load session…")
        load_button.clicked.connect(self._on_load_session_clicked)
        save_button = QPushButton("Save session…")
        save_button.clicked.connect(self._on_save_session_clicked)
        clear_button = QPushButton("Clear captured rows")
        clear_button.clicked.connect(self._on_clear_rows_clicked)
        for button in (new_button, load_button, save_button, clear_button):
            session_layout.addWidget(button)
        session_layout.addStretch(1)

        self._port_list = QListWidget()
        self._port_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        refresh_button = QPushButton("Refresh ports")
        refresh_button.clicked.connect(self._refresh_ports)
        self._learn_button = QPushButton("Start learning")
        self._learn_button.clicked.connect(self._toggle_learning)
        self._learn_status = QLabel("Stopped")
        capture_help = QLabel(_CAPTURE_HELP)
        capture_help.setWordWrap(True)
        capture_box = QGroupBox("Capture (learn from controller)")
        capture_layout = QVBoxLayout(capture_box)
        capture_layout.addWidget(self._port_list)
        capture_layout.addWidget(refresh_button)
        capture_layout.addWidget(self._learn_button)
        capture_layout.addWidget(self._learn_status)
        capture_layout.addWidget(capture_help)

        import_button = QPushButton("Import from Serato XML…")
        import_button.clicked.connect(self._on_import_xml_clicked)
        import_help = QLabel(_IMPORT_HELP)
        import_help.setWordWrap(True)
        import_box = QGroupBox("Import")
        import_layout = QVBoxLayout(import_box)
        import_layout.addWidget(import_button)
        import_layout.addWidget(import_help)
        import_layout.addStretch(1)

        check_button = QPushButton("Check for conflicts")
        check_button.clicked.connect(self._on_check_conflicts_clicked)
        self._apply_button = QPushButton("Apply now (this session)")
        self._apply_button.clicked.connect(self._on_apply_clicked)
        apply_help = QLabel(_APPLY_HELP)
        apply_help.setWordWrap(True)
        export_button = QPushButton("Generate catalog module…")
        export_button.clicked.connect(self._on_export_clicked)
        export_box = QGroupBox("Apply / Export")
        export_layout = QVBoxLayout(export_box)
        export_layout.addWidget(check_button)
        export_layout.addWidget(self._apply_button)
        export_layout.addWidget(apply_help)
        export_layout.addWidget(export_button)
        export_layout.addStretch(1)

        top_row = QHBoxLayout()
        top_row.addWidget(session_box, 1)
        top_row.addWidget(capture_box, 1)
        top_row.addWidget(import_box, 1)
        top_row.addWidget(export_box, 1)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(["Section", "Name", "Type", "Channel(s)", "Data1", "Source", "Device"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.cellChanged.connect(self._on_cell_changed)

        delete_button = QPushButton("Delete selected row(s)")
        delete_button.clicked.connect(self._on_delete_selected_clicked)
        add_button = QPushButton("Add row")
        add_button.clicked.connect(self._on_add_row_clicked)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(delete_button)
        row_buttons.addWidget(add_button)
        row_buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(name_row)
        layout.addLayout(top_row)
        layout.addWidget(self._table)
        layout.addLayout(row_buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        self._refresh_ports()

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
        entry = ControlInfo(self._controller_name, "", "", kind, (channel,), data1)
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
        self._rows[row] = ControlInfo(self._controller_name, section, name, note_or_cc, channels, data1)
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

    # -- session lifecycle --------------------------------------------------

    def _confirm(self, text: str) -> bool:
        reply = QMessageBox.question(self, "Confirm", text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return reply == QMessageBox.StandardButton.Yes

    def _reset(self, *, clear_name: bool) -> None:
        self._rows = []
        self._sources = []
        self._devices = []
        if clear_name:
            self._controller_name = ""
            self._name_edit.setText("")
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

    def _is_checked(self, row: int) -> bool:
        return self._port_list.item(row).checkState() == Qt.CheckState.Checked

    def _toggle_learning(self) -> None:
        if self._learning:
            self._stop_learning()
        else:
            self._start_learning()

    def _start_learning(self) -> None:
        selected = [self._port_list.item(i).text() for i in range(self._port_list.count()) if self._is_checked(i)]
        for name in selected:
            self._monitor.open_input(name)
        self._learning = True
        self._learn_button.setText("Stop learning")
        self._learn_status.setText(f"Listening ({len(selected)} input(s))")
        self._timer.start()

    def _stop_learning(self) -> None:
        self._timer.stop()
        self._monitor.close_all()
        self._learning = False
        self._learn_button.setText("Start learning")
        self._learn_status.setText("Stopped")

    def _poll(self) -> None:
        for event in self._monitor.poll():
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
        except Exception as exc:  # noqa: BLE001 - surface any parse error to the user
            QMessageBox.critical(self, "Failed to import file", str(exc))
            return
        added = self._import_config(config, Path(path_str).name)
        QMessageBox.information(self, "Import complete", f"Added {added} new trigger(s) (others already present were skipped).")

    # -- session save / load --------------------------------------------------

    def _rows_to_session_dict(self) -> dict:
        return {
            "version": 1,
            "controller_name": self._controller_name,
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
        rows = []
        sources = []
        devices = []
        for raw in data["rows"]:
            rows.append(
                ControlInfo(name, raw["section"], raw["name"], raw["note_or_cc"], tuple(raw["channels"]), raw["data1"])
            )
            sources.append(raw.get("source", "manual"))
            devices.append(raw.get("device", ""))
        self._controller_name = name
        self._name_edit.setText(name)
        self._rows = rows
        self._sources = sources
        self._devices = devices
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
            QMessageBox.critical(self, "Failed to save session", str(exc))

    def _on_load_session_clicked(self) -> None:
        if self._dirty and not self._confirm("This will discard the current unsaved draft. Continue?"):
            return
        path_str, _ = QFileDialog.getOpenFileName(self, "Load controller setup session", "", "JSON files (*.json)")
        if not path_str:
            return
        try:
            self._load_session(path_str)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Failed to load session", str(exc))

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

    def _export_module(self, path: str | Path) -> None:
        merged = merge_by_channel(self._rows)
        source = generate_module_source(self._controller_name, merged)
        Path(path).write_text(source)

    def _on_check_conflicts_clicked(self) -> None:
        errors = self._validate()
        if errors:
            QMessageBox.warning(self, "Conflicts found", "\n".join(errors))
        else:
            QMessageBox.information(self, "No conflicts", "No missing fields or conflicting triggers found — draft looks stable.")

    def _apply(self) -> None:
        register(build_definition(self._controller_name, self._rows), replace=True)
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
        except Exception as exc:  # noqa: BLE001 - surface any bug instead of failing silently
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
        default_path = str(Path("src") / "seratomidiconf" / "catalog" / f"{self._slug()}.py")
        path_str, _ = QFileDialog.getSaveFileName(self, "Generate catalog module", default_path, "Python files (*.py)")
        if not path_str:
            return
        if Path(path_str).exists() and not self._confirm(f"{path_str} already exists. Overwrite?"):
            return
        try:
            self._export_module(path_str)
        except OSError as exc:
            QMessageBox.critical(self, "Failed to write file", str(exc))
            return
        slug = Path(path_str).stem
        QMessageBox.information(
            self,
            "Catalog module generated",
            f"Wrote {path_str}.\n\nOne manual step remains: add '{slug}' to the import block in "
            "catalog/__init__.py (kept alphabetical, matching the existing style) so it's picked up.",
        )

    # -- lifecycle -------------------------------------------------------------

    def shutdown(self) -> None:
        """Releases MIDI ports; call when the app is closing."""
        if self._learning:
            self._stop_learning()


__all__ = ["ControllerSetupView"]
