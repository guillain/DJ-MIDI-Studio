"""Music Library tab (issue #132): the GUI home for the library initiative.

Binds the Qt-free `djmidi.library` layer (scan index, tag cache, taxonomy,
playlist engine, Serato/Traktor/Rekordbox formats) to one tab:

- music folder list + a "Scan & read tags" job, driven a slice at a time by
  a `QTimer` (this project's non-blocking pattern, see `midi_io` polling);
- the consolidated metadata table (sortable/filterable, category column);
- a Track panel whose tag edits go through a `QUndoStack`
  (`commands.WriteTrackMetadataCommand`, or `WriteTracksMetadataCommand` when
  "Write tags to selection…" copies chosen fields to every selected track),
  a Categories panel over the
  taxonomy registry, and a Playlists panel (import/generate/export).

Opening the library index is lazy (first time the tab is shown), so merely
constructing the main window never creates or reads `library.sqlite3`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator, Iterator
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableView,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi import taxonomy
from djmidi.gui import help_texts
from djmidi.gui.commands import WriteTrackMetadataCommand, WriteTracksMetadataCommand
from djmidi.gui.help_button import help_button, help_row
from djmidi.library import workspace
from djmidi.library.db import LibraryDB, default_library_db_path
from djmidi.library.metadata import TrackMetadata, clean_noise_frames
from djmidi.library.playlist import is_camelot_compatible
from djmidi.library.scanner import iter_scan_root

_LOGGER = logging.getLogger(__name__)

# Time slice a job may use per timer tick before yielding back to Qt.
# A bulk tag write shows its progress window only past this delay, so a
# handful of files doesn't flash a dialog.
_PROGRESS_DELAY_MS = 400
_SLICE_SECONDS = 0.025

# (header, key) -- key is a TrackMetadata field or a LibraryRow extra.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("Title", "title"),
    ("Artist", "artist"),
    ("Album", "album"),
    ("Genre", "genre"),
    ("Category", "category"),
    ("BPM", "bpm"),
    ("Key", "key"),
    ("Camelot", "camelot"),
    ("Rating", "rating"),
    ("Energy", "energy"),
    ("Comment", "comment"),
    ("Path", "path"),
)
_COLUMN_INDEX = {key: index for index, (_header, key) in enumerate(COLUMNS)}
_EDIT_FIELDS = ("title", "artist", "album", "genre", "bpm", "key", "comment", "rating", "energy")

# Below this the tab scrolls rather than squeezing its panels (issue #19).
_CONTENT_MIN_WIDTH = 760
_CONTENT_MIN_HEIGHT = 440

ALL_CATEGORIES = "All categories"
UNCATEGORIZED = "Uncategorized"
ALL_GENRES = "All genres"
ALL_KEYS = "All keys"
ALL_CAMELOT = "All Camelot"
# Wheel order: 1A, 1B, 2A, … 12B.
CAMELOT_CODES = tuple(f"{number}{letter}" for number in range(1, 13) for letter in "AB")
_BPM_FILTER_MAX = 300

ROW_ROLE = Qt.ItemDataRole.UserRole + 1
SORT_ROLE = Qt.ItemDataRole.UserRole + 2


def category_label(canonical: str | None) -> str:
    return canonical.replace("%%", " / ") if canonical else ""


def _format_bpm(bpm: float | None) -> str:
    if bpm is None:
        return ""
    return f"{bpm:g}" if bpm == int(bpm) else f"{bpm:.2f}"


def _scrolled(panel: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(panel)
    return area


def _field_text(name: str, value: object) -> str:
    if name == "bpm":
        return _format_bpm(value)
    return "" if value is None else str(value)


def _field_label(name: str) -> str:
    return "BPM" if name == "bpm" else name.capitalize()


def _parse_field(name: str, text: str) -> object:
    """Edit-box text -> tag value; empty clears the tag. Raises ValueError
    for a non-numeric BPM."""
    text = text.strip()
    if name == "bpm":
        return float(text.replace(",", ".")) if text else None
    return text or None


def _same_value(name: str, a: object, b: object) -> bool:
    return _same_bpm(a, b) if name == "bpm" else a == b


class BulkTagDialog(QDialog):
    """Pick which tag(s) to copy onto every selected track. Each field starts
    from the Track panel's current text; only checked fields are written,
    and a checked empty field clears that tag."""

    def __init__(
        self,
        values: dict[str, str],
        track_count: int,
        checked: set[str] | frozenset[str] = frozenset(),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Write tags to selection")
        self.setMinimumWidth(420)
        box = QVBoxLayout(self)
        intro = QLabel(
            f"Check the tag(s) to write to the {track_count} selected track(s). Unchecked tags are left "
            "as they are in every file; a checked empty field clears that tag. Serato/Traktor data is preserved."
        )
        intro.setWordWrap(True)
        box.addWidget(intro)
        grid = QGridLayout()
        self.checks: dict[str, QCheckBox] = {}
        self.edits: dict[str, QLineEdit] = {}
        for row, name in enumerate(_EDIT_FIELDS):
            check = QCheckBox(_field_label(name))
            check.setChecked(name in checked)
            edit = QLineEdit(values.get(name, ""))
            edit.setPlaceholderText("(empty: clears the tag)")
            edit.setEnabled(check.isChecked())
            check.toggled.connect(edit.setEnabled)
            check.toggled.connect(self._update_ok)
            grid.addWidget(check, row, 0)
            grid.addWidget(edit, row, 1)
            self.checks[name] = check
            self.edits[name] = edit
        box.addLayout(grid)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(f"Write to {track_count} track(s)")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)
        self._update_ok()

    def _update_ok(self, *_args: object) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.checked_fields()))

    def checked_fields(self) -> list[str]:
        return [name for name, check in self.checks.items() if check.isChecked()]

    def values(self) -> dict[str, object]:
        """Checked fields only, parsed. Raises ValueError for a bad BPM."""
        return {name: _parse_field(name, self.edits[name].text()) for name in self.checked_fields()}

    def _on_accept(self) -> None:
        try:
            self.values()
        except ValueError:
            QMessageBox.warning(self, "Invalid BPM", "BPM must be a number, e.g. 174 or 128.5.")
            return
        self.accept()


def _can_confirm_suggestion(row: workspace.LibraryRow) -> bool:
    return bool(row.category is None and row.category_suggestion and row.metadata and row.metadata.genre)


def _same_bpm(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= 1e-6


class LibraryTableModel(QAbstractTableModel):
    """Read-only table over `workspace.LibraryRow`s -- a custom model rather
    than a `QStandardItemModel` since a real collection runs to ~85k rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[workspace.LibraryRow] = []

    def set_rows(self, rows: list[workspace.LibraryRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rows(self) -> list[workspace.LibraryRow]:
        return list(self._rows)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        return None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        key = COLUMNS[index.column()][1]
        if role == ROW_ROLE:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(row, key)
        if role == SORT_ROLE:
            return (row.bpm if row.bpm is not None else -1.0) if key == "bpm" else self._display(row, key).casefold()
        return self._decoration(row, key, role)

    @staticmethod
    def _decoration(row: workspace.LibraryRow, key: str, role: int):
        suggested = key == "category" and row.category is None and bool(row.category_suggestion)
        if role == Qt.ItemDataRole.ForegroundRole:
            if row.missing:
                return QBrush(QColor("#888888"))
            return QBrush(QColor("#b07a00")) if suggested else None
        if role == Qt.ItemDataRole.FontRole and suggested:
            font = QFont()
            font.setItalic(True)
            return font
        if role == Qt.ItemDataRole.ToolTipRole:
            return LibraryTableModel._tooltip(row, key, suggested)
        return None

    @staticmethod
    def _tooltip(row: workspace.LibraryRow, key: str, suggested: bool) -> str | None:
        if row.missing:
            return f"Missing on disk: {row.path}"
        if suggested:
            return "Fuzzy suggestion only -- confirm it from the Track panel to make it stick."
        return row.path if key == "path" else None

    @staticmethod
    def _display(row: workspace.LibraryRow, key: str) -> str:
        if key == "path":
            return row.path
        if key == "category":
            if row.category:
                return category_label(row.category)
            if row.category_suggestion:
                return f"? {category_label(row.category_suggestion)}"
            return ""
        if key == "camelot":
            return row.camelot_key or ""
        if key == "bpm":
            return _format_bpm(row.bpm)
        value = getattr(row.metadata, key, None) if row.metadata else None
        return "" if value is None else str(value)


def _norm(text: str | None) -> str:
    return (text or "").strip().casefold()


class LibraryFilterProxy(QSortFilterProxyModel):
    """Free-text filter across every column, plus category, genre, BPM
    range, key and Camelot filters (all combined with AND)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._category: str = ALL_CATEGORIES
        self._genre: str | None = None
        self._bpm_min: float | None = None
        self._bpm_max: float | None = None
        self._key: str | None = None
        self._camelot: str | None = None
        self._camelot_compatible = False
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)
        self.setSortRole(SORT_ROLE)

    def _change_filter(self, apply: Callable[[], None]) -> None:
        # Qt 6.10 deprecated invalidateFilter() for this begin/end pair.
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            apply()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            apply()
            self.invalidateFilter()

    def set_category_filter(self, category: str) -> None:
        self._change_filter(lambda: setattr(self, "_category", category))

    def set_genre_filter(self, genre: str | None) -> None:
        """Exact genre tag (case-insensitive); None for every genre."""
        self._change_filter(lambda: setattr(self, "_genre", _norm(genre) or None))

    def set_bpm_range(self, minimum: float | None, maximum: float | None) -> None:
        """Inclusive BPM bounds; None leaves that side open. With any bound
        set, tracks without a BPM are hidden."""

        def apply() -> None:
            self._bpm_min, self._bpm_max = minimum, maximum

        self._change_filter(apply)

    def set_key_filter(self, key: str | None) -> None:
        """Exact key tag as written in the file (case-insensitive)."""
        self._change_filter(lambda: setattr(self, "_key", _norm(key) or None))

    def set_camelot_filter(self, camelot: str | None, compatible: bool = False) -> None:
        """One Camelot code; with `compatible`, also every harmonically
        compatible key (same code, ±1 on the wheel, relative major/minor)."""

        def apply() -> None:
            self._camelot = camelot.upper() if camelot else None
            self._camelot_compatible = compatible

        self._change_filter(apply)

    def has_track_filters(self) -> bool:
        return any(
            value is not None for value in (self._genre, self._bpm_min, self._bpm_max, self._key, self._camelot)
        )

    def _accepts_track(self, row: workspace.LibraryRow) -> bool:
        metadata = row.metadata
        if self._genre is not None and _norm(metadata.genre if metadata else None) != self._genre:
            return False
        if self._bpm_min is not None or self._bpm_max is not None:
            bpm = row.bpm
            if bpm is None:
                return False
            if self._bpm_min is not None and bpm < self._bpm_min:
                return False
            if self._bpm_max is not None and bpm > self._bpm_max:
                return False
        if self._key is not None and _norm(metadata.key if metadata else None) != self._key:
            return False
        if self._camelot is not None:
            if row.camelot_key is None:
                return False
            if self._camelot_compatible:
                return is_camelot_compatible(self._camelot, row.camelot_key)
            return row.camelot_key.upper() == self._camelot
        return True

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex) -> bool:
        model = self.sourceModel()
        row = model.data(model.index(source_row, 0, source_parent), ROW_ROLE)
        if self._category == UNCATEGORIZED and row.category is not None:
            return False
        if self._category not in (ALL_CATEGORIES, UNCATEGORIZED) and row.category != self._category:
            return False
        if not self._accepts_track(row):
            return False
        return super().filterAcceptsRow(source_row, source_parent)


class MusicLibraryView(QWidget):
    def __init__(self, db_path: str | Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._db: LibraryDB | None = None
        self.undo_stack = QUndoStack(self)
        self._job: Iterator[None] | None = None
        self._job_timer = QTimer(self)
        self._job_timer.setInterval(0)
        self._job_timer.timeout.connect(self._run_job_slice)
        self._current_path: str | None = None

        # The whole tab scrolls below its real minimum instead of crushing
        # buttons into slivers (issue #19's standing rule for every tab).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll)
        content = QWidget()
        content.setMinimumSize(_CONTENT_MIN_WIDTH, _CONTENT_MIN_HEIGHT)
        self._scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.addWidget(self._build_folders_group())

        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self._build_table_panel())
        self.side_tabs = QTabWidget()
        self.side_tabs.addTab(_scrolled(self._build_track_panel()), "Track")
        self.side_tabs.addTab(_scrolled(self._build_categories_panel()), "Categories")
        self.side_tabs.addTab(_scrolled(self._build_playlists_panel()), "Playlists")
        body.addWidget(self.side_tabs)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)
        body.setChildrenCollapsible(False)
        # Stretch factors alone left the side panel at half the width; the
        # table is what needs the room.
        body.setSizes([680, 320])
        layout.addWidget(body, 1)
        self._update_track_panel(None)

    # --- construction ---------------------------------------------------

    def _build_folders_group(self) -> QGroupBox:
        group = QGroupBox("Music folders")
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        box = QVBoxLayout(group)
        row = QHBoxLayout()
        self.roots_list = QListWidget()
        self.roots_list.setMaximumHeight(56)
        self.roots_list.setToolTip("Folders this app indexes. Scanning never modifies your files.")
        row.addWidget(self.roots_list, 1)
        self.add_root_button = QPushButton("Add folder…")
        self.add_root_button.clicked.connect(self._on_add_root_clicked)
        self.remove_root_button = QPushButton("Remove")
        self.remove_root_button.clicked.connect(self._on_remove_root_clicked)
        self.scan_button = QPushButton("Scan && read tags")
        self.scan_button.setToolTip(
            "Index new/changed files and read their tags. Incremental: unchanged files are skipped."
        )
        self.scan_button.clicked.connect(self.start_scan)
        for button in (self.add_root_button, self.remove_root_button, self.scan_button):
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(help_button(self, *help_texts.LIBRARY_FOLDERS), 0, Qt.AlignmentFlag.AlignTop)
        box.addLayout(row)
        status_row = QHBoxLayout()
        self.status_label = QLabel("Add a music folder, then scan it.")
        self.status_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.progress_bar, 1)
        box.addLayout(status_row)
        return group

    def _build_table_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by artist, title, genre, BPM, key, comment…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumWidth(160)
        self.category_filter = QComboBox()
        self.category_filter.setMinimumContentsLength(16)
        self.count_label = QLabel()
        filters.addWidget(self.filter_edit, 1)
        filters.addWidget(self.category_filter)
        filters.addWidget(self.count_label)
        box.addLayout(filters)
        box.addLayout(self._build_track_filters())

        self.table_model = LibraryTableModel(self)
        self.proxy = LibraryFilterProxy(self)
        self.proxy.setSourceModel(self.table_model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(_COLUMN_INDEX["artist"], Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setWordWrap(False)
        box.addWidget(self.table, 1)

        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self.category_filter.currentTextChanged.connect(self._on_category_filter_changed)
        self.table.selectionModel().currentRowChanged.connect(self._on_current_row_changed)
        self.proxy.rowsInserted.connect(self._update_count_label)
        self.proxy.modelReset.connect(self._update_count_label)
        self.proxy.layoutChanged.connect(self._update_count_label)
        return panel

    def _build_track_filters(self) -> QVBoxLayout:
        """Genre / key / Camelot, then BPM range, under the search box (two
        rows so the table panel stays usable at narrow widths, issue #19)."""
        rows = QVBoxLayout()
        first, second = QHBoxLayout(), QHBoxLayout()
        self.genre_filter = QComboBox()
        self.genre_filter.setToolTip("Only tracks with this genre tag")
        self.bpm_min_filter = QSpinBox()
        self.bpm_max_filter = QSpinBox()
        for spin, label in ((self.bpm_min_filter, "min"), (self.bpm_max_filter, "max")):
            spin.setRange(0, _BPM_FILTER_MAX)
            spin.setSpecialValueText(label)
            spin.setToolTip(f"{label.capitalize()}imum BPM (inclusive); leave at “{label}” for no limit")
            spin.setAccelerated(True)
        self.key_filter = QComboBox()
        self.key_filter.setToolTip("Only tracks with this key tag, as written in the file")
        self.camelot_filter = QComboBox()
        self.camelot_filter.addItem(ALL_CAMELOT, None)
        for code in CAMELOT_CODES:
            self.camelot_filter.addItem(code, code)
        self.camelot_filter.setToolTip("Only tracks in this Camelot key")
        self.camelot_compatible_check = QCheckBox("+ compatible")
        self.camelot_compatible_check.setToolTip(
            "Also show harmonically compatible keys: ±1 on the wheel and the relative major/minor"
        )
        # A long genre or key must not widen the table panel: size each combo
        # from a few characters, the popup still shows full names.
        for combo, length in ((self.genre_filter, 8), (self.key_filter, 5), (self.camelot_filter, 5)):
            combo.setMinimumContentsLength(length)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.reset_filters_button = QPushButton("Reset filters")
        self.reset_filters_button.clicked.connect(self.reset_filters)
        first.addWidget(self.genre_filter, 2)
        first.addWidget(self.key_filter, 1)
        first.addWidget(self.camelot_filter, 1)
        second.addWidget(QLabel("BPM"))
        second.addWidget(self.bpm_min_filter)
        second.addWidget(QLabel("–"))
        second.addWidget(self.bpm_max_filter)
        second.addWidget(self.camelot_compatible_check)
        second.addStretch(1)
        second.addWidget(self.reset_filters_button)
        second.addWidget(help_button(self, *help_texts.LIBRARY_TABLE))
        rows.addLayout(first)
        rows.addLayout(second)
        self._refill_combo(self.genre_filter, ALL_GENRES, [])
        self._refill_combo(self.key_filter, ALL_KEYS, [])

        self.genre_filter.currentIndexChanged.connect(self._on_genre_filter_changed)
        self.key_filter.currentIndexChanged.connect(self._on_key_filter_changed)
        self.bpm_min_filter.valueChanged.connect(self._on_bpm_filter_changed)
        self.bpm_max_filter.valueChanged.connect(self._on_bpm_filter_changed)
        self.camelot_filter.currentIndexChanged.connect(self._on_camelot_filter_changed)
        self.camelot_compatible_check.toggled.connect(self._on_camelot_filter_changed)
        return rows

    def _build_track_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.addLayout(help_row(self, *help_texts.LIBRARY_TRACK))
        self.track_path_label = QLabel()
        self.track_path_label.setWordWrap(True)
        self.track_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.track_path_label)
        form = QFormLayout()
        self.field_edits: dict[str, QLineEdit] = {}
        for name in _EDIT_FIELDS:
            edit = QLineEdit()
            edit.returnPressed.connect(self.apply_track_edits)
            self.field_edits[name] = edit
            form.addRow(_field_label(name), edit)
        self.camelot_label = QLabel()
        form.addRow("Camelot", self.camelot_label)
        self.category_value_label = QLabel()
        self.category_value_label.setWordWrap(True)
        form.addRow("Category", self.category_value_label)
        box.addLayout(form)

        self.accept_suggestion_button = QPushButton("Confirm suggested category")
        self.accept_suggestion_button.setToolTip(
            "Records this track's genre tag as an alias of the suggested category, so every "
            "track with that genre resolves to it from now on. Never applied automatically."
        )
        self.accept_suggestion_button.clicked.connect(self.confirm_category_suggestion)
        box.addWidget(self.accept_suggestion_button)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton("Write tags")
        self.apply_button.setToolTip("Writes only the changed fields into the file. Serato/Traktor data is preserved.")
        self.apply_button.clicked.connect(self.apply_track_edits)
        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(lambda: self._update_track_panel(self._current_row()))
        undo_button = QPushButton("Undo")
        redo_button = QPushButton("Redo")
        undo_button.clicked.connect(self.undo_stack.undo)
        redo_button.clicked.connect(self.undo_stack.redo)
        self.undo_stack.canUndoChanged.connect(undo_button.setEnabled)
        self.undo_stack.canRedoChanged.connect(redo_button.setEnabled)
        undo_button.setEnabled(False)
        redo_button.setEnabled(False)
        self.undo_button, self.redo_button = undo_button, redo_button
        for button in (self.apply_button, self.revert_button, undo_button, redo_button):
            buttons.addWidget(button)
        box.addLayout(buttons)

        self.write_selection_button = QPushButton("Write tags to selection…")
        self.write_selection_button.setToolTip(
            "Choose which tag(s) to copy from the fields above onto every selected track, "
            "as one undoable step. Serato/Traktor data is preserved."
        )
        self.write_selection_button.clicked.connect(self._on_write_selection_clicked)
        box.addWidget(self.write_selection_button)
        self.table.selectionModel().selectionChanged.connect(self._update_selection_actions)

        self.clean_button = QPushButton("Clean noise frames…")
        self.clean_button.setToolTip(
            "Lists leftover junk tags (ID3v1 comment mirrors, old player preferences, ReplayGain…) "
            "and removes them only after you confirm."
        )
        self.clean_button.clicked.connect(self._on_clean_clicked)
        box.addWidget(self.clean_button)
        box.addStretch(1)
        return panel

    def _build_categories_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.addLayout(help_row(self, *help_texts.LIBRARY_CATEGORIES))
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderLabels(["Category", "Tracks", "Aliases"])
        self.category_tree.setColumnWidth(0, 160)
        box.addWidget(self.category_tree, 1)
        grid = QGridLayout()
        self.new_category_button = QPushButton("New…")
        self.alias_button = QPushButton("Add alias…")
        self.rename_category_button = QPushButton("Rename…")
        self.merge_button = QPushButton("Merge into…")
        self.delete_category_button = QPushButton("Delete")
        self.new_category_button.clicked.connect(self._on_new_category_clicked)
        self.alias_button.clicked.connect(self._on_add_alias_clicked)
        self.rename_category_button.clicked.connect(self._on_rename_category_clicked)
        self.merge_button.clicked.connect(self._on_merge_clicked)
        self.delete_category_button.clicked.connect(self._on_delete_category_clicked)
        for index, button in enumerate(
            (
                self.new_category_button,
                self.alias_button,
                self.rename_category_button,
                self.merge_button,
                self.delete_category_button,
            )
        ):
            grid.addWidget(button, index // 3, index % 3)
        box.addLayout(grid)
        return panel

    def _build_playlists_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.addLayout(help_row(self, *help_texts.LIBRARY_PLAYLISTS))
        self.playlist_list = QListWidget()
        self.playlist_list.currentItemChanged.connect(self._on_playlist_selected)
        box.addWidget(self.playlist_list, 1)
        self.playlist_tracks = QListWidget()
        box.addWidget(QLabel("Tracks in playlist"))
        box.addWidget(self.playlist_tracks, 1)
        grid = QGridLayout()
        specs: list[tuple[str, str, Callable[[], None], str]] = [
            ("new_playlist_button", "New from selection", self._on_new_playlist_clicked,
             "Creates a playlist from the rows selected in the table."),
            ("generate_button", "Auto: sort visible", self._on_generate_clicked,
             "Every visible row, grouped by category, then BPM range, then key."),
            ("match_button", "Auto: match current", self._on_match_clicked,
             "The current track followed by every visible track compatible in BPM and key."),
            ("import_serato_button", "Import Serato crate…", self._on_import_serato_clicked, ""),
            ("import_traktor_button", "Import Traktor NML…", self._on_import_traktor_clicked, ""),
            ("import_rekordbox_button", "Import Rekordbox export…", self._on_import_rekordbox_clicked, ""),
            ("export_serato_button", "Export as Serato crate…", self._on_export_serato_clicked,
             "Writes a new .crate file where you choose. Never overwrites a crate on its own."),
            ("export_traktor_button", "Export as Traktor playlist…", self._on_export_traktor_clicked,
             ("Writes a new single-playlist .nml where you choose, for Traktor's Import Playlist. "
              "Never touches collection.nml.")),
            ("rename_playlist_button", "Rename…", self._on_rename_playlist_clicked, ""),
            ("delete_playlist_button", "Delete", self._on_delete_playlist_clicked, ""),
        ]
        for index, (attr, label, handler, tip) in enumerate(specs):
            button = QPushButton(label)
            if tip:
                button.setToolTip(tip)
            button.clicked.connect(handler)
            setattr(self, attr, button)
            grid.addWidget(button, index // 3, index % 3)
        box.addLayout(grid)
        return panel

    # --- database lifecycle --------------------------------------------

    @property
    def db(self) -> LibraryDB:
        return self.ensure_open()

    def ensure_open(self) -> LibraryDB:
        if self._db is None:
            path = self._db_path if self._db_path is not None else default_library_db_path()
            self._db = LibraryDB(path)
            workspace.load_taxonomy_overrides(self._db)
            self.reload()
        return self._db

    def close_db(self) -> None:
        self._stop_job()
        if self._db is not None:
            self._db.close()
            self._db = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        try:
            self.ensure_open()
        except Exception:
            _LOGGER.exception("Could not open the music library index")
            self.status_label.setText("Could not open the music library index (see the log).")

    def reload(self) -> None:
        """Re-read roots, table rows, categories and playlists from the DB."""
        db = self.ensure_open()
        self.roots_list.clear()
        for root in db.list_roots():
            item = QListWidgetItem(root.path)
            item.setData(Qt.ItemDataRole.UserRole, root.id)
            self.roots_list.addItem(item)
        self._reload_rows()
        self._reload_playlists()

    def _reload_rows(self) -> None:
        current = self._current_path
        self.table_model.set_rows(workspace.consolidate(self.db))
        self._refresh_category_filter()
        self._refresh_value_filters(self.table_model.rows())
        if current is not None:
            self.select_path(current)
        self._update_count_label()
        # Per-category track counts follow the rows.
        self._reload_categories()

    # --- folders & scanning ---------------------------------------------

    def add_root(self, path: str | Path) -> None:
        self.db.add_root(Path(path))
        self.reload()

    def _on_add_root_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Add music folder")
        if directory:
            self.add_root(directory)

    def _on_remove_root_clicked(self) -> None:
        item = self.roots_list.currentItem()
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            "Remove music folder",
            f"Stop indexing {item.text()}?\n\nOnly this app's index is cleared -- no file is touched.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.remove_root(int(item.data(Qt.ItemDataRole.UserRole)))
            self.reload()

    def is_busy(self) -> bool:
        return self._job is not None

    def start_scan(self) -> None:
        if self.is_busy():
            return
        roots = self.db.list_roots()
        if not roots:
            self.status_label.setText("Add a music folder first.")
            return
        self._start_job(self._scan_job([root.path for root in roots]))

    def _scan_job(self, root_paths: list[str]) -> Generator[None]:
        totals = {"added": 0, "updated": 0, "unchanged": 0, "missing": 0}
        self.progress_bar.setRange(0, 0)
        for root_path in root_paths:
            if not Path(root_path).is_dir():
                self.status_label.setText(f"Skipping unavailable folder: {root_path}")
                yield
                continue
            steps = iter_scan_root(root_path, self.db)
            while True:
                try:
                    count = next(steps)
                except StopIteration as done:
                    for name in totals:
                        totals[name] += getattr(done.value, name)
                    break
                if count % 50 == 0:
                    self.status_label.setText(f"Scanning {root_path}… {count} files")
                yield
        pending = len(self.db.tracks_needing_metadata())
        self.progress_bar.setRange(0, max(pending, 1))
        for count in workspace.iter_refresh_metadata(self.db):
            self.progress_bar.setValue(count)
            if count % 50 == 0:
                self.status_label.setText(f"Reading tags… {count}/{pending}")
            yield
        self.status_label.setText(
            "Scan done: {added} new, {updated} changed, {unchanged} unchanged, {missing} missing.".format(**totals)
            + f" Tags read for {pending} file(s)."
        )
        self._reload_rows()

    def _start_job(self, job: Generator[None]) -> None:
        self._job = job
        self.scan_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._job_timer.start()

    def _stop_job(self) -> None:
        self._job_timer.stop()
        self._job = None
        self.scan_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    def _run_job_slice(self) -> None:
        if self._job is None:
            self._job_timer.stop()
            return
        deadline = time.monotonic() + _SLICE_SECONDS
        try:
            while time.monotonic() < deadline:
                next(self._job)
        except StopIteration:
            self._stop_job()
        except Exception:
            _LOGGER.exception("Music library job failed")
            self.status_label.setText("Scan failed (see the log).")
            self._stop_job()

    def run_pending_job(self) -> None:
        """Drain the current job synchronously (tests, scripted use)."""
        while self._job is not None:
            self._run_job_slice()

    # --- table ------------------------------------------------------------

    def _on_filter_changed(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        self._update_count_label()

    def _on_category_filter_changed(self, text: str) -> None:
        if text:
            self.proxy.set_category_filter(self.category_filter.currentData() or text)
            self._update_count_label()

    def _refresh_category_filter(self) -> None:
        previous = self.category_filter.currentData() or ALL_CATEGORIES
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(ALL_CATEGORIES, ALL_CATEGORIES)
        self.category_filter.addItem(UNCATEGORIZED, UNCATEGORIZED)
        for category in taxonomy.all_categories():
            self.category_filter.addItem(category_label(category.canonical), category.canonical)
        index = self.category_filter.findData(previous)
        self.category_filter.setCurrentIndex(max(index, 0))
        self.category_filter.blockSignals(False)
        self.proxy.set_category_filter(self.category_filter.currentData())

    @staticmethod
    def _refill_combo(combo: QComboBox, all_label: str, values: list[str]) -> None:
        """Replace a value filter's items, keeping the current choice when
        it still exists (else falling back to `all_label`)."""
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(all_label, None)
        for value in values:
            combo.addItem(value, value)
        index = combo.findData(previous) if previous is not None else 0
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)

    def _refresh_value_filters(self, rows: list[workspace.LibraryRow]) -> None:
        genres: dict[str, str] = {}
        keys: dict[str, str] = {}
        for row in rows:
            if row.metadata is None:
                continue
            for value, seen in ((row.metadata.genre, genres), (row.metadata.key, keys)):
                if value and value.strip():
                    seen.setdefault(_norm(value), value.strip())
        self._refill_combo(self.genre_filter, ALL_GENRES, sorted(genres.values(), key=str.casefold))
        self._refill_combo(self.key_filter, ALL_KEYS, sorted(keys.values(), key=str.casefold))
        self.proxy.set_genre_filter(self.genre_filter.currentData())
        self.proxy.set_key_filter(self.key_filter.currentData())

    def _on_genre_filter_changed(self, *_args: object) -> None:
        self.proxy.set_genre_filter(self.genre_filter.currentData())
        self._update_count_label()

    def _on_key_filter_changed(self, *_args: object) -> None:
        self.proxy.set_key_filter(self.key_filter.currentData())
        self._update_count_label()

    def _on_bpm_filter_changed(self, *_args: object) -> None:
        minimum = self.bpm_min_filter.value() or None
        maximum = self.bpm_max_filter.value() or None
        self.proxy.set_bpm_range(minimum, maximum)
        self._update_count_label()

    def _on_camelot_filter_changed(self, *_args: object) -> None:
        self.proxy.set_camelot_filter(self.camelot_filter.currentData(), self.camelot_compatible_check.isChecked())
        self._update_count_label()

    def reset_filters(self) -> None:
        """Clear the search box and every filter."""
        widgets = (
            self.filter_edit, self.category_filter, self.genre_filter, self.key_filter,
            self.bpm_min_filter, self.bpm_max_filter, self.camelot_filter, self.camelot_compatible_check,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self.filter_edit.clear()
        for combo in (self.category_filter, self.genre_filter, self.key_filter, self.camelot_filter):
            combo.setCurrentIndex(0)
        self.bpm_min_filter.setValue(0)
        self.bpm_max_filter.setValue(0)
        self.camelot_compatible_check.setChecked(False)
        for widget in widgets:
            widget.blockSignals(False)
        self.proxy.setFilterFixedString("")
        self.proxy.set_category_filter(ALL_CATEGORIES)
        self.proxy.set_genre_filter(None)
        self.proxy.set_key_filter(None)
        self.proxy.set_bpm_range(None, None)
        self.proxy.set_camelot_filter(None)
        self._update_count_label()

    def _update_count_label(self, *_args: object) -> None:
        self.count_label.setText(f"{self.proxy.rowCount()} / {self.table_model.rowCount()} tracks")

    def visible_rows(self) -> list[workspace.LibraryRow]:
        return [self.proxy.index(r, 0).data(ROW_ROLE) for r in range(self.proxy.rowCount())]

    def selected_rows(self) -> list[workspace.LibraryRow]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self.proxy.index(r, 0).data(ROW_ROLE) for r in rows]

    def select_path(self, path: str) -> bool:
        for proxy_row in range(self.proxy.rowCount()):
            index = self.proxy.index(proxy_row, 0)
            if index.data(ROW_ROLE).path == path:
                self.table.selectionModel().setCurrentIndex(
                    index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
                )
                return True
        return False

    def _current_row(self) -> workspace.LibraryRow | None:
        index = self.table.selectionModel().currentIndex()
        return index.data(ROW_ROLE) if index.isValid() else None

    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        self._update_track_panel(current.data(ROW_ROLE) if current.isValid() else None)

    # --- track panel ------------------------------------------------------

    def _update_track_panel(self, row: workspace.LibraryRow | None) -> None:
        self._current_path = row.path if row is not None else None
        self._update_selection_actions()
        metadata = (row.metadata if row is not None else None) or TrackMetadata()
        for name, edit in self.field_edits.items():
            edit.setText(_field_text(name, getattr(metadata, name)))
        editable = row is not None and not row.missing
        for widget in (*self.field_edits.values(), self.apply_button, self.revert_button, self.clean_button):
            widget.setEnabled(editable)
        if row is None:
            self.track_path_label.setText("Select a track in the table.")
            self.camelot_label.setText("")
            self.category_value_label.setText("")
            self.accept_suggestion_button.setEnabled(False)
            return
        self.track_path_label.setText(row.path + ("  (missing on disk)" if row.missing else ""))
        self.camelot_label.setText(row.camelot_key or "—")
        self.category_value_label.setText(self._category_text(row))
        self.accept_suggestion_button.setEnabled(_can_confirm_suggestion(row))

    def _writable_selection(self) -> list[workspace.LibraryRow]:
        return [row for row in self.selected_rows() if not row.missing]

    def _update_selection_actions(self, *_args: object) -> None:
        self.write_selection_button.setEnabled(bool(self._writable_selection()))

    @staticmethod
    def _category_text(row: workspace.LibraryRow) -> str:
        if row.category:
            return category_label(row.category)
        if row.category_suggestion:
            return f"Suggested: {category_label(row.category_suggestion)}"
        return "—"

    def pending_track_edits(self) -> dict[str, object]:
        """Fields whose edit box differs from the cached tags."""
        row = self._current_row()
        if row is None:
            return {}
        metadata = row.metadata or TrackMetadata()
        changes: dict[str, object] = {}
        for name, edit in self.field_edits.items():
            new = _parse_field(name, edit.text())
            if not _same_value(name, new, getattr(metadata, name)):
                changes[name] = new
        return changes

    def apply_track_edits(self) -> bool:
        row = self._current_row()
        if row is None or row.missing:
            return False
        try:
            changes = self.pending_track_edits()
        except ValueError:
            QMessageBox.warning(self, "Invalid BPM", "BPM must be a number, e.g. 174 or 128.5.")
            return False
        if not changes:
            self.status_label.setText("No tag changes to write.")
            return False
        metadata = row.metadata or TrackMetadata()
        old_values = {name: getattr(metadata, name) for name in changes}
        try:
            self.undo_stack.push(WriteTrackMetadataCommand(row.path, old_values, changes, self._on_track_written))
        except Exception as exc:
            _LOGGER.exception("Tag write failed for %s", row.path)
            QMessageBox.warning(self, "Could not write tags", f"{row.path}\n\n{exc}")
            return False
        return True

    def _on_write_selection_clicked(self) -> None:
        rows = self._writable_selection()
        if not rows:
            return
        try:
            preselected = set(self.pending_track_edits())
        except ValueError:
            preselected = {"bpm"}
        values = {name: edit.text() for name, edit in self.field_edits.items()}
        dialog = BulkTagDialog(values, len(rows), preselected, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.write_tags_to_selection(dialog.values())

    def write_tags_to_selection(self, values: dict[str, object]) -> int:
        """Write `values` to every selected, present track as one undo step.
        Tracks already holding those values are skipped. Returns the number
        of files written."""
        if not values:
            return 0
        changes: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
        for row in self._writable_selection():
            metadata = row.metadata or TrackMetadata()
            new = {name: value for name, value in values.items() if not _same_value(name, value, getattr(metadata, name))}
            if new:
                changes[row.path] = ({name: getattr(metadata, name) for name in new}, new)
        if not changes:
            self.status_label.setText("Selected tracks already have these tags.")
            return 0
        command = WriteTracksMetadataCommand(
            changes, self._on_tracks_written, progress_factory=self._tag_write_progress
        )
        self.undo_stack.push(command)
        if command.cancelled:
            self.status_label.setText(
                f"Stopped: tags written to {len(command.written)} of {len(changes)} track(s)."
                " Undo restores the ones already written."
            )
        if command.failures:
            _LOGGER.warning("Tag write failed for %d file(s): %s", len(command.failures), command.failures)
            details = "\n".join(f"{Path(path).name}: {error}" for path, error in list(command.failures.items())[:20])
            QMessageBox.warning(
                self,
                "Some tags could not be written",
                f"{len(command.written)} track(s) written, {len(command.failures)} failed:\n\n{details}",
            )
        return len(command.written)

    def _tag_write_progress(self, label: str, total: int, cancellable: bool = True) -> Callable[[int, int], bool]:
        """A progress window for one pass of a bulk tag write (write, undo or
        redo): shown only if the pass lasts more than a moment, with a Cancel
        button. Returns the command's per-file callback; False means stop."""
        dialog = QProgressDialog(label, "Cancel" if cancellable else "", 0, max(total, 1), self)
        if not cancellable:
            dialog.setCancelButton(None)
        dialog.setWindowTitle("Music Library")
        dialog.setMinimumWidth(360)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(_PROGRESS_DELAY_MS)
        dialog.setAutoClose(True)
        dialog.setAutoReset(True)

        def report(done: int, total: int, text: str | None = None) -> bool:
            dialog.setLabelText(text or f"{label} {done}/{total}")
            dialog.setValue(done)
            return not dialog.wasCanceled()

        return report

    def _on_tracks_written(self, paths: list[str]) -> None:
        selected = [row.path for row in self.selected_rows()]
        # Re-reading every written file's tags takes as long as writing them.
        # Not cancellable: stopping here would leave the table showing stale
        # tags. One extra step keeps the window up while the table reloads
        # (seconds on a large library), so the app never looks frozen.
        total = len(paths) + 1
        progress = self._tag_write_progress("Reading tags back…", total, cancellable=False) if len(paths) > 1 else None
        for index, path in enumerate(paths):
            if progress is not None:
                progress(index, total)
            workspace.refresh_track_metadata(self.db, path)
        if progress is not None:
            progress(len(paths), total, "Refreshing the table…")
        self._reload_rows()
        self.select_paths(selected)
        if progress is not None:
            progress(total, total)
        self.status_label.setText(f"Tags written to {len(paths)} track(s).")

    def select_paths(self, paths: list[str]) -> None:
        """Re-select several tracks (after a reload), keeping the current one current."""
        wanted = set(paths)
        # One select() call for the whole set: selecting row by row emitted
        # selectionChanged (and refreshed the Track panel) once per track,
        # which froze the window for minutes after a bulk write on a long
        # selection. Contiguous rows are merged into one range each.
        selection = QItemSelection()
        start = None
        for proxy_row in range(self.proxy.rowCount() + 1):
            hit = proxy_row < self.proxy.rowCount() and self.proxy.index(proxy_row, 0).data(ROW_ROLE).path in wanted
            if hit and start is None:
                start = proxy_row
            elif not hit and start is not None:
                selection.select(self.proxy.index(start, 0), self.proxy.index(proxy_row - 1, 0))
                start = None
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        self.table.selectionModel().select(selection, flags)

    def _on_track_written(self, path: str) -> None:
        workspace.refresh_track_metadata(self.db, path)
        self._current_path = path
        # Reloading a large library takes a few seconds even for one track.
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            self._reload_rows()
        finally:
            QApplication.restoreOverrideCursor()
        self.status_label.setText(f"Tags written: {Path(path).name}")

    def confirm_category_suggestion(self) -> None:
        row = self._current_row()
        if row is None or row.category_suggestion is None or row.metadata is None or not row.metadata.genre:
            return
        workspace.add_category_alias(self.db, row.category_suggestion, row.metadata.genre)
        self.status_label.setText(
            f"“{row.metadata.genre}” is now an alias of {category_label(row.category_suggestion)}."
        )
        self._reload_rows()

    def _on_clean_clicked(self) -> None:
        row = self._current_row()
        if row is None or row.missing:
            return
        try:
            found = clean_noise_frames(row.path, dry_run=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Could not read tags", f"{row.path}\n\n{exc}")
            return
        if not found:
            QMessageBox.information(self, "Clean noise frames", "No noise frames found in this file.")
            return
        answer = QMessageBox.question(
            self,
            "Clean noise frames",
            "Remove these frames?\n\n" + "\n".join(found) + "\n\nSerato/Traktor data is never touched.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            clean_noise_frames(row.path, dry_run=False)
            self._on_track_written(row.path)

    # --- categories -------------------------------------------------------

    def _reload_categories(self) -> None:
        counts: dict[str, int] = {}
        for row in self.table_model.rows():
            if row.category:
                counts[row.category] = counts.get(row.category, 0) + 1
        self.category_tree.clear()
        family_items: dict[str, QTreeWidgetItem] = {}
        for category in taxonomy.all_categories():
            family_item = family_items.get(category.family)
            if family_item is None:
                family_item = QTreeWidgetItem([category.family])
                family_item.setFirstColumnSpanned(False)
                self.category_tree.addTopLevelItem(family_item)
                family_items[category.family] = family_item
            item = QTreeWidgetItem(
                [category.name, str(counts.get(category.canonical, 0)), ", ".join(sorted(category.aliases))]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, category.canonical)
            family_item.addChild(item)
        self.category_tree.expandAll()

    def selected_category(self) -> str | None:
        item = self.category_tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def _after_category_change(self, message: str) -> None:
        self.status_label.setText(message)
        self._reload_rows()

    def _category_action(self, action: Callable[[], str]) -> None:
        try:
            message = action()
        except ValueError as exc:
            QMessageBox.warning(self, "Categories", str(exc))
            return
        self._after_category_change(message)

    def _on_new_category_clicked(self) -> None:
        families = taxonomy.families()
        family, ok = QInputDialog.getItem(self, "New category", "Family:", families, 0, True)
        if not ok or not family.strip():
            return
        name, ok = QInputDialog.getText(self, "New category", f"Name (in {family}):")
        if ok and name.strip():
            self._category_action(
                lambda: f"Created {category_label(workspace.create_category(self.db, family, name).canonical)}."
            )

    def _on_add_alias_clicked(self) -> None:
        canonical = self.selected_category()
        if canonical is None:
            return
        alias, ok = QInputDialog.getText(self, "Add alias", f"Alias for {category_label(canonical)}:")
        if ok and alias.strip():
            self._category_action(
                lambda: (workspace.add_category_alias(self.db, canonical, alias), f"Alias “{alias}” added.")[1]
            )

    def _on_rename_category_clicked(self) -> None:
        canonical = self.selected_category()
        if canonical is None:
            return
        current = taxonomy.get_category(canonical).name
        name, ok = QInputDialog.getText(self, "Rename category", "New name:", text=current)
        if ok and name.strip():
            self._category_action(
                lambda: f"Renamed to {category_label(workspace.rename_category(self.db, canonical, name).canonical)}."
            )

    def _on_merge_clicked(self) -> None:
        absorb = self.selected_category()
        if absorb is None:
            return
        targets = [c.canonical for c in taxonomy.all_categories() if c.canonical != absorb]
        if not targets:
            return
        labels = [category_label(t) for t in targets]
        label, ok = QInputDialog.getItem(
            self, "Merge category", f"Merge {category_label(absorb)} into:", labels, 0, False
        )
        if ok:
            keep = targets[labels.index(label)]
            self._category_action(
                lambda: f"Merged into {category_label(workspace.merge_categories(self.db, keep, absorb).canonical)}."
            )

    def _on_delete_category_clicked(self) -> None:
        canonical = self.selected_category()
        if canonical is None:
            return
        answer = QMessageBox.question(
            self, "Delete category", f"Delete {category_label(canonical)}? Its tracks become uncategorized."
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._category_action(
                lambda: (workspace.delete_category(self.db, canonical), f"Deleted {category_label(canonical)}.")[1]
            )

    # --- playlists --------------------------------------------------------

    def _reload_playlists(self, select_id: int | None = None) -> None:
        if select_id is None:
            select_id = self.selected_playlist_id()
        self.playlist_list.clear()
        for record in self.db.list_playlists():
            item = QListWidgetItem(f"{record.name}  ({record.track_count}) · {record.source}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            self.playlist_list.addItem(item)
            if record.id == select_id:
                self.playlist_list.setCurrentItem(item)
        if self.playlist_list.currentItem() is None:
            self.playlist_tracks.clear()

    def selected_playlist_id(self) -> int | None:
        item = self.playlist_list.currentItem()
        return int(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _on_playlist_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self.playlist_tracks.clear()
        if current is None:
            return
        indexed = {row.path: row for row in self.table_model.rows()}
        for path in self.db.playlist_paths(int(current.data(Qt.ItemDataRole.UserRole))):
            self.playlist_tracks.addItem(_playlist_track_item(path, indexed.get(path)))

    def create_playlist(self, name: str, paths: list[str], source: str = workspace.SOURCE_MANUAL) -> int:
        playlist_id = self.db.create_playlist(name, paths, source)
        self._reload_playlists(select_id=playlist_id)
        self.side_tabs.setCurrentIndex(2)
        return playlist_id

    def _ask_playlist_name(self, default: str) -> str | None:
        name, ok = QInputDialog.getText(self, "Playlist name", "Name:", text=default)
        return name.strip() if ok and name.strip() else None

    def _on_new_playlist_clicked(self) -> None:
        rows = self.selected_rows()
        if not rows:
            self.status_label.setText("Select tracks in the table first.")
            return
        name = self._ask_playlist_name("New playlist")
        if name:
            self.create_playlist(name, [row.path for row in rows])

    def _on_generate_clicked(self) -> None:
        paths = workspace.generate_playlist(self.visible_rows())
        if not paths:
            self.status_label.setText("No visible tracks to build a playlist from.")
            return
        name = self._ask_playlist_name("Auto playlist")
        if name:
            self.create_playlist(name, paths, workspace.SOURCE_GENERATED)

    def _on_match_clicked(self) -> None:
        row = self._current_row()
        if row is None or row.missing:
            self.status_label.setText("Select the track to start from first.")
            return
        if row.bpm is None:
            self.status_label.setText("The current track has no BPM -- scan or tag it first.")
            return
        candidates = self.visible_rows()
        if row not in candidates:
            candidates.append(row)
        paths = workspace.generate_playlist(candidates, seed_path=row.path)
        name = self._ask_playlist_name(f"Mix from {row.title or Path(row.path).stem}")
        if name:
            self.create_playlist(name, paths, workspace.SOURCE_GENERATED)
            self.status_label.setText(f"{len(paths) - 1} compatible track(s) found.")

    def import_playlists(self, playlists: dict[str, list[str]], source: str) -> int:
        first_id = None
        for name, paths in playlists.items():
            playlist_id = self.db.create_playlist(name, paths, source)
            first_id = first_id if first_id is not None else playlist_id
        if source == workspace.SOURCE_SERATO:
            # Crate names are category hints (issue #127), so re-resolve.
            self._reload_rows()
        self._reload_playlists(select_id=first_id)
        self.side_tabs.setCurrentIndex(2)
        self.status_label.setText(f"Imported {len(playlists)} playlist(s) from {source}.")
        return len(playlists)

    def _import_with(self, reader: Callable[[str], dict[str, list[str]]], path: str, source: str) -> None:
        try:
            playlists = reader(path)
        except Exception as exc:
            _LOGGER.exception("Playlist import failed: %s", path)
            QMessageBox.warning(self, "Import failed", f"{path}\n\n{exc}")
            return
        self.import_playlists(playlists, source)

    def _on_import_serato_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Import Serato crates", "", "Serato crates (*.crate)")
        playlists = {}
        for path in paths:
            try:
                playlists[Path(path).stem] = workspace.read_serato_crate(path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Import failed", f"{path}\n\n{exc}")
        if playlists:
            self.import_playlists(playlists, workspace.SOURCE_SERATO)

    def _on_import_traktor_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Traktor playlists", "", "Traktor collection (*.nml)")
        if path:
            self._import_with(workspace.read_traktor_playlists, path, workspace.SOURCE_TRAKTOR)

    def _on_import_rekordbox_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Rekordbox playlists", "", "Rekordbox device export (export.pdb)"
        )
        if path:
            self._import_with(workspace.read_rekordbox_playlists, path, workspace.SOURCE_REKORDBOX)

    def export_playlist_as_crate(self, playlist_id: int, crate_path: str) -> None:
        workspace.export_serato_crate(crate_path, self.db.playlist_paths(playlist_id))
        self.status_label.setText(f"Exported {Path(crate_path).name}.")

    def _on_export_serato_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        name = self.playlist_list.currentItem().text().split("  (", 1)[0]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as Serato crate", f"{name}.crate", "Serato crates (*.crate)"
        )
        if path:
            try:
                self.export_playlist_as_crate(playlist_id, path)
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", f"{path}\n\n{exc}")

    def export_playlist_as_nml(self, playlist_id: int, nml_path: str, name: str) -> None:
        workspace.export_traktor_playlist(nml_path, name, self.db.playlist_paths(playlist_id), db=self.db)
        self.status_label.setText(f"Exported {Path(nml_path).name}.")

    def _on_export_traktor_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        name = self.playlist_list.currentItem().text().split("  (", 1)[0]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as Traktor playlist", f"{name}.nml", "Traktor playlists (*.nml)"
        )
        if path:
            try:
                self.export_playlist_as_nml(playlist_id, path, name)
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", f"{path}\n\n{exc}")

    def _on_rename_playlist_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        current = self.playlist_list.currentItem().text().split("  (", 1)[0]
        name = self._ask_playlist_name(current)
        if name:
            self.db.rename_playlist(playlist_id, name)
            self._reload_playlists(select_id=playlist_id)

    def _on_delete_playlist_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete playlist",
            "Delete this playlist from the app's library? Files and DJ-software playlists are not touched.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_playlist(playlist_id)
            self._reload_playlists()


def _playlist_track_label(path: str, row: workspace.LibraryRow | None) -> str:
    if row is None or row.metadata is None or not row.metadata.title:
        return Path(path).name
    artist = f"{row.metadata.artist} — " if row.metadata.artist else ""
    details = " · ".join(filter(None, [_format_bpm(row.bpm), row.camelot_key or ""]))
    return f"{artist}{row.metadata.title}" + (f"  [{details}]" if details else "")


def _playlist_track_item(path: str, row: workspace.LibraryRow | None) -> QListWidgetItem:
    item = QListWidgetItem(_playlist_track_label(path, row))
    item.setToolTip(path if row is not None else f"Not in the indexed folders: {path}")
    if row is None:
        item.setForeground(QBrush(QColor("#888888")))
    return item
