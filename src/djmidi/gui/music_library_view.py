"""Music Library tab (issue #132): the GUI home for the library initiative.

Binds the Qt-free `djmidi.library` layer (scan index, tag cache, taxonomy,
playlist engine, Serato/Traktor/Rekordbox formats) to one tab:

- music folder list + a "Scan & read tags" job, driven a slice at a time by
  a `QTimer` (this project's non-blocking pattern, see `midi_io` polling),
  and a "Find duplicates…" job on the same timer (issue #184, opens a
  `DuplicatesDialog` whose ticked copies `discard_duplicates` moves to the
  Trash, issue #208), and a "Health report…" job (issue #225, opens a
  read-only `HealthReportDialog`: unreadable, empty-tag, cover-less,
  low-bitrate and zero-length files, filterable, exportable to CSV), and a
  "Statistics…" window (issue #258, `LibraryStatsDialog`: categories,
  genres, BPM, Camelot keys, files added per month, most/never played);
- the consolidated metadata table (sortable/filterable, category column);
- a Track panel whose tag edits go through a `QUndoStack`
  (`commands.WriteTrackMetadataCommand`, or `WriteTracksMetadataCommand` when
  "Write tags to selection…" copies chosen fields to every selected track,
  or `RenameFilesCommand` when "Rename files…" renames them from a tag
  template, issue #260),
  with an embedded cover-art preview set/removed through
  `WriteTrackCoverCommand` (issue #256),
  a Categories panel over the
  taxonomy registry, a Playlists panel (import/generate/export), a History
  panel (issue #227: Serato/Traktor play history, read-only, plus the
  indexed tracks never played), and a Set panel (`gui/set_preparation.py`,
  issue #221) where a set is built by dragging table rows in play order.

Opening the library index is lazy (first time the tab is shown), so merely
constructing the main window never creates or reads `library.sqlite3`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    QAbstractTableModel,
    QCoreApplication,
    QEvent,
    QFile,
    QItemSelection,
    QItemSelectionModel,
    QMimeData,
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QPixmap, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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

from djmidi import taxonomy, user_paths
from djmidi.gui import help_texts
from djmidi.gui.audio_preview import AudioPreviewBar
from djmidi.gui.change_history_dialog import ChangeHistoryDialog
from djmidi.gui.commands import (
    RenameFilesCommand,
    WriteTrackCoverCommand,
    WriteTrackMetadataCommand,
    WriteTracksMetadataCommand,
)
from djmidi.gui.duplicates_dialog import DuplicatesDialog
from djmidi.gui.health_report_dialog import HealthReportDialog
from djmidi.gui.help_button import help_button, help_row
from djmidi.gui.library_stats_dialog import LibraryStatsDialog
from djmidi.gui.rename_files_dialog import RenameFilesDialog
from djmidi.gui.set_preparation import (
    SET_TRACKS_MIME,
    SetPreparationPanel,
    encode_paths,
)
from djmidi.gui.smart_export_dialog import SmartExportDialog
from djmidi.gui.translation import translator
from djmidi.gui.window_size import keep_tab_titles_whole, keep_wrapped_text_visible
from djmidi.library import (
    change_log,
    discard,
    duplicates,
    health,
    history,
    relink,
    rename,
    set_prep,
    smart_playlist,
    stats,
    workspace,
)
from djmidi.library.analysis import analysis_available, to_camelot
from djmidi.library.cover_art import load_cover_file, read_cover_art
from djmidi.library.db import LibraryDB, TrackRecord, default_library_db_path
from djmidi.library.metadata import TrackMetadata, clean_noise_frames
from djmidi.library.playlist import is_camelot_compatible
from djmidi.library.playlist_compare import PlaylistComparison, compare_playlists
from djmidi.library.relink import RelinkCandidate, RelinkProposal
from djmidi.library.scanner import iter_scan_root

_LOGGER = logging.getLogger(__name__)

# The last "Rename files…" template, remembered in the library index.
_RENAME_TEMPLATE_SETTING = "rename_template"

# How many entries a confirmation lists before "… and N more".
_LIST_LIMIT = 15


def trash_file(path: str) -> bool | str:
    """Move `path` to the system Trash (issue #208); never deletes it.

    Returns the file's new path inside the Trash (so the change history can
    put it back, issue #261), or False when it couldn't be moved."""
    file = QFile(path)
    if not file.moveToTrash():
        return False
    return file.fileName() or True


def _bullet_list(lines) -> str:
    items = list(lines)
    text = "\n".join(f"• {line}" for line in items[:_LIST_LIMIT])
    if len(items) > _LIST_LIMIT:
        text += "\n" + QCoreApplication.translate("MusicLibraryView", "… and {count} more").format(count=len(items) - _LIST_LIMIT)
    return text


def _group_name(group: duplicates.DuplicateGroup) -> str:
    return group.label or (Path(group.paths[0]).name if group.paths else group.key)

# Time slice a job may use per timer tick before yielding back to Qt.
# A bulk tag write shows its progress window only past this delay, so a
# handful of files doesn't flash a dialog.
_PROGRESS_DELAY_MS = 400
_SLICE_SECONDS = 0.025

# (header, key) -- key is a TrackMetadata field or a LibraryRow extra.
COLUMNS: tuple[tuple[str, str], ...] = (
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Title"), "title"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Artist"), "artist"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Album"), "album"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Genre"), "genre"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Category"), "category"),
    ("BPM", "bpm"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Key"), "key"),
    ("Camelot", "camelot"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Rating"), "rating"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Energy"), "energy"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Comment"), "comment"),
    (QT_TRANSLATE_NOOP("MusicLibraryView", "Path"), "path"),
)
_COLUMN_INDEX = {key: index for index, (_header, key) in enumerate(COLUMNS)}
_EDIT_FIELDS = ("title", "artist", "album", "genre", "bpm", "key", "comment", "rating", "energy")
# Side of the Track panel's cover-art preview, in pixels (issue #256).
_COVER_SIZE = 140

# Below this the tab scrolls rather than squeezing its panels (issue #19).
# "Auto: mix path…" choices -> playlist.build_playlist_path directions.
PATH_DIRECTION_LABELS = {
    QT_TRANSLATE_NOOP("MixPathDialog", "Rising BPM"): "up",
    QT_TRANSLATE_NOOP("MixPathDialog", "Falling BPM"): "down",
    QT_TRANSLATE_NOOP("MixPathDialog", "Steady BPM (smallest moves)"): "flat",
}

_CONTENT_MIN_WIDTH = 920
_CONTENT_MIN_HEIGHT = 440

# Data keys of the filter combos; shown through tr() (issue #306).
ALL_CATEGORIES = QT_TRANSLATE_NOOP("MusicLibraryView", "All categories")
UNCATEGORIZED = QT_TRANSLATE_NOOP("MusicLibraryView", "Uncategorized")
ALL_GENRES = QT_TRANSLATE_NOOP("MusicLibraryView", "All genres")
ALL_KEYS = QT_TRANSLATE_NOOP("MusicLibraryView", "All keys")
ALL_CAMELOT = QT_TRANSLATE_NOOP("MusicLibraryView", "All Camelot")
# Wheel order: 1A, 1B, 2A, … 12B.
CAMELOT_CODES = tuple(f"{number}{letter}" for number in range(1, 13) for letter in "AB")
_BPM_FILTER_MAX = 300

_ANALYSE_LABEL = QT_TRANSLATE_NOOP("MusicLibraryView", "Analyse BPM/key")
_STOP_ANALYSIS_LABEL = QT_TRANSLATE_NOOP("MusicLibraryView", "Stop analysis")
_ANALYSIS_UNAVAILABLE = QT_TRANSLATE_NOOP(
    "MusicLibraryView",
    "Audio analysis needs the optional 'analysis' extra (librosa), which isn't installed. "
    "From a source checkout: uv sync --extra analysis.",
)
_SUGGESTION_COLOR = "#b07a00"

ROW_ROLE = Qt.ItemDataRole.UserRole + 1
SORT_ROLE = Qt.ItemDataRole.UserRole + 2


def category_label(canonical: str | None) -> str:
    return canonical.replace("%%", " / ") if canonical else ""


def _format_bpm(bpm: float | None) -> str:
    if bpm is None:
        return ""
    return f"{bpm:g}" if bpm == int(bpm) else f"{bpm:.2f}"


class _TabContent(QWidget):
    """The scrolled body of the tab: at least _CONTENT_MIN_WIDTH x
    _CONTENT_MIN_HEIGHT, and never narrower than its own layout needs. A fixed
    setMinimumSize() hid the layout's minimum from the scroll area, so the
    longer French filter row squeezed "Reset filters" at 900x600 (issue #327)."""

    def minimumSizeHint(self) -> QSize:
        return super().minimumSizeHint().expandedTo(QSize(_CONTENT_MIN_WIDTH, _CONTENT_MIN_HEIGHT))


class _SidePanelScroll(QScrollArea):
    """Scrolls a side panel vertically only, and asks for the panel's whole
    minimum width plus the scroll bar. A plain QScrollArea asks for almost
    nothing, so on macOS in French the splitter left the Track panel 21 px
    short and its help button sat half under the scroll bar (issue #19)."""

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        panel = self.widget()
        if panel is None:
            return hint
        width = panel.minimumSizeHint().width() + self.verticalScrollBar().sizeHint().width() + 2 * self.frameWidth()
        return QSize(max(hint.width(), width), hint.height())


def _scrolled(panel: QWidget) -> QScrollArea:
    area = _SidePanelScroll()
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(panel)
    return area


def _field_text(name: str, value: object) -> str:
    if name == "bpm":
        return _format_bpm(value)
    return "" if value is None else str(value)


_FIELD_LABELS = {
    "title": QT_TRANSLATE_NOOP("MusicLibraryView", "Title"),
    "artist": QT_TRANSLATE_NOOP("MusicLibraryView", "Artist"),
    "album": QT_TRANSLATE_NOOP("MusicLibraryView", "Album"),
    "genre": QT_TRANSLATE_NOOP("MusicLibraryView", "Genre"),
    "bpm": "BPM",
    "key": QT_TRANSLATE_NOOP("MusicLibraryView", "Key"),
    "comment": QT_TRANSLATE_NOOP("MusicLibraryView", "Comment"),
    "rating": QT_TRANSLATE_NOOP("MusicLibraryView", "Rating"),
    "energy": QT_TRANSLATE_NOOP("MusicLibraryView", "Energy"),
}


def _field_label(name: str) -> str:
    return QCoreApplication.translate("MusicLibraryView", _FIELD_LABELS.get(name, name.capitalize()))


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
        self.setWindowTitle(self.tr("Write tags to selection"))
        self.setMinimumWidth(420)
        box = QVBoxLayout(self)
        intro = QLabel(
            self.tr(
                "Check the tag(s) to write to the {count} selected track(s). Unchecked tags are left "
                "as they are in every file; a checked empty field clears that tag. Serato/Traktor data is preserved."
            ).format(count=track_count)
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
            edit.setPlaceholderText(self.tr("(empty: clears the tag)"))
            edit.setEnabled(check.isChecked())
            check.toggled.connect(edit.setEnabled)
            check.toggled.connect(self._update_ok)
            grid.addWidget(check, row, 0)
            grid.addWidget(edit, row, 1)
            self.checks[name] = check
            self.edits[name] = edit
        box.addLayout(grid)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Write to {count} track(s)").format(count=track_count))
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
            QMessageBox.warning(self, self.tr("Invalid BPM"), self.tr("BPM must be a number, e.g. 174 or 128.5."))
            return
        self.accept()


class MixPathDialog(QDialog):
    """The "Auto: mix path…" options (issues #191/#211): BPM direction, BPM
    tolerance and maximum length, pre-filled with the last values used."""

    def __init__(
        self,
        options: workspace.MixPathOptions,
        track_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Mix path"))
        self.setMinimumWidth(380)
        options = options.normalized()
        box = QVBoxLayout(self)
        form = QFormLayout()
        self.direction_combo = QComboBox()
        for label, direction in PATH_DIRECTION_LABELS.items():
            self.direction_combo.addItem(self.tr(label), direction)
        self.direction_combo.setCurrentIndex(max(self.direction_combo.findData(options.direction), 0))
        form.addRow(self.tr("BPM direction:"), self.direction_combo)
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(*workspace.MIX_PATH_TOLERANCE_RANGE)
        self.tolerance_spin.setSingleStep(0.5)
        self.tolerance_spin.setDecimals(1)
        self.tolerance_spin.setPrefix("± ")
        self.tolerance_spin.setSuffix(" %")
        self.tolerance_spin.setValue(options.bpm_tolerance_pct)
        self.tolerance_spin.setToolTip(self.tr("Largest BPM gap allowed between two consecutive tracks."))
        form.addRow(self.tr("BPM tolerance:"), self.tolerance_spin)
        self.length_spin = QSpinBox()
        self.length_spin.setRange(0, workspace.MIX_PATH_MAX_LENGTH_LIMIT)
        self.length_spin.setSpecialValueText(self.tr("No limit"))
        self.length_spin.setSuffix(self.tr(" tracks"))
        self.length_spin.setValue(options.max_length or 0)
        self.length_spin.setToolTip(self.tr("Stop the path after this many tracks; the rest go to the leftovers."))
        form.addRow(self.tr("Maximum length:"), self.length_spin)
        box.addLayout(form)
        self.note_label = QLabel(
            self.tr(
                "Uses only the {count} track(s) the current filter shows (plus the selected start "
                "track). Clear the filters first to build from the whole library."
            ).format(count=track_count)
        )
        self.note_label.setWordWrap(True)
        self.note_label.setEnabled(False)
        box.addWidget(self.note_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def options(self) -> workspace.MixPathOptions:
        length = self.length_spin.value()
        return workspace.MixPathOptions(
            direction=self.direction_combo.currentData(),
            bpm_tolerance_pct=self.tolerance_spin.value(),
            max_length=length or None,
        ).normalized()


class SmartPlaylistDialog(QDialog):
    """Name and rules of a smart playlist (issue #259). Every rule left at
    its "any"/0 value is off; the rest are AND-ed."""

    def __init__(
        self,
        name: str,
        rules: smart_playlist.SmartRules,
        has_history: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Smart playlist"))
        self.setMinimumWidth(420)
        box = QVBoxLayout(self)
        form = QFormLayout()
        # macOS keeps line edits at their small size hint, which cut the
        # (French) placeholders: let them take the dialog's width.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name_edit = QLineEdit(name)
        form.addRow(self.tr("Name:"), self.name_edit)
        self.category_combo = QComboBox()
        self.category_combo.addItem(self.tr("Any category"), None)
        for family in taxonomy.families():
            self.category_combo.addItem(self.tr("{family} (whole family)").format(family=family), family)
        for category in taxonomy.all_categories():
            self.category_combo.addItem(category_label(category.canonical), category.canonical)
        if rules.category is not None and self.category_combo.findData(rules.category) < 0:
            self.category_combo.addItem(category_label(rules.category), rules.category)
        self.category_combo.setCurrentIndex(max(self.category_combo.findData(rules.category), 0))
        form.addRow(self.tr("Category:"), self.category_combo)
        self.genre_edit = QLineEdit(rules.genre or "")
        self.genre_edit.setPlaceholderText(self.tr("Genre tag contains…"))
        form.addRow(self.tr("Genre:"), self.genre_edit)
        self.text_edit = QLineEdit(rules.text or "")
        self.text_edit.setPlaceholderText(self.tr("Title, artist, album or path contains…"))
        form.addRow(self.tr("Text:"), self.text_edit)
        bpm_row = QHBoxLayout()
        self.bpm_min_spin = self._bpm_spin(rules.bpm_min, self.tr("Any"))
        self.bpm_max_spin = self._bpm_spin(rules.bpm_max, self.tr("Any"))
        bpm_row.addWidget(self.bpm_min_spin)
        bpm_row.addWidget(QLabel(self.tr("to")))
        bpm_row.addWidget(self.bpm_max_spin)
        form.addRow(self.tr("BPM:"), bpm_row)
        key_row = QHBoxLayout()
        self.key_combo = QComboBox()
        self.key_combo.addItem(self.tr("Any key"), None)
        for code in CAMELOT_CODES:
            self.key_combo.addItem(code, code)
        self.key_combo.setCurrentIndex(max(self.key_combo.findData(rules.camelot_key), 0))
        self.key_compatible_check = QCheckBox(self.tr("or compatible"))
        self.key_compatible_check.setToolTip(self.tr("Also every key that mixes harmonically with it (±1, relative)."))
        self.key_compatible_check.setChecked(rules.key_compatible)
        key_row.addWidget(self.key_combo, 1)
        key_row.addWidget(self.key_compatible_check)
        form.addRow(self.tr("Camelot key:"), key_row)
        self.not_played_spin = QSpinBox()
        self.not_played_spin.setRange(0, 3650)
        self.not_played_spin.setSpecialValueText(self.tr("Off"))
        self.not_played_spin.setSuffix(self.tr(" days"))
        self.not_played_spin.setValue(rules.not_played_days or 0)
        self.not_played_spin.setToolTip(
            self.tr(
                "Never played, or last played longer ago than this, per the DJ history last loaded in the "
                "History panel."
            )
        )
        form.addRow(self.tr("Not played for:"), self.not_played_spin)
        self.sort_combo = QComboBox()
        for sort, label in smart_playlist.SORT_LABELS.items():
            self.sort_combo.addItem(QCoreApplication.translate("SmartPlaylistDialog", label), sort)
        self.sort_combo.setCurrentIndex(max(self.sort_combo.findData(rules.sort), 0))
        form.addRow(self.tr("Order:"), self.sort_combo)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 100000)
        self.limit_spin.setSpecialValueText(self.tr("No limit"))
        self.limit_spin.setSuffix(self.tr(" tracks"))
        self.limit_spin.setValue(rules.limit or 0)
        form.addRow(self.tr("Maximum length:"), self.limit_spin)
        box.addLayout(form)
        if not has_history:
            self.history_note = QLabel(
                self.tr(
                    "No DJ history loaded yet: “Not played for” treats every track as never played until "
                    "you load it in the History panel."
                )
            )
            self.history_note.setWordWrap(True)
            self.history_note.setEnabled(False)
            box.addWidget(self.history_note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.name_edit.textChanged.connect(lambda text: self._ok_button.setEnabled(bool(text.strip())))
        self._ok_button.setEnabled(bool(name.strip()))
        box.addWidget(buttons)
        keep_wrapped_text_visible(self)

    @staticmethod
    def _bpm_spin(value: float | None, any_text: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, _BPM_FILTER_MAX)
        spin.setDecimals(1)
        spin.setSpecialValueText(any_text)
        spin.setValue(value or 0)
        return spin

    def name(self) -> str:
        return self.name_edit.text().strip()

    def rules(self) -> smart_playlist.SmartRules:
        return smart_playlist.SmartRules(
            category=self.category_combo.currentData(),
            genre=self.genre_edit.text(),
            text=self.text_edit.text(),
            bpm_min=self.bpm_min_spin.value() or None,
            bpm_max=self.bpm_max_spin.value() or None,
            camelot_key=self.key_combo.currentData(),
            key_compatible=self.key_compatible_check.isChecked(),
            not_played_days=self.not_played_spin.value() or None,
            sort=self.sort_combo.currentData(),
            limit=self.limit_spin.value() or None,
        ).normalized()

    def _on_accept(self) -> None:
        if self.name():
            self.accept()


class PlaylistCompareDialog(QDialog):
    """Read-only result of comparing an app playlist with a Serato crate or a
    Traktor playlist (issue #229): one tab per difference kind. Nothing here
    changes either side -- export stays a separate button."""

    def __init__(
        self,
        comparison: PlaylistComparison,
        app_name: str,
        other_name: str,
        label_for: Callable[[str], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Compare playlists"))
        self.resize(640, 460)
        box = QVBoxLayout(self)
        shared = len(comparison.in_both)
        if comparison.identical:
            summary = self.tr("“{app}” and {other} list the same {shared} track(s) in the same order.").format(
                app=app_name, other=other_name, shared=shared
            )
        else:
            summary = self.tr(
                "“{app}” and {other}: {shared} track(s) in both, {only_app} only in the app playlist, "
                "{only_other} only in {other}, {moved} in a different order."
            ).format(
                app=app_name,
                other=other_name,
                shared=shared,
                only_app=len(comparison.only_in_app),
                only_other=len(comparison.only_in_other),
                moved=len(comparison.moved),
            )
        self.summary_label = QLabel(summary)
        self.summary_label.setWordWrap(True)
        box.addWidget(self.summary_label)
        self.tabs = QTabWidget()
        self.only_app_list = self._add_tab(
            self.tr("Only in app ({count})").format(count=len(comparison.only_in_app)),
            [f"#{t.app_position}  {label_for(t.path)}" for t in comparison.only_in_app],
            comparison.only_in_app,
        )
        self.only_other_list = self._add_tab(
            self.tr("Only in {other} ({count})").format(other=other_name, count=len(comparison.only_in_other)),
            [f"#{t.other_position}  {label_for(t.path)}" for t in comparison.only_in_other],
            comparison.only_in_other,
        )
        self.moved_list = self._add_tab(
            self.tr("Order differences ({count})").format(count=len(comparison.moved)),
            [f"#{t.app_position} → #{t.other_position}  {label_for(t.path)}" for t in comparison.moved],
            comparison.moved,
        )
        box.addWidget(self.tabs, 1)
        note = QLabel(
            self.tr(
                "Positions read “app → other”. Order differences list only the tracks out of place "
                "relative to the others; tracks missing on one side don't count as moves. "
                "Nothing is changed: export the playlist to update the other side."
            )
        )
        note.setWordWrap(True)
        note.setEnabled(False)
        box.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def _add_tab(self, title: str, lines: list[str], tracks) -> QListWidget:
        widget = QListWidget()
        for line, track in zip(lines, tracks, strict=True):
            item = QListWidgetItem(line)
            item.setToolTip(track.path)
            widget.addItem(item)
        if not lines:
            widget.addItem(QListWidgetItem(self.tr("(none)")))
            widget.setEnabled(False)
        self.tabs.addTab(widget, title)
        return widget


class RelinkDialog(QDialog):
    """Review `relink.RelinkProposal`s (issue #190): one checkable row per
    missing track, its proposed new path (a combo when several files
    match), and how it matched. Confident proposals start checked; a track
    with no match is listed but can't be checked."""

    def __init__(self, proposals: list[RelinkProposal], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Relink missing tracks"))
        self.resize(900, 420)
        self._proposals = proposals
        box = QVBoxLayout(self)
        intro = QLabel(
            self.tr(
                "Files that moved since they were indexed. Checked tracks are relinked in this app's index "
                "only: their playlists and cached tags follow the new path. No audio file or DJ software "
                "library is modified. Pre-checked rows have exactly one file with the same name and size."
            )
        )
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([self.tr("Missing track"), self.tr("Relink to"), self.tr("Match")])
        self.tree.setRootIsDecorated(False)
        self._combos: dict[int, QComboBox] = {}
        for index, proposal in enumerate(proposals):
            item = QTreeWidgetItem([proposal.missing.path, "", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            self.tree.addTopLevelItem(item)
            if not proposal.candidates:
                item.setText(1, self.tr("No matching file found"))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                continue
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if proposal.confident else Qt.CheckState.Unchecked)
            item.setText(2, _match_label(proposal.best))
            if len(proposal.candidates) == 1:
                item.setText(1, proposal.best.path)
                continue
            combo = QComboBox()
            for candidate in proposal.candidates:
                combo.addItem(candidate.path)
            combo.currentIndexChanged.connect(
                lambda row, item=item, proposal=proposal: item.setText(2, _match_label(proposal.candidates[row]))
            )
            self._combos[index] = combo
            self.tree.setItemWidget(item, 1, combo)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 320)
        box.addWidget(self.tree, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Relink checked…"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.tree.itemChanged.connect(self._update_ok)
        box.addWidget(self.buttons)
        self._update_ok()

    def _update_ok(self, *_args: object) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.choices()))

    def set_choice(self, index: int, checked: bool, candidate_index: int = 0) -> None:
        item = self.tree.topLevelItem(index)
        item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        if index in self._combos:
            self._combos[index].setCurrentIndex(candidate_index)

    def choices(self) -> list[tuple[TrackRecord, RelinkCandidate]]:
        """Checked (missing track, chosen candidate) pairs."""
        result = []
        for row in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(row)
            if item.checkState(0) != Qt.CheckState.Checked:
                continue
            proposal = self._proposals[item.data(0, Qt.ItemDataRole.UserRole)]
            combo = self._combos.get(row)
            candidate = proposal.candidates[combo.currentIndex() if combo is not None else 0]
            result.append((proposal.missing, candidate))
        return result


def _match_label(candidate: RelinkCandidate) -> str:
    if candidate.match == relink.MATCH_EXACT:
        label = QCoreApplication.translate("MusicLibraryView", "Same name and size")
    elif candidate.match == relink.MATCH_NAME:
        label = QCoreApplication.translate("MusicLibraryView", "Same name, other size")
    else:
        label = QCoreApplication.translate("MusicLibraryView", "Same title and artist")
    if candidate.tags_agree and candidate.match != relink.MATCH_TAGS:
        label += QCoreApplication.translate("MusicLibraryView", " + tags")
    return label + ("" if candidate.indexed else QCoreApplication.translate("MusicLibraryView", " (not scanned yet)"))


def _can_confirm_suggestion(row: workspace.LibraryRow) -> bool:
    return bool(row.category is None and row.category_suggestion and row.metadata and row.metadata.genre)


def _analysis_suggestion_text(row: workspace.LibraryRow, key: str) -> str | None:
    """The audio-analysis estimate a BPM/Key/Camelot cell shows in place of
    an empty tag (issue #224), or None."""
    if key == "bpm" and row.bpm_suggestion is not None:
        return _format_bpm(row.bpm_suggestion)
    if key == "key" and row.key_suggestion:
        return row.key_suggestion
    if key == "camelot" and row.camelot_key is None and row.key_suggestion:
        return to_camelot(row.key_suggestion)
    return None


def _analysis_text(row: workspace.LibraryRow) -> str:
    """Track panel line for the selected track's audio-analysis estimates."""
    parts = []
    if row.bpm_suggestion is not None:
        parts.append(f"{_format_bpm(row.bpm_suggestion)} BPM")
    if row.key_suggestion:
        camelot = to_camelot(row.key_suggestion)
        parts.append(row.key_suggestion + (f" ({camelot})" if camelot else ""))
    return QCoreApplication.translate("MusicLibraryView", "Estimated: {values}").format(values=", ".join(parts)) if parts else "—"


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
        # The model sorts itself (the proxy forwards sort() here): one Python
        # sort with a key beats Qt calling data() ~2.5M times on 85k rows.
        self._sort: tuple[int, Qt.SortOrder] | None = None
        # Lower-cased, tab-joined display text of each row, built on the
        # first text filter, keyed by row identity so a re-sort keeps it.
        self._search_text: dict[int, str] | None = None

    def set_rows(self, rows: list[workspace.LibraryRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._search_text = None
        if self._sort is not None:
            self._rows.sort(key=self._sort_key(self._sort[0]), reverse=self._sort[1] == Qt.SortOrder.DescendingOrder)
        self.endResetModel()

    @staticmethod
    def _sort_key(column: int):
        key = COLUMNS[column][1]
        if key == "bpm":
            return lambda row: row.bpm if row.bpm is not None else -1.0
        return lambda row: LibraryTableModel._display(row, key).casefold()

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sorts in place (same keys as `SORT_ROLE`), keeping selections:
        the persistent indexes follow their rows."""
        if not 0 <= column < len(COLUMNS):
            return
        self._sort = (column, order)
        self.layoutAboutToBeChanged.emit()
        before = self.persistentIndexList()
        moved = [(self._rows[index.row()], index.column()) for index in before]
        self._rows.sort(key=self._sort_key(column), reverse=order == Qt.SortOrder.DescendingOrder)
        position = {id(row): number for number, row in enumerate(self._rows)}
        self.changePersistentIndexList(before, [self.index(position[id(row)], col) for row, col in moved])
        self.layoutChanged.emit()

    def row_at(self, row_number: int) -> workspace.LibraryRow:
        return self._rows[row_number]

    def replace_row(self, old: workspace.LibraryRow, new: workspace.LibraryRow) -> None:
        """Swaps one row in place (a stage note edit) without a model reset."""
        for number, row in enumerate(self._rows):
            if row is old:
                self._rows[number] = new
                if self._search_text is not None:
                    self._search_text.pop(id(old), None)
                    self._search_text = None
                self.dataChanged.emit(self.index(number, 0), self.index(number, len(COLUMNS) - 1))
                return

    def search_text(self, row_number: int) -> str:
        """Every column's display text of a row, lower-cased, for the free
        text filter."""
        if self._search_text is None:
            self._search_text = {
                id(row): "\t".join(self._display(row, key) for _header, key in COLUMNS).casefold() for row in self._rows
            }
        row = self._rows[row_number]
        return self._search_text.get(id(row), "")

    def rows(self) -> list[workspace.LibraryRow]:
        return list(self._rows)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return QCoreApplication.translate("MusicLibraryView", COLUMNS[section][0])
        return None

    # Dragging rows out (to the Set panel, issue #221) carries their paths.
    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsDragEnabled if index.isValid() else flags

    def mimeTypes(self) -> list[str]:
        return [SET_TRACKS_MIME]

    def mimeData(self, indexes) -> QMimeData:
        rows = sorted({index.row() for index in indexes if index.isValid()})
        mime = QMimeData()
        mime.setData(SET_TRACKS_MIME, encode_paths([self._rows[row].path for row in rows]))
        return mime

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.CopyAction

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
        estimated = _analysis_suggestion_text(row, key) is not None
        if estimated and role == Qt.ItemDataRole.ToolTipRole and not row.missing:
            return QCoreApplication.translate("LibraryTableModel", "Estimated from the audio -- not in the file. Apply it from the Track panel.")
        suggested = suggested or estimated
        if role == Qt.ItemDataRole.ForegroundRole:
            if row.missing:
                return QBrush(QColor("#888888"))
            return QBrush(QColor(_SUGGESTION_COLOR)) if suggested else None
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
            return QCoreApplication.translate("LibraryTableModel", "Missing on disk: {path}").format(path=row.path)
        if suggested:
            return QCoreApplication.translate("LibraryTableModel", "Fuzzy suggestion only -- confirm it from the Track panel to make it stick.")
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
        estimate = _analysis_suggestion_text(row, key)
        if estimate is not None:
            return f"? {estimate}"
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
        self._text = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)
        self.setSortRole(SORT_ROLE)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sorting is done by the source model (much faster on a large
        collection); the proxy keeps its order and only filters."""
        source = self.sourceModel()
        if isinstance(source, LibraryTableModel):
            source.sort(column, order)
        else:
            super().sort(column, order)

    def set_text_filter(self, text: str) -> None:
        """Case-insensitive substring in any column (what
        `setFilterFixedString` did, from cached row text)."""
        if text.casefold() != self._text:
            self._change_filter(lambda: setattr(self, "_text", text.casefold()))

    def is_filtering(self) -> bool:
        return bool(self._text) or self._category != ALL_CATEGORIES or self.has_track_filters()

    def text_filter(self) -> str:
        return self._text

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
        if category != self._category:
            self._change_filter(lambda: setattr(self, "_category", category))

    def set_genre_filter(self, genre: str | None) -> None:
        """Exact genre tag (case-insensitive); None for every genre."""
        value = _norm(genre) or None
        if value != self._genre:
            self._change_filter(lambda: setattr(self, "_genre", value))

    def set_bpm_range(self, minimum: float | None, maximum: float | None) -> None:
        """Inclusive BPM bounds; None leaves that side open. With any bound
        set, tracks without a BPM are hidden."""

        def apply() -> None:
            self._bpm_min, self._bpm_max = minimum, maximum

        if (minimum, maximum) != (self._bpm_min, self._bpm_max):
            self._change_filter(apply)

    def set_key_filter(self, key: str | None) -> None:
        """Exact key tag as written in the file (case-insensitive)."""
        value = _norm(key) or None
        if value != self._key:
            self._change_filter(lambda: setattr(self, "_key", value))

    def set_camelot_filter(self, camelot: str | None, compatible: bool = False) -> None:
        """One Camelot code; with `compatible`, also every harmonically
        compatible key (same code, ±1 on the wheel, relative major/minor)."""

        def apply() -> None:
            self._camelot = camelot.upper() if camelot else None
            self._camelot_compatible = compatible

        if (camelot.upper() if camelot else None, compatible) != (self._camelot, self._camelot_compatible):
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
        if isinstance(model, LibraryTableModel):
            row = model.row_at(source_row)  # no data() round trip per row
        else:
            row = model.data(model.index(source_row, 0, source_parent), ROW_ROLE)
        if self._category == UNCATEGORIZED and row.category is not None:
            return False
        if self._category not in (ALL_CATEGORIES, UNCATEGORIZED) and row.category != self._category:
            return False
        if not self._accepts_track(row):
            return False
        if self._text:
            return self._text in model.search_text(source_row)
        return True


class MusicLibraryView(QWidget):
    def __init__(self, db_path: str | Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._executor: ThreadPoolExecutor | None = None
        self.smart_export_dialog_factory = SmartExportDialog
        self._analysis_future: Future | None = None
        self._db: LibraryDB | None = None
        self.undo_stack = QUndoStack(self)
        self._job: Iterator[None] | None = None
        self._analysing = False
        self._job_timer = QTimer(self)
        self._job_timer.setInterval(0)
        self._job_timer.timeout.connect(self._run_job_slice)
        self._current_path: str | None = None
        self.duplicates_dialog: DuplicatesDialog | None = None
        self.history_dialog: ChangeHistoryDialog | None = None
        self._history_sessions: list[history.HistorySession] = []
        self.health_dialog: HealthReportDialog | None = None
        self.stats_dialog: LibraryStatsDialog | None = None

        # The whole tab scrolls below its real minimum instead of crushing
        # buttons into slivers (issue #19's standing rule for every tab).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self._scroll)
        content = _TabContent()
        self._scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.addWidget(self._build_folders_group())

        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self._build_table_panel())
        self.side_tabs = QTabWidget()
        self.side_tabs.addTab(_scrolled(self._build_track_panel()), self.tr("Track"))
        self.side_tabs.addTab(_scrolled(self._build_categories_panel()), self.tr("Categories"))
        self.side_tabs.addTab(_scrolled(self._build_playlists_panel()), self.tr("Playlists"))
        self._history_tab = self.side_tabs.addTab(_scrolled(self._build_history_panel()), self.tr("History"))
        self.set_panel = SetPreparationPanel(
            db=lambda: self.db,
            selected_rows=self.selected_rows,
            selected_playlist=self._selected_playlist,
            status=self.status_label.setText,
        )
        self.set_panel.saveRequested.connect(self.save_set)
        self.side_tabs.addTab(_scrolled(self.set_panel), self.tr("Set"))
        # Five tabs overflow the side panel's width: grow it instead of
        # showing squeezed scroll arrows (the tab itself scrolls, issue #19).
        # macOS also elided the titles to "Tr…" / "Hi…" (issue #290).
        keep_tab_titles_whole(self.side_tabs, scroll=False)
        body.addWidget(self.side_tabs)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 2)
        body.setChildrenCollapsible(False)
        # Stretch factors alone left the side panel at half the width; the
        # table is what needs the room.
        body.setSizes([680, 320])
        layout.addWidget(body, 1)
        # Issue #192: play the current track (gui/audio_preview.py).
        self.audio_preview = AudioPreviewBar(self)
        layout.addWidget(self.audio_preview)
        self.table.selectionModel().currentRowChanged.connect(self._preview_current_row)
        # Issue #210: Space / Left / Right in the table drive the preview,
        # and auto-advance moves to the next row when a track ends.
        self.table.installEventFilter(self)
        self.audio_preview.advanceRequested.connect(self._advance_preview)
        self._update_track_panel(None)

    # --- construction ---------------------------------------------------

    def _build_folders_group(self) -> QGroupBox:
        group = QGroupBox(self.tr("Music folders"))
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        box = QVBoxLayout(group)
        row = QHBoxLayout()
        self.roots_list = QListWidget()
        self.roots_list.setMaximumHeight(96)
        self.roots_list.setToolTip(self.tr("Folders this app indexes. Scanning never modifies your files."))
        row.addWidget(self.roots_list, 1)
        self.add_root_button = QPushButton(self.tr("Add folder…"))
        self.add_root_button.clicked.connect(self._on_add_root_clicked)
        self.remove_root_button = QPushButton(self.tr("Remove"))
        self.remove_root_button.clicked.connect(self._on_remove_root_clicked)
        self.scan_button = QPushButton(self.tr("Scan && read tags"))
        self.scan_button.setToolTip(
            self.tr("Index new/changed files and read their tags. Incremental: unchanged files are skipped.")
        )
        self.scan_button.clicked.connect(self.start_scan)
        self.relink_button = QPushButton(self.tr("Relink missing…"))
        self.relink_button.setToolTip(
            self.tr("Find where missing tracks moved (same file name and size) and relink them in this app's index.")
        )
        self.relink_button.clicked.connect(self.start_relink_search)
        self.duplicates_button = QPushButton(self.tr("Find duplicates…"))
        self.duplicates_button.setToolTip(
            self.tr(
                "List identical files, tracks sharing artist + title, and other versions of the same song "
                "(suggestions). Read-only: nothing is deleted."
            )
        )
        self.duplicates_button.clicked.connect(self.find_duplicates)
        self.health_button = QPushButton(self.tr("Health report…"))
        self.health_button.setToolTip(
            self.tr(
                "List unreadable files, empty title/artist, missing artwork, low bitrate (≤128 kbps) "
                "and zero-length files. Read-only."
            )
        )
        self.health_button.clicked.connect(self.start_health_report)
        self.history_button = QPushButton(self.tr("Change history…"))
        self.history_button.setToolTip(
            self.tr(
                "Every tag, cover and rename write and Trash move this app made, kept across restarts. "
                "Inspect and revert them."
            )
        )
        self.history_button.clicked.connect(self.show_change_history)
        self.stats_button = QPushButton(self.tr("Statistics…"))
        self.stats_button.setToolTip(
            self.tr(
                "Charts of the tracks shown: categories, genres, BPM, keys, files added per month and, "
                "with DJ history loaded, most/never played. Read-only."
            )
        )
        self.stats_button.clicked.connect(self.show_statistics)
        # Issue #224: needs the optional 'analysis' extra; greyed out with
        # the reason as tooltip when librosa isn't installed.
        self.analyse_button = QPushButton(self.tr(_ANALYSE_LABEL))
        self.analyse_button.clicked.connect(self._on_analyse_clicked)
        if analysis_available():
            self.analyse_button.setToolTip(
                self.tr(
                    "Estimate BPM and key from the audio for tracks whose tags lack them. Results are "
                    "shown as amber suggestions only; nothing is written until you apply them."
                )
            )
        else:
            self.analyse_button.setEnabled(False)
            self.analyse_button.setToolTip(self.tr(_ANALYSIS_UNAVAILABLE))
        # Two button columns rather than one row: six buttons side by side
        # need more width than the tab's minimum content width guarantees.
        buttons = QGridLayout()
        for index, button in enumerate(
            (
                self.add_root_button,
                self.scan_button,
                self.remove_root_button,
                self.duplicates_button,
                self.relink_button,
                self.health_button,
                self.stats_button,
                self.analyse_button,
                self.history_button,
            )
        ):
            buttons.addWidget(button, index // 2, index % 2)
        buttons.addWidget(help_button(self, *help_texts.LIBRARY_FOLDERS), 0, 2, Qt.AlignmentFlag.AlignTop)
        row.addLayout(buttons)
        box.addLayout(row)
        status_row = QHBoxLayout()
        self.status_label = QLabel(self.tr("Add a music folder, then scan it."))
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
        self.filter_edit.setPlaceholderText(self.tr("Filter by artist, title, genre, BPM, key, comment…"))
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
        # Rows drag out to the Set panel (issue #221); the table itself
        # never accepts drops.
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
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
        self.genre_filter.setToolTip(self.tr("Only tracks with this genre tag"))
        self.bpm_min_filter = QSpinBox()
        self.bpm_max_filter = QSpinBox()
        bounds = (
            (self.bpm_min_filter, self.tr("min"), self.tr("Minimum BPM (inclusive); leave at “{label}” for no limit")),
            (self.bpm_max_filter, self.tr("max"), self.tr("Maximum BPM (inclusive); leave at “{label}” for no limit")),
        )
        for spin, label, tip in bounds:
            spin.setRange(0, _BPM_FILTER_MAX)
            spin.setSpecialValueText(label)
            spin.setToolTip(tip.format(label=label))
            spin.setAccelerated(True)
        self.key_filter = QComboBox()
        self.key_filter.setToolTip(self.tr("Only tracks with this key tag, as written in the file"))
        self.camelot_filter = QComboBox()
        self.camelot_filter.addItem(self.tr(ALL_CAMELOT), None)
        for code in CAMELOT_CODES:
            self.camelot_filter.addItem(code, code)
        self.camelot_filter.setToolTip(self.tr("Only tracks in this Camelot key"))
        self.camelot_compatible_check = QCheckBox(self.tr("+ compatible"))
        self.camelot_compatible_check.setToolTip(
            self.tr("Also show harmonically compatible keys: ±1 on the wheel and the relative major/minor")
        )
        # A long genre or key must not widen the table panel: size each combo
        # from a few characters, the popup still shows full names -- but
        # always wide enough for its own "All …" entry, which French makes
        # longer ("Toutes les tonalités" was cut off, issue #327).
        combos = (
            (self.genre_filter, 8, ALL_GENRES),
            (self.key_filter, 5, ALL_KEYS),
            (self.camelot_filter, 5, ALL_CAMELOT),
        )
        for combo, length, everything in combos:
            combo.setMinimumContentsLength(max(length, len(self.tr(everything))))
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.reset_filters_button = QPushButton(self.tr("Reset filters"))
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
        self._refill_combo(self.genre_filter, self.tr(ALL_GENRES), [])
        self._refill_combo(self.key_filter, self.tr(ALL_KEYS), [])

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
        box.addLayout(self._build_cover_row())
        form = QFormLayout()
        self.field_edits: dict[str, QLineEdit] = {}
        for name in _EDIT_FIELDS:
            edit = QLineEdit()
            edit.returnPressed.connect(self.apply_track_edits)
            self.field_edits[name] = edit
            form.addRow(_field_label(name), edit)
        self.camelot_label = QLabel()
        form.addRow(self.tr("Camelot"), self.camelot_label)
        self.category_value_label = QLabel()
        self.category_value_label.setWordWrap(True)
        form.addRow(self.tr("Category"), self.category_value_label)
        self.analysis_value_label = QLabel()
        self.analysis_value_label.setWordWrap(True)
        form.addRow(self.tr("Analysis"), self.analysis_value_label)
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText(self.tr("e.g. long intro, mix out on the break"))
        self.note_edit.setToolTip(
            self.tr("Shown in Stage Mode when this track is in your set. Kept in this app, never in the file.")
        )
        self.note_edit.editingFinished.connect(self.save_track_note)
        form.addRow(self.tr("Stage note"), self.note_edit)
        box.addLayout(form)

        self.accept_suggestion_button = QPushButton(self.tr("Confirm suggested category"))
        self.accept_suggestion_button.setToolTip(
            self.tr(
                "Records this track's genre tag as an alias of the suggested category, so every "
                "track with that genre resolves to it from now on. Never applied automatically."
            )
        )
        self.accept_suggestion_button.clicked.connect(self.confirm_category_suggestion)
        box.addWidget(self.accept_suggestion_button)
        self.accept_all_suggestions_button = QPushButton(self.tr("Confirm all suggestions"))
        self.accept_all_suggestions_button.setToolTip(
            self.tr(
                "Confirms every suggested category among the tracks shown in the table (narrow them "
                "with the filters first if needed): each genre becomes an alias of its suggested "
                "category. Lists them and asks before applying."
            )
        )
        self.accept_all_suggestions_button.clicked.connect(self._on_confirm_all_suggestions_clicked)
        box.addWidget(self.accept_all_suggestions_button)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton(self.tr("Write tags"))
        self.apply_button.setToolTip(
            self.tr("Writes only the changed fields into the file. Serato/Traktor data is preserved.")
        )
        self.apply_button.clicked.connect(self.apply_track_edits)
        self.revert_button = QPushButton(self.tr("Revert"))
        self.revert_button.clicked.connect(lambda: self._update_track_panel(self._current_row()))
        undo_button = QPushButton(self.tr("Undo"))
        redo_button = QPushButton(self.tr("Redo"))
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

        self.write_selection_button = QPushButton(self.tr("Write tags to selection…"))
        self.write_selection_button.setToolTip(
            self.tr(
                "Choose which tag(s) to copy from the fields above onto every selected track, "
                "as one undoable step. Serato/Traktor data is preserved."
            )
        )
        self.write_selection_button.clicked.connect(self._on_write_selection_clicked)
        box.addWidget(self.write_selection_button)
        self.apply_analysis_button = QPushButton(self.tr("Apply analysis suggestions…"))
        self.apply_analysis_button.setToolTip(
            self.tr(
                "Writes the estimated BPM/key of the selected tracks into their empty tags, after "
                "listing them, as one undoable step. Tags already set are never overwritten."
            )
        )
        self.apply_analysis_button.clicked.connect(self._on_apply_analysis_clicked)
        box.addWidget(self.apply_analysis_button)
        self.rename_files_button = QPushButton(self.tr("Rename files…"))
        self.rename_files_button.setToolTip(
            self.tr(
                "Renames the selected files from their tags (e.g. {artist} - {title}) inside their "
                "folder, after a preview, as one undoable step. DJ software will need relinking."
            )
        )
        self.rename_files_button.clicked.connect(self._on_rename_files_clicked)
        box.addWidget(self.rename_files_button)
        self.table.selectionModel().selectionChanged.connect(self._update_selection_actions)

        self.clean_button = QPushButton(self.tr("Clean noise frames…"))
        self.clean_button.setToolTip(
            self.tr(
                "Lists leftover junk tags (ID3v1 comment mirrors, old player preferences, ReplayGain…) "
                "and removes them only after you confirm."
            )
        )
        self.clean_button.clicked.connect(self._on_clean_clicked)
        box.addWidget(self.clean_button)
        box.addStretch(1)
        return panel

    def _build_cover_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.cover_label.setWordWrap(True)
        row.addWidget(self.cover_label)
        buttons = QVBoxLayout()
        self.set_cover_button = QPushButton(self.tr("Set cover…"))
        self.set_cover_button.setToolTip(
            self.tr(
                "Embeds a JPEG or PNG image as the track's front cover (undoable). Only the "
                "cover picture changes: other tags and Serato/Traktor data are preserved."
            )
        )
        self.set_cover_button.clicked.connect(self._on_set_cover_clicked)
        self.remove_cover_button = QPushButton(self.tr("Remove cover"))
        self.remove_cover_button.setToolTip(self.tr("Removes the embedded front cover (undoable)."))
        self.remove_cover_button.clicked.connect(self.remove_cover)
        buttons.addWidget(self.set_cover_button)
        buttons.addWidget(self.remove_cover_button)
        buttons.addStretch(1)
        row.addLayout(buttons)
        row.addStretch(1)
        return row

    def _build_categories_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.addLayout(help_row(self, *help_texts.LIBRARY_CATEGORIES))
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderLabels([self.tr("Category"), self.tr("Tracks"), self.tr("Aliases")])
        self.category_tree.setColumnWidth(0, 160)
        box.addWidget(self.category_tree, 1)
        grid = QGridLayout()
        self.new_category_button = QPushButton(self.tr("New…"))
        self.alias_button = QPushButton(self.tr("Add alias…"))
        self.rename_category_button = QPushButton(self.tr("Rename…"))
        self.merge_button = QPushButton(self.tr("Merge into…"))
        self.delete_category_button = QPushButton(self.tr("Delete"))
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
        box.addWidget(QLabel(self.tr("Tracks in playlist")))
        box.addWidget(self.playlist_tracks, 1)
        grid = QGridLayout()
        specs: list[tuple[str, str, Callable[[], None], str]] = [
            ("new_playlist_button", self.tr("New from selection"), self._on_new_playlist_clicked,
             self.tr("Creates a playlist from the rows selected in the table.")),
            ("generate_button", self.tr("Auto: sort visible"), self._on_generate_clicked,
             self.tr("Every visible row, grouped by category, then BPM range, then key.")),
            ("match_button", self.tr("Auto: match current"), self._on_match_clicked,
             self.tr("The current track followed by every visible track compatible in BPM and key.")),
            ("path_button", self.tr("Auto: mix path…"), self._on_path_clicked,
             self.tr("Every visible track ordered as a mixable path (each step compatible in BPM and key, "
                     "BPM rising, falling or flat), from the current track. Tracks that don't fit go to "
                     "a separate leftovers playlist.")),
            ("new_smart_button", self.tr("New smart playlist…"), self._on_new_smart_clicked,
             self.tr("A saved set of rules (category, BPM range, key, not played for…) re-evaluated against "
                     "the whole library after every scan and on demand.")),
            ("edit_smart_button", self.tr("Edit smart rules…"), self._on_edit_smart_clicked,
             self.tr("Changes the rules of the selected smart playlist and re-evaluates it.")),
            ("refresh_smart_button", self.tr("Refresh smart playlists"), self._on_refresh_smart_clicked,
             self.tr("Re-evaluates every smart playlist against the current library and play history.")),
            ("export_smart_button", self.tr("Export all smart…"), self._on_export_smart_clicked,
             self.tr("Re-evaluates every smart playlist and writes each as a Serato crate and/or Traktor "
                     "playlist into one folder, in one go.")),
            ("import_serato_button", self.tr("Import Serato crate…"), self._on_import_serato_clicked, ""),
            ("import_traktor_button", self.tr("Import Traktor NML…"), self._on_import_traktor_clicked, ""),
            ("import_rekordbox_button", self.tr("Import Rekordbox export…"), self._on_import_rekordbox_clicked, ""),
            ("export_serato_button", self.tr("Export as Serato crate…"), self._on_export_serato_clicked,
             self.tr("Writes a new .crate file where you choose. Never overwrites a crate on its own.")),
            ("export_traktor_button", self.tr("Export as Traktor playlist…"), self._on_export_traktor_clicked,
             self.tr("Writes a new single-playlist .nml where you choose, for Traktor's Import Playlist. "
                     "Never touches collection.nml.")),
            ("compare_serato_button", self.tr("Compare with crate…"), self._on_compare_serato_clicked,
             self.tr("Compares the selected playlist with a Serato crate: tracks only on each side and "
                     "order differences. Read-only.")),
            ("compare_traktor_button", self.tr("Compare with Traktor…"), self._on_compare_traktor_clicked,
             self.tr("Compares the selected playlist with a playlist of a Traktor .nml: tracks only on "
                     "each side and order differences. Read-only.")),
            ("rename_playlist_button", self.tr("Rename…"), self._on_rename_playlist_clicked, ""),
            ("delete_playlist_button", self.tr("Delete"), self._on_delete_playlist_clicked, ""),
        ]
        for index, (attr, label, handler, tip) in enumerate(specs):
            button = QPushButton(label)
            if tip:
                button.setToolTip(tip)
            button.clicked.connect(handler)
            setattr(self, attr, button)
            # Two columns: three made this panel ~690 px wide, wider than the
            # side panel, so its third column sat off the right edge (issue #19).
            grid.addWidget(button, index // 2, index % 2)
        box.addLayout(grid)
        return panel

    def _build_history_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.addLayout(help_row(self, *help_texts.LIBRARY_HISTORY))
        grid = QGridLayout()
        self.load_history_button = QPushButton(self.tr("Load DJ history"))
        self.load_history_button.setToolTip(
            self.tr(
                "Reads Serato (~/Music/_Serato_/History) and Traktor (~/Music/_Traktor/History) history. Read-only."
            )
        )
        self.load_history_button.clicked.connect(self._on_load_history_clicked)
        self.history_folder_button = QPushButton(self.tr("Load from folder…"))
        self.history_folder_button.setToolTip(self.tr("A Serato History/Sessions folder or a Traktor History folder."))
        self.history_folder_button.clicked.connect(self._on_history_folder_clicked)
        self.select_never_played_button = QPushButton(self.tr("Select never played"))
        self.select_never_played_button.setToolTip(self.tr("Selects, in the table, the visible tracks never played."))
        self.select_never_played_button.clicked.connect(self.select_never_played)
        self.select_never_played_button.setEnabled(False)
        grid.addWidget(self.load_history_button, 0, 0)
        grid.addWidget(self.history_folder_button, 0, 1)
        grid.addWidget(self.select_never_played_button, 1, 0)
        box.addLayout(grid)
        self.history_summary = QLabel(self.tr("No history loaded."))
        self.history_summary.setWordWrap(True)
        box.addWidget(self.history_summary)
        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderLabels([self.tr("When"), self.tr("Track"), self.tr("Deck")])
        self.history_tree.itemDoubleClicked.connect(self._on_history_item_activated)
        box.addWidget(self.history_tree, 1)
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
        self.audio_preview.stop()
        self._stop_job()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        if self.history_dialog is not None:
            # It holds the connection about to close.
            self.history_dialog.close()
            self.history_dialog.deleteLater()
            self.history_dialog = None
        if self._db is not None:
            self._db.close()
            self._db = None

    def hideEvent(self, event) -> None:
        # Leaving the tab stops the preview; minimizing the window (a
        # spontaneous hide) lets it play on.
        if not event.spontaneous():
            self.audio_preview.stop()
        super().hideEvent(event)

    def _preview_current_row(self, current: QModelIndex, _previous: QModelIndex) -> None:
        row = current.data(ROW_ROLE) if current.isValid() else None
        self.audio_preview.set_source(row.path if row is not None and not row.missing else None)

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.table
            and event.type() == QEvent.Type.KeyPress
            and self.audio_preview.handle_key(event.key(), event.modifiers())
        ):
            return True
        return super().eventFilter(watched, event)

    def _advance_preview(self) -> bool:
        """Select and play the next playable row below the current one (issue #210)."""
        current = self.table.selectionModel().currentIndex()
        start = current.row() + 1 if current.isValid() else 0
        for proxy_row in range(start, self.proxy.rowCount()):
            index = self.proxy.index(proxy_row, 0)
            row = index.data(ROW_ROLE)
            if row is None or row.missing:
                continue
            self.table.selectionModel().setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
            )
            self.table.scrollTo(index)
            self.audio_preview.play()
            return True
        return False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        try:
            self.ensure_open()
        except Exception:
            _LOGGER.exception("Could not open the music library index")
            self.status_label.setText(self.tr("Could not open the music library index (see the log)."))

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
        self.set_panel.set_rows(self.table_model.rows())
        self._refresh_category_filter()
        self._refresh_value_filters(self.table_model.rows())
        if current is not None:
            self.select_path(current)
        self._update_count_label()
        if self._history_sessions:
            self._update_history_summary()
        # Per-category track counts follow the rows.
        self._reload_categories()

    # --- folders & scanning ---------------------------------------------

    def add_root(self, path: str | Path) -> None:
        self.db.add_root(Path(path))
        self.reload()

    def _on_add_root_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, self.tr("Add music folder"))
        if directory:
            self.add_root(directory)

    def _on_remove_root_clicked(self) -> None:
        item = self.roots_list.currentItem()
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            self.tr("Remove music folder"),
            self.tr("Stop indexing {folder}?\n\nOnly this app's index is cleared -- no file is touched.").format(
                folder=item.text()
            ),
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
            self.status_label.setText(self.tr("Add a music folder first."))
            return
        self._start_job(self._scan_job([root.path for root in roots]))

    def _scan_job(self, root_paths: list[str]) -> Generator[None]:
        totals = {"added": 0, "updated": 0, "unchanged": 0, "missing": 0}
        self.progress_bar.setRange(0, 0)
        for root_path in root_paths:
            if not Path(root_path).is_dir():
                self.status_label.setText(self.tr("Skipping unavailable folder: {folder}").format(folder=root_path))
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
                    self.status_label.setText(self.tr("Scanning {folder}… {count} files").format(folder=root_path, count=count))
                yield
        pending = len(self.db.tracks_needing_metadata())
        self.progress_bar.setRange(0, max(pending, 1))
        for count in workspace.iter_refresh_metadata(self.db):
            self.progress_bar.setValue(count)
            if count % 50 == 0:
                self.status_label.setText(self.tr("Reading tags… {count}/{total}").format(count=count, total=pending))
            yield
        self.status_label.setText(
            self.tr("Scan done: {added} new, {updated} changed, {unchanged} unchanged, {missing} missing.").format(
                **totals
            )
            + self.tr(" Tags read for {count} file(s).").format(count=pending)
        )
        self._reload_rows()
        # Issue #259: smart playlists follow the freshly scanned library.
        refreshed = self.refresh_smart_playlists()
        if refreshed:
            self.status_label.setText(
                self.status_label.text() + self.tr(" {count} smart playlist(s) refreshed.").format(count=len(refreshed))
            )

    def find_duplicates(self) -> None:
        """Start the duplicate search over the indexed, present tracks."""
        if self.is_busy():
            return
        if not self.db.list_tracks(include_missing=False):
            self.status_label.setText(self.tr("Scan a music folder first."))
            return
        self._start_job(self._duplicates_job())

    def _duplicates_job(self) -> Generator[None]:
        # Metadata tier: tag cache only, instant even on a large library.
        entries = duplicates.metadata_entries(self.db)
        groups = duplicates.find_metadata_duplicates(entries)
        # Same song, other version (issue #257): suggestions, listed apart.
        versions = duplicates.find_version_variants(entries)
        sizes = duplicates.size_entries(self.db)
        total = duplicates.exact_candidate_count(sizes)
        self.progress_bar.setRange(0, max(total, 1))
        self.status_label.setText(self.tr("Comparing {total} file(s) of equal size…").format(total=total))
        yield
        steps = duplicates.iter_exact_duplicates(sizes)
        while True:
            try:
                done = next(steps)
            except StopIteration as finished:
                exact = finished.value
                break
            self.progress_bar.setValue(done)
            self.status_label.setText(self.tr("Comparing files of equal size… {done}/{total}").format(done=done, total=total))
            yield
        self.status_label.setText(
            self.tr(
                "Duplicates: {exact} group(s) of identical files, {groups} group(s) sharing artist + title, "
                "{versions} song(s) with other versions."
            ).format(exact=len(exact), groups=len(groups), versions=len(versions))
        )
        self._show_duplicates(exact + groups + versions)

    def _show_duplicates(self, groups: list[duplicates.DuplicateGroup]) -> None:
        if self.duplicates_dialog is not None:
            self.duplicates_dialog.close()
            self.duplicates_dialog.deleteLater()
        self.duplicates_dialog = DuplicatesDialog(groups, self)
        self.duplicates_dialog.discardRequested.connect(self.discard_duplicates)
        self.duplicates_dialog.show()

    def discard_duplicates(self, paths: list[str]) -> None:
        """Move ticked duplicate copies to the Trash (issue #208).

        Refuses outright when a group would keep no copy; otherwise confirms
        with the full list, moves each copy with `trash_file`
        (`QFile.moveToTrash`, never a hard delete), flags it missing in the
        index, then offers to point this app's playlists at the kept copy."""
        dialog = self.duplicates_dialog
        parent = dialog if dialog is not None else self
        plan = discard.plan_discard(dialog.groups if dialog is not None else [], paths)
        if plan.refused:
            names = "\n".join(f"• {_group_name(group)}" for group in plan.refused[:_LIST_LIMIT])
            QMessageBox.warning(
                parent,
                self.tr("Move to Trash"),
                self.tr("Every copy of these groups is ticked -- untick at least one copy to keep in each:")
                + "\n\n"
                + names,
            )
            return
        if not plan.discards:
            return
        answer = QMessageBox.question(
            parent,
            self.tr("Move to Trash"),
            self.tr("Move {count} file(s) to the Trash?").format(count=len(plan.discards))
            + "\n\n"
            + _bullet_list(
                path + "\n    " + self.tr("keeps {kept}").format(kept=kept) for path, kept in plan.discards
            )
            + "\n\n"
            + self.tr("You can put them back from the Trash. They are flagged missing in this app's index."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = discard.move_to_trash(self.db, plan, trash_file)
        change_log.record_trash(self.db, result.moved, result.trash_paths)
        message = self.tr("Moved {count} duplicate(s) to the Trash.").format(count=len(result.moved))
        referenced = discard.playlists_referencing(self.db, result.moved)
        if referenced:
            names = sorted({name for playlist_names in referenced.values() for name in playlist_names})
            answer = QMessageBox.question(
                parent,
                self.tr("Update playlists"),
                self.tr("{count} discarded copy(ies) are in this app's playlists:").format(count=len(referenced))
                + "\n\n"
                + _bullet_list(names)
                + "\n\n"
                + self.tr(
                    "Point those playlists at the kept copy instead? "
                    "(Serato, Traktor and Rekordbox files are not changed.)"
                ),
            )
            if answer == QMessageBox.StandardButton.Yes:
                repointed = discard.repoint_playlists(self.db, result.moved)
                message += self.tr(" Playlists now use the kept copy for {count} of them.").format(count=repointed)
        if result.failed:
            message += self.tr(" {count} could not be moved.").format(count=len(result.failed))
            QMessageBox.warning(
                parent,
                self.tr("Move to Trash"),
                self.tr("These files were left where they are:")
                + "\n\n"
                + _bullet_list(f"{path}: {reason}" for path, reason in result.failed),
            )
        if dialog is not None:
            dialog.remove_paths([path for path, _kept in result.moved])
        self.status_label.setText(message)
        self._reload_rows()
        self._reload_playlists()

    # --- change history (issue #261) ---------------------------------------

    def _record_tag_change(self, summary: str, changes: dict[str, tuple[dict[str, object], dict[str, object]]]) -> None:
        change_log.record_tag_changes(self.db, changes, summary)

    def _record_cover_change(self, summary: str, path: str, old: object | None, new: object | None) -> None:
        change_log.record_cover_change(self.db, path, old, new, summary)

    def _record_renames(self, summary: str, pairs: list[tuple[str, str]]) -> None:
        change_log.record_renames(self.db, pairs, summary)

    def show_change_history(self) -> ChangeHistoryDialog:
        """Open (or raise) the persistent change history window."""
        if self.history_dialog is None:
            self.history_dialog = ChangeHistoryDialog(self.db, self)
            self.history_dialog.reverted.connect(self._on_changes_reverted)
        else:
            self.history_dialog.refresh()
        self.history_dialog.show()
        self.history_dialog.raise_()
        return self.history_dialog

    def _on_changes_reverted(self, paths: list[str]) -> None:
        for path in paths:
            if Path(path).is_file():
                workspace.refresh_track_metadata(self.db, path)
        self._reload_rows()
        self._reload_playlists()
        if self._current_path in paths:
            # A reverted cover leaves the row's tags as they were.
            self._show_cover(self._current_row())
        self.status_label.setText(self.tr("Change reverted on {count} file(s).").format(count=len(paths)))

    # --- health report (issue #225) ----------------------------------------

    def start_health_report(self) -> None:
        """Check every indexed, present track, then show the report."""
        if self.is_busy():
            return
        entries = health.health_entries(self.db)
        if not entries:
            self.status_label.setText(self.tr("Scan a music folder first."))
            return
        self._start_job(self._health_job(entries))

    def _health_job(self, entries: list[tuple[str, int | None]]) -> Generator[None]:
        total = len(entries)
        self.progress_bar.setRange(0, total)
        steps = health.iter_health_check(entries)
        while True:
            try:
                done = next(steps)
            except StopIteration as finished:
                report = finished.value
                break
            self.progress_bar.setValue(done)
            if done % 50 == 0:
                self.status_label.setText(self.tr("Checking files… {done}/{total}").format(done=done, total=total))
            yield
        self.status_label.setText(
            self.tr("Health report: {affected} of {checked} file(s) with at least one issue.").format(
                affected=report.affected_files, checked=report.checked
            )
        )
        self._show_health_report(report)

    def _show_health_report(self, report: health.HealthReport) -> None:
        if self.health_dialog is not None:
            self.health_dialog.close()
            self.health_dialog.deleteLater()
        self.health_dialog = HealthReportDialog(report, self)
        self.health_dialog.showTrackRequested.connect(self.show_track)
        self.health_dialog.show()

    # --- statistics (issue #258) -------------------------------------------

    def compute_statistics(self) -> stats.LibraryStats:
        """Statistics of the rows the table shows (filters apply), with play
        counts when DJ history is loaded."""
        mtimes = {track.path: track.mtime for track in self.db.list_tracks()}
        plays = history.summarize_plays(self._history_sessions) if self._history_sessions else None
        return stats.compute_library_stats(self.visible_rows(), mtimes, plays)

    def show_statistics(self) -> None:
        if self.table_model.rowCount() == 0:
            self.status_label.setText(self.tr("Scan a music folder first."))
            return
        shown, total = self.proxy.rowCount(), self.table_model.rowCount()
        scope = (
            self.tr("all indexed tracks")
            if shown == total
            else self.tr("the {shown} of {total} tracks the filters show").format(shown=shown, total=total)
        )
        if self.stats_dialog is not None:
            self.stats_dialog.close()
            self.stats_dialog.deleteLater()
        self.stats_dialog = LibraryStatsDialog(self.compute_statistics(), scope, self)
        self.stats_dialog.showTrackRequested.connect(self.show_track)
        self.stats_dialog.show()

    def show_track(self, path: str) -> bool:
        """Select `path` in the table, clearing the filters if they hide it."""
        if not self.select_path(path):
            self.reset_filters()
            if not self.select_path(path):
                self.status_label.setText(self.tr("Not in the library table: {path}").format(path=path))
                return False
        self.table.scrollTo(self.table.currentIndex())
        return True
    # --- background BPM/key analysis (issue #224) ----------------------

    def is_analysing(self) -> bool:
        return self._job is not None and self._analysing

    def _on_analyse_clicked(self) -> None:
        if self.is_analysing():
            self.stop_analysis()
        else:
            self.start_analysis()

    def start_analysis(self, analyser: workspace.Analyser | None = None) -> None:
        """Estimate BPM/key for tracks missing them, one track per timer
        slice. `analyser` replaces the librosa one (tests)."""
        if self.is_busy():
            return
        if analyser is None and not analysis_available():
            self.status_label.setText(self.tr(_ANALYSIS_UNAVAILABLE))
            return
        pending = len(self.db.tracks_needing_analysis())
        if not pending:
            self.status_label.setText(self.tr("Every track has a BPM and a key tag (or was analysed already)."))
            return
        self._analysing = True
        self._start_job(self._analysis_job(pending, analyser))
        self.analyse_button.setText(self.tr(_STOP_ANALYSIS_LABEL))
        self.analyse_button.setEnabled(True)

    def stop_analysis(self) -> None:
        """Stop after the current track; estimates found so far are kept."""
        if not self.is_analysing():
            return
        self._stop_job()
        self.status_label.setText(self.tr("Analysis stopped. Estimates found so far are kept."))
        self._reload_rows()

    def _analysis_job(self, pending: int, analyser: workspace.Analyser | None) -> Generator[None]:
        """Each track's audio is decoded and analysed on a worker thread
        (a 60 s clip takes seconds); this generator only hands the next track
        over, checks whether the result is in at every timer slice, and
        records it -- the database stays on the GUI thread. The window keeps
        responding the whole time."""
        self.progress_bar.setRange(0, pending)
        self.progress_bar.setValue(0)  # not the previous job's last value
        self.status_label.setText(self.tr("Analysing audio… {count}/{total}").format(count=0, total=pending))
        yield
        executor = self._analysis_executor()
        found = 0
        targets = workspace.analysis_targets(self.db)
        for index, target in enumerate(targets, start=1):
            future = executor.submit(workspace.run_analyser, target, analyser)
            self._analysis_future = future
            while not future.done():
                yield
            self._analysis_future = None
            if workspace.record_analysis(self.db, target, future.result()):
                found += 1
            self.progress_bar.setValue(index)
            self.status_label.setText(
                self.tr("Analysing audio… {count}/{total}").format(count=index, total=len(targets))
            )
            yield
        self.status_label.setText(
            self.tr(
                "Analysis done: estimates for {found} of {total} track(s), shown in amber. "
                "Select tracks and use Apply analysis suggestions… to write them."
            ).format(found=found, total=len(targets))
        )
        self._reload_rows()

    def _analysis_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="djmidi-analysis")
        return self._executor

    def _drop_analysis_future(self) -> None:
        """A stopped analysis can't interrupt the clip being decoded; its
        result is simply never recorded."""
        if self._analysis_future is not None:
            self._analysis_future.cancel()
            self._analysis_future = None

    def _start_job(self, job: Generator[None]) -> None:
        self._job = job
        self.scan_button.setEnabled(False)
        self.relink_button.setEnabled(False)
        self.duplicates_button.setEnabled(False)
        self.health_button.setEnabled(False)
        self.analyse_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._job_timer.start()

    def _stop_job(self) -> None:
        self._job_timer.stop()
        self._job = None
        self._drop_analysis_future()
        self._analysing = False
        self.scan_button.setEnabled(True)
        self.relink_button.setEnabled(True)
        self.duplicates_button.setEnabled(True)
        self.health_button.setEnabled(True)
        self.analyse_button.setText(self.tr(_ANALYSE_LABEL))
        self.analyse_button.setEnabled(analysis_available())
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
            self.status_label.setText(self.tr("The scan, duplicate search or health check failed (see the log)."))
            self._stop_job()

    # --- relinking missing tracks (issue #190) ---------------------------

    def start_relink_search(self) -> None:
        """Search the roots for missing tracks' new paths, then review them."""
        if self.is_busy():
            return
        self._start_job(self._relink_job())

    def _relink_job(self) -> Generator[None]:
        self.progress_bar.setRange(0, 0)
        steps = relink.iter_relink_proposals(self.db)
        while True:
            try:
                count = next(steps)
            except StopIteration as done:
                proposals = done.value
                break
            self.status_label.setText(self.tr("Looking for moved files… {count} checked").format(count=count))
            yield
        if not proposals:
            self.status_label.setText(self.tr("No missing tracks to relink."))
            return
        found = sum(1 for proposal in proposals if proposal.candidates)
        self.status_label.setText(
            self.tr("{count} missing track(s), {found} with a possible new location.").format(
                count=len(proposals), found=found
            )
        )
        # Opened once the job has stopped: a modal dialog inside a timer
        # slice would re-enter this generator.
        QTimer.singleShot(0, lambda: self.review_relinks(proposals))

    def review_relinks(self, proposals: list[RelinkProposal]) -> None:
        dialog = RelinkDialog(proposals, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        choices = dialog.choices()
        if not choices:
            return
        answer = QMessageBox.question(
            self,
            self.tr("Relink missing tracks"),
            self.tr(
                "Relink {count} track(s) in this app's index?\n\n"
                "Playlists and cached tags follow the new paths and the stale entries are dropped. "
                "No audio file or DJ software library is modified. This can't be undone."
            ).format(count=len(choices)),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = relink.apply_relinks(self.db, choices)
        message = self.tr("Relinked {count} track(s).").format(count=result.relinked)
        if result.skipped:
            message += self.tr(" Skipped {count} whose file is gone or outside the music folders.").format(
                count=len(result.skipped)
            )
        self.status_label.setText(message)
        self._reload_rows()
        self._reload_playlists()

    def run_pending_job(self) -> None:
        """Drain the current job synchronously (tests, scripted use)."""
        while self._job is not None:
            self._run_job_slice()

    # --- table ------------------------------------------------------------

    def _on_filter_changed(self, text: str) -> None:
        self.proxy.set_text_filter(text)
        self._update_count_label()

    def _on_category_filter_changed(self, text: str) -> None:
        if text:
            self.proxy.set_category_filter(self.category_filter.currentData() or text)
            self._update_count_label()

    def _refresh_category_filter(self) -> None:
        previous = self.category_filter.currentData() or ALL_CATEGORIES
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(self.tr(ALL_CATEGORIES), ALL_CATEGORIES)
        self.category_filter.addItem(self.tr(UNCATEGORIZED), UNCATEGORIZED)
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
        self._refill_combo(self.genre_filter, self.tr(ALL_GENRES), sorted(genres.values(), key=str.casefold))
        self._refill_combo(self.key_filter, self.tr(ALL_KEYS), sorted(keys.values(), key=str.casefold))
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
        self.proxy.set_text_filter("")
        self.proxy.set_category_filter(ALL_CATEGORIES)
        self.proxy.set_genre_filter(None)
        self.proxy.set_key_filter(None)
        self.proxy.set_bpm_range(None, None)
        self.proxy.set_camelot_filter(None)
        self._update_count_label()

    def _update_count_label(self, *_args: object) -> None:
        self.count_label.setText(
            self.tr("{shown} / {total} tracks").format(shown=self.proxy.rowCount(), total=self.table_model.rowCount())
        )
        self._update_all_suggestions_button()

    def pending_suggestions(self) -> dict[str, str]:
        """Genre -> suggested category for the visible tracks that have a
        suggestion (the pairs "Confirm all suggestions" would record)."""
        pairs: dict[str, str] = {}
        for row in self.visible_rows():
            if _can_confirm_suggestion(row):
                pairs.setdefault(row.metadata.genre.strip(), row.category_suggestion)
        return pairs

    def _update_all_suggestions_button(self) -> None:
        if not hasattr(self, "accept_all_suggestions_button"):
            return
        count = len(self.pending_suggestions())
        self.accept_all_suggestions_button.setEnabled(count > 0)
        self.accept_all_suggestions_button.setText(
            self.tr("Confirm all suggestions ({count})").format(count=count)
            if count
            else self.tr("Confirm all suggestions")
        )

    def confirm_all_suggestions(self) -> int:
        """Record every pending genre -> suggested category pair as an alias;
        returns how many were recorded. One table reload at the end."""
        recorded = 0
        for genre, category in self.pending_suggestions().items():
            try:
                workspace.add_category_alias(self.db, category, genre)
            except ValueError as exc:
                _LOGGER.warning("Could not confirm %r as an alias of %s: %s", genre, category, exc)
                continue
            recorded += 1
        if recorded:
            self._reload_rows()
        self.status_label.setText(self.tr("Confirmed {count} suggested category(ies).").format(count=recorded))
        return recorded

    def _on_confirm_all_suggestions_clicked(self) -> None:
        pairs = self.pending_suggestions()
        if not pairs:
            return
        lines = [f"“{genre}” → {category_label(category)}" for genre, category in sorted(pairs.items())]
        shown = "\n".join(lines[:20]) + (
            "\n" + self.tr("… and {count} more").format(count=len(lines) - 20) if len(lines) > 20 else ""
        )
        answer = QMessageBox.question(
            self,
            self.tr("Confirm all suggestions"),
            self.tr("Each genre below becomes an alias of its suggested category, for every track with that genre:")
            + "\n\n"
            + shown,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.confirm_all_suggestions()

    def visible_rows(self) -> list[workspace.LibraryRow]:
        # The proxy only filters (the model sorts), so with no filter its
        # rows are the model's, in the same order.
        if not self.proxy.is_filtering():
            return self.table_model.rows()
        rows = self.table_model._rows
        return [rows[self.proxy.mapToSource(self.proxy.index(r, 0)).row()] for r in range(self.proxy.rowCount())]

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
        self._show_cover(row)
        self.note_edit.setText((row.note or "") if row is not None else "")
        self.note_edit.setEnabled(row is not None)
        if row is None:
            self.track_path_label.setText(self.tr("Select a track in the table."))
            self.camelot_label.setText("")
            self.category_value_label.setText("")
            self.analysis_value_label.setText("")
            self.accept_suggestion_button.setEnabled(False)
            return
        self.track_path_label.setText(row.path + (self.tr("  (missing on disk)") if row.missing else ""))
        self.camelot_label.setText(row.camelot_key or "—")
        self.category_value_label.setText(self._category_text(row))
        self.analysis_value_label.setText(_analysis_text(row))
        self.accept_suggestion_button.setEnabled(_can_confirm_suggestion(row))

    def save_track_note(self, text: str | None = None) -> bool:
        """Stores the current track's stage note (phase 6 item 3). Only that
        row is refreshed -- reloading a large collection per note would lag."""
        row = self._current_row()
        if row is None or self._db is None:
            return False
        note = (self.note_edit.text() if text is None else text).strip() or None
        if note == row.note:
            return False
        self.db.set_track_note(row.track_id, note or "")
        updated = replace(row, note=note)
        self.table_model.replace_row(row, updated)
        self.set_panel.update_row(updated)
        self.status_label.setText(
            self.tr("Stage note saved.") if note else self.tr("Stage note removed.")
        )
        return True

    # --- cover art (issue #256) --------------------------------------------

    def _show_cover(self, row: workspace.LibraryRow | None) -> None:
        cover = None
        if row is not None and not row.missing:
            try:
                cover = read_cover_art(row.path)
            except Exception:
                _LOGGER.warning("Could not read the cover of %s", row.path, exc_info=True)
        pixmap = QPixmap()
        if cover is not None and pixmap.loadFromData(cover.data):
            self.cover_label.setPixmap(
                pixmap.scaled(
                    _COVER_SIZE,
                    _COVER_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.cover_label.setPixmap(QPixmap())
            self.cover_label.setText("" if row is None else (self.tr("Unreadable cover") if cover else self.tr("No cover")))
        self._has_cover = cover is not None
        editable = row is not None and not row.missing
        self.set_cover_button.setEnabled(editable)
        self.remove_cover_button.setEnabled(editable and self._has_cover)

    def _on_set_cover_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose cover image"), "", self.tr("Images (*.jpg *.jpeg *.png)")
        )
        if path:
            self.set_cover_from_file(path)

    def set_cover_from_file(self, image_path: str) -> bool:
        row = self._current_row()
        if row is None or row.missing:
            return False
        try:
            cover = load_cover_file(image_path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, self.tr("Unsupported image"), str(exc))
            return False
        return self._push_cover(row.path, cover)

    def remove_cover(self) -> bool:
        row = self._current_row()
        if row is None or row.missing:
            return False
        return self._push_cover(row.path, None)

    def _push_cover(self, path: str, cover: object | None) -> bool:
        try:
            self.undo_stack.push(WriteTrackCoverCommand(path, cover, self._on_cover_written, recorder=self._record_cover_change))
        except Exception as exc:
            _LOGGER.exception("Cover write failed for %s", path)
            QMessageBox.warning(self, self.tr("Could not write the cover"), f"{path}\n\n{exc}")
            return False
        return True

    def _on_cover_written(self, path: str) -> None:
        # Only the picture changed: refresh the preview, not the whole table.
        if path == self._current_path:
            self._show_cover(self._current_row())
        self.status_label.setText(self.tr("Cover updated: {name}").format(name=Path(path).name))

    def _writable_selection(self) -> list[workspace.LibraryRow]:
        return [row for row in self.selected_rows() if not row.missing]

    def _update_selection_actions(self, *_args: object) -> None:
        writable = self._writable_selection()
        self.write_selection_button.setEnabled(bool(writable))
        self.rename_files_button.setEnabled(bool(writable))
        self.apply_analysis_button.setEnabled(any(row.has_analysis_suggestion for row in writable))

    @staticmethod
    def _category_text(row: workspace.LibraryRow) -> str:
        if row.category:
            return category_label(row.category)
        if row.category_suggestion:
            return QCoreApplication.translate("MusicLibraryView", "Suggested: {category}").format(
                category=category_label(row.category_suggestion)
            )
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
            QMessageBox.warning(self, self.tr("Invalid BPM"), self.tr("BPM must be a number, e.g. 174 or 128.5."))
            return False
        if not changes:
            self.status_label.setText(self.tr("No tag changes to write."))
            return False
        metadata = row.metadata or TrackMetadata()
        old_values = {name: getattr(metadata, name) for name in changes}
        try:
            self.undo_stack.push(WriteTrackMetadataCommand(row.path, old_values, changes, self._on_track_written, recorder=self._record_tag_change))
        except Exception as exc:
            _LOGGER.exception("Tag write failed for %s", row.path)
            QMessageBox.warning(self, self.tr("Could not write tags"), f"{row.path}\n\n{exc}")
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
            self.status_label.setText(self.tr("Selected tracks already have these tags."))
            return 0
        return self._push_bulk_write(changes)

    def _push_bulk_write(self, changes: dict[str, tuple[dict[str, object], dict[str, object]]]) -> int:
        command = WriteTracksMetadataCommand(
            changes,
            self._on_tracks_written,
            progress_factory=self._tag_write_progress,
            recorder=self._record_tag_change,
        )
        self.undo_stack.push(command)
        if command.cancelled:
            self.status_label.setText(
                self.tr(
                    "Stopped: tags written to {written} of {total} track(s). Undo restores the ones already written."
                ).format(written=len(command.written), total=len(changes))
            )
        if command.failures:
            _LOGGER.warning("Tag write failed for %d file(s): %s", len(command.failures), command.failures)
            details = "\n".join(f"{Path(path).name}: {error}" for path, error in list(command.failures.items())[:20])
            QMessageBox.warning(
                self,
                self.tr("Some tags could not be written"),
                self.tr("{written} track(s) written, {failed} failed:").format(
                    written=len(command.written), failed=len(command.failures)
                )
                + "\n\n"
                + details,
            )
        return len(command.written)

    def _on_apply_analysis_clicked(self) -> None:
        changes = workspace.analysis_tag_changes(self._writable_selection())
        if not changes:
            return
        lines = [
            f"{Path(path).name}: " + ", ".join(f"{_field_label(name)} {_field_text(name, value)}" for name, value in new.items())
            for path, (_old, new) in changes.items()
        ]
        answer = QMessageBox.question(
            self,
            self.tr("Apply analysis suggestions"),
            self.tr(
                "Write the estimated BPM/key into {count} track(s)? Only empty tags are filled; "
                "Undo writes them back empty."
            ).format(count=len(changes))
            + "\n\n"
            + _bullet_list(lines),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.apply_analysis_suggestions()

    def apply_analysis_suggestions(self) -> int:
        """Write the selected tracks' audio-analysis estimates into their
        empty BPM/key tags as one undo step (no confirmation -- the button
        asks first). Returns the number of files written."""
        changes = workspace.analysis_tag_changes(self._writable_selection())
        if not changes:
            return 0
        return self._push_bulk_write(changes)

    # --- file renaming (issue #260) ---------------------------------------

    def _on_rename_files_clicked(self) -> None:
        paths = [row.path for row in self._writable_selection()]
        if not paths:
            return
        template = self.db.get_setting(_RENAME_TEMPLATE_SETTING, rename.DEFAULT_TEMPLATE)
        dialog = RenameFilesDialog(
            lambda text: rename.plan_from_db(self.db, paths, text),
            template if isinstance(template, str) else rename.DEFAULT_TEMPLATE,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.db.set_setting(_RENAME_TEMPLATE_SETTING, dialog.template)
        renamed = self.rename_files(dialog.renames())
        if renamed and dialog.save_csv:
            self._save_rename_csv(renamed)

    def rename_files(self, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Rename ``(old, new)`` files as one undo step (no confirmation --
        the dialog previewed them) and return the pairs actually renamed."""
        if not pairs:
            return []
        command = RenameFilesCommand(
            pairs,
            lambda batch: rename.apply_renames(self.db, batch),
            self._on_files_renamed,
            recorder=self._record_renames,
        )
        self.undo_stack.push(command)
        if command.failures:
            _LOGGER.warning("Rename failed for %d file(s): %s", len(command.failures), command.failures)
            QMessageBox.warning(
                self,
                self.tr("Some files were not renamed"),
                self.tr("{renamed} file(s) renamed, {failed} left as they were:").format(
                    renamed=len(command.renamed), failed=len(command.failures)
                )
                + "\n\n"
                + _bullet_list(f"{Path(path).name}: {reason}" for path, reason in command.failures),
            )
        return command.renamed

    def _on_files_renamed(self, pairs: list[tuple[str, str]]) -> None:
        moved = dict(pairs)
        selected = [moved.get(row.path, row.path) for row in self.selected_rows()]
        if self._current_path is not None:
            self._current_path = moved.get(self._current_path, self._current_path)
        self._reload_rows()
        self._reload_playlists()
        self.select_paths(selected)
        self.status_label.setText(
            self.tr("Renamed {count} file(s). Serato, Traktor and Rekordbox need relinking to find them.").format(
                count=len(pairs)
            )
        )

    def _save_rename_csv(self, pairs: list[tuple[str, str]]) -> None:
        default = str(user_paths.subfolder(user_paths.EXPORTS) / "renamed-files.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save old → new paths"), default, self.tr("CSV files (*.csv)")
        )
        if not path:
            return
        try:
            count = rename.export_mapping_csv(path, pairs)
        except OSError as exc:
            QMessageBox.warning(
                self, self.tr("Save old → new paths"), self.tr("Could not write {path}:").format(path=path) + f"\n{exc}"
            )
            return
        self.status_label.setText(
            self.tr("Renamed {count} file(s); old → new paths saved to {path}").format(count=count, path=path)
        )

    def _tag_write_progress(self, label: str, total: int, cancellable: bool = True) -> Callable[[int, int], bool]:
        """A progress window for one pass of a bulk tag write (write, undo or
        redo): shown only if the pass lasts more than a moment, with a Cancel
        button. Returns the command's per-file callback; False means stop."""
        dialog = QProgressDialog(label, self.tr("Cancel") if cancellable else "", 0, max(total, 1), self)
        if not cancellable:
            dialog.setCancelButton(None)
        dialog.setWindowTitle(self.tr("Music Library"))
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
        progress = self._tag_write_progress(self.tr("Reading tags back…"), total, cancellable=False) if len(paths) > 1 else None
        for index, path in enumerate(paths):
            if progress is not None:
                progress(index, total)
            workspace.refresh_track_metadata(self.db, path)
        if progress is not None:
            progress(len(paths), total, self.tr("Refreshing the table…"))
        self._reload_rows()
        self.select_paths(selected)
        if progress is not None:
            progress(total, total)
        self.status_label.setText(self.tr("Tags written to {count} track(s).").format(count=len(paths)))

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
        self.status_label.setText(self.tr("Tags written: {name}").format(name=Path(path).name))

    def confirm_category_suggestion(self) -> None:
        row = self._current_row()
        if row is None or row.category_suggestion is None or row.metadata is None or not row.metadata.genre:
            return
        workspace.add_category_alias(self.db, row.category_suggestion, row.metadata.genre)
        self.status_label.setText(
            self.tr("“{genre}” is now an alias of {category}.").format(
                genre=row.metadata.genre, category=category_label(row.category_suggestion)
            )
        )
        self._reload_rows()

    def _on_clean_clicked(self) -> None:
        row = self._current_row()
        if row is None or row.missing:
            return
        try:
            found = clean_noise_frames(row.path, dry_run=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, self.tr("Could not read tags"), f"{row.path}\n\n{exc}")
            return
        if not found:
            QMessageBox.information(self, self.tr("Clean noise frames"), self.tr("No noise frames found in this file."))
            return
        answer = QMessageBox.question(
            self,
            self.tr("Clean noise frames"),
            self.tr("Remove these frames?")
            + "\n\n"
            + "\n".join(found)
            + "\n\n"
            + self.tr("Serato/Traktor data is never touched."),
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
            QMessageBox.warning(self, self.tr("Categories"), str(exc))
            return
        self._after_category_change(message)

    def _on_new_category_clicked(self) -> None:
        families = taxonomy.families()
        family, ok = QInputDialog.getItem(self, self.tr("New category"), self.tr("Family:"), families, 0, True)
        if not ok or not family.strip():
            return
        name, ok = QInputDialog.getText(self, self.tr("New category"), self.tr("Name (in {family}):").format(family=family))
        if ok and name.strip():
            self._category_action(
                lambda: self.tr("Created {category}.").format(
                    category=category_label(workspace.create_category(self.db, family, name).canonical)
                )
            )

    def _on_add_alias_clicked(self) -> None:
        canonical = self.selected_category()
        if canonical is None:
            return
        alias, ok = QInputDialog.getText(
            self, self.tr("Add alias"), self.tr("Alias for {category}:").format(category=category_label(canonical))
        )
        if ok and alias.strip():
            self._category_action(
                lambda: (
                    workspace.add_category_alias(self.db, canonical, alias),
                    self.tr("Alias “{alias}” added.").format(alias=alias),
                )[1]
            )

    def _on_rename_category_clicked(self) -> None:
        canonical = self.selected_category()
        if canonical is None:
            return
        current = taxonomy.get_category(canonical).name
        name, ok = QInputDialog.getText(self, self.tr("Rename category"), self.tr("New name:"), text=current)
        if ok and name.strip():
            self._category_action(
                lambda: self.tr("Renamed to {category}.").format(
                    category=category_label(workspace.rename_category(self.db, canonical, name).canonical)
                )
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
            self,
            self.tr("Merge category"),
            self.tr("Merge {category} into:").format(category=category_label(absorb)),
            labels,
            0,
            False,
        )
        if ok:
            keep = targets[labels.index(label)]
            self._category_action(
                lambda: self.tr("Merged into {category}.").format(
                    category=category_label(workspace.merge_categories(self.db, keep, absorb).canonical)
                )
            )

    def _on_delete_category_clicked(self) -> None:
        canonical = self.selected_category()
        if canonical is None:
            return
        answer = QMessageBox.question(
            self,
            self.tr("Delete category"),
            self.tr("Delete {category}? Its tracks become uncategorized.").format(category=category_label(canonical)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._category_action(
                lambda: (
                    workspace.delete_category(self.db, canonical),
                    self.tr("Deleted {category}.").format(category=category_label(canonical)),
                )[1]
            )

    # --- playlists --------------------------------------------------------

    def _reload_playlists(self, select_id: int | None = None) -> None:
        if select_id is None:
            select_id = self.selected_playlist_id()
        self.playlist_list.clear()
        smart_rules = self.db.list_smart_rules()
        for record in self.db.list_playlists():
            item = QListWidgetItem(f"{record.name}  ({record.track_count}) · {record.source}")
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            if record.id in smart_rules:
                try:
                    summary = smart_playlist.SmartRules.from_json(smart_rules[record.id]).describe(
                        translator("SmartPlaylistDialog")
                    )
                except ValueError:
                    summary = self.tr("unreadable rules")
                item.setToolTip(self.tr("Smart playlist: {summary}").format(summary=summary))
            self.playlist_list.addItem(item)
            if record.id == select_id:
                self.playlist_list.setCurrentItem(item)
        if self.playlist_list.currentItem() is None:
            self.playlist_tracks.clear()

    def selected_playlist_id(self) -> int | None:
        item = self.playlist_list.currentItem()
        return int(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _selected_playlist(self) -> tuple[int, str] | None:
        item = self.playlist_list.currentItem()
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole)), item.text().split("  (", 1)[0]

    def save_set(self, name: str, paths: list[str]) -> int:
        """The Set panel's draft as an app playlist, then exportable like any
        other from the Playlists panel (issue #221)."""
        playlist_id = self.create_playlist(name, paths, set_prep.SOURCE_SET)
        self.status_label.setText(
            self.tr("Saved the set as “{name}” ({count} track(s)).").format(name=name, count=len(paths))
        )
        return playlist_id

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
        name, ok = QInputDialog.getText(self, self.tr("Playlist name"), self.tr("Name:"), text=default)
        return name.strip() if ok and name.strip() else None

    def _on_new_playlist_clicked(self) -> None:
        rows = self.selected_rows()
        if not rows:
            self.status_label.setText(self.tr("Select tracks in the table first."))
            return
        name = self._ask_playlist_name(self.tr("New playlist"))
        if name:
            self.create_playlist(name, [row.path for row in rows])

    def _on_generate_clicked(self) -> None:
        paths = workspace.generate_playlist(self.visible_rows())
        if not paths:
            self.status_label.setText(self.tr("No visible tracks to build a playlist from."))
            return
        name = self._ask_playlist_name(self.tr("Auto playlist"))
        if name:
            self.create_playlist(name, paths, workspace.SOURCE_GENERATED)

    def _on_match_clicked(self) -> None:
        row = self._current_row()
        if row is None or row.missing:
            self.status_label.setText(self.tr("Select the track to start from first."))
            return
        if row.bpm is None:
            self.status_label.setText(self.tr("The current track has no BPM -- scan or tag it first."))
            return
        candidates = self.visible_rows()
        if row not in candidates:
            candidates.append(row)
        paths = workspace.generate_playlist(candidates, seed_path=row.path)
        name = self._ask_playlist_name(self.tr("Mix from {title}").format(title=row.title or Path(row.path).stem))
        if name:
            self.create_playlist(name, paths, workspace.SOURCE_GENERATED)
            self.status_label.setText(self.tr("{count} compatible track(s) found.").format(count=len(paths) - 1))

    def _on_path_clicked(self) -> None:
        """Issue #191's path mode: every visible track as one mixable path,
        starting from the current track when it has a BPM and a key. Tracks
        the path can't place go to a second, "(leftovers)" playlist."""
        candidates = self.visible_rows()
        if not candidates:
            self.status_label.setText(self.tr("No visible tracks to build a playlist from."))
            return
        options = self._ask_mix_path_options(len(candidates))
        if options is None:
            return
        row = self._current_row()
        start = None
        if row is not None and not row.missing and row.bpm is not None and row.camelot_key:
            start = row.path
            if row not in candidates:
                candidates.append(row)
        path, leftovers = workspace.generate_playlist_path(
            candidates,
            start_path=start,
            direction=options.direction,
            bpm_tolerance_pct=options.bpm_tolerance_pct,
            max_length=options.max_length,
        )
        if not path:
            self.status_label.setText(self.tr("No visible track has both a BPM and a key -- scan or tag them first."))
            return
        first = next((r for r in candidates if r.path == path[0]), None)
        title = first.title if first is not None and first.title else Path(path[0]).stem
        name = self._ask_playlist_name(self.tr("Path from {title}").format(title=title))
        if not name:
            return
        if leftovers:
            leftovers_name = self.tr("{name} (leftovers)").format(name=name)
            self.create_playlist(leftovers_name, leftovers, workspace.SOURCE_GENERATED)
        self.create_playlist(name, path, workspace.SOURCE_GENERATED)
        self.status_label.setText(
            self.tr("{count} track(s) in the path; {others} other track(s) are in “{leftovers}”.").format(
                count=len(path), others=len(leftovers), leftovers=leftovers_name
            )
            if leftovers
            else self.tr("{count} track(s) in the path.").format(count=len(path))
        )

    def _ask_mix_path_options(self, track_count: int) -> workspace.MixPathOptions | None:
        """Show `MixPathDialog` pre-filled with the last values, and remember
        the new ones on OK (issue #211). `None` when cancelled."""
        dialog = MixPathDialog(workspace.load_mix_path_options(self.db), track_count, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        options = dialog.options()
        workspace.save_mix_path_options(self.db, options)
        return options

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
        self.status_label.setText(
            self.tr("Imported {count} playlist(s) from {source}.").format(count=len(playlists), source=source)
        )
        return len(playlists)

    def _import_with(self, reader: Callable[[str], dict[str, list[str]]], path: str, source: str) -> None:
        try:
            playlists = reader(path)
        except Exception as exc:
            _LOGGER.exception("Playlist import failed: %s", path)
            QMessageBox.warning(self, self.tr("Import failed"), f"{path}\n\n{exc}")
            return
        self.import_playlists(playlists, source)

    def _on_import_serato_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Import Serato crates"), "", self.tr("Serato crates (*.crate)")
        )
        playlists = {}
        for path in paths:
            try:
                playlists[Path(path).stem] = workspace.read_serato_crate(path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, self.tr("Import failed"), f"{path}\n\n{exc}")
        if playlists:
            self.import_playlists(playlists, workspace.SOURCE_SERATO)

    def _on_import_traktor_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Import Traktor playlists"), "", self.tr("Traktor collection (*.nml)")
        )
        if path:
            self._import_with(workspace.read_traktor_playlists, path, workspace.SOURCE_TRAKTOR)

    def _on_import_rekordbox_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Import Rekordbox playlists"), "", self.tr("Rekordbox device export (export.pdb)")
        )
        if path:
            self._import_with(workspace.read_rekordbox_playlists, path, workspace.SOURCE_REKORDBOX)

    def export_playlist_as_crate(self, playlist_id: int, crate_path: str) -> None:
        workspace.export_serato_crate(crate_path, self.db.playlist_paths(playlist_id))
        self.status_label.setText(self.tr("Exported {name}.").format(name=Path(crate_path).name))

    def _on_export_serato_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        name = self.playlist_list.currentItem().text().split("  (", 1)[0]
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export as Serato crate"),
            str(user_paths.subfolder(user_paths.EXPORTS) / f"{name}.crate"),
            self.tr("Serato crates (*.crate)"),
        )
        if path:
            try:
                self.export_playlist_as_crate(playlist_id, path)
            except OSError as exc:
                QMessageBox.warning(self, self.tr("Export failed"), f"{path}\n\n{exc}")

    def export_playlist_as_nml(self, playlist_id: int, nml_path: str, name: str) -> None:
        workspace.export_traktor_playlist(nml_path, name, self.db.playlist_paths(playlist_id), db=self.db)
        self.status_label.setText(self.tr("Exported {name}.").format(name=Path(nml_path).name))

    def _on_export_traktor_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        name = self.playlist_list.currentItem().text().split("  (", 1)[0]
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export as Traktor playlist"),
            str(user_paths.subfolder(user_paths.EXPORTS) / f"{name}.nml"),
            self.tr("Traktor playlists (*.nml)"),
        )
        if path:
            try:
                self.export_playlist_as_nml(playlist_id, path, name)
            except OSError as exc:
                QMessageBox.warning(self, self.tr("Export failed"), f"{path}\n\n{exc}")

    # Compare (issue #229): read-only, never writes either side.

    def _selected_playlist_name(self) -> str:
        return self.playlist_list.currentItem().text().split("  (", 1)[0]

    def compare_playlist(self, playlist_id: int, other_name: str, other_paths: list[str]) -> PlaylistComparison:
        """Compares an app playlist with `other_paths` and shows the result."""
        comparison = compare_playlists(self.db.playlist_paths(playlist_id), other_paths)
        name = next((p.name for p in self.db.list_playlists() if p.id == playlist_id), "")
        indexed = {row.path: row for row in self.table_model.rows()}
        self.status_label.setText(
            self.tr("“{name}” matches {other}.").format(name=name, other=other_name)
            if comparison.identical
            else self.tr("Compared with {other}: {only_app} only in app, {only_other} only in {other}, {moved} moved.").format(
                other=other_name,
                only_app=len(comparison.only_in_app),
                only_other=len(comparison.only_in_other),
                moved=len(comparison.moved),
            )
        )
        PlaylistCompareDialog(
            comparison, name, other_name, lambda path: _playlist_track_label(path, indexed.get(path)), self
        ).exec()
        return comparison

    def _on_compare_serato_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            self.status_label.setText(self.tr("Select a playlist to compare first."))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Compare with Serato crate"), "", self.tr("Serato crates (*.crate)")
        )
        if not path:
            return
        try:
            other = workspace.read_serato_crate(path)
        except Exception as exc:
            _LOGGER.exception("Crate read failed: %s", path)
            QMessageBox.warning(self, self.tr("Compare failed"), f"{path}\n\n{exc}")
            return
        self.compare_playlist(playlist_id, self.tr("crate “{name}”").format(name=Path(path).stem), other)

    def _on_compare_traktor_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            self.status_label.setText(self.tr("Select a playlist to compare first."))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Compare with Traktor playlist"), "", self.tr("Traktor collection or playlist (*.nml)")
        )
        if not path:
            return
        try:
            playlists = workspace.read_traktor_playlists(path)
        except Exception as exc:
            _LOGGER.exception("Traktor read failed: %s", path)
            QMessageBox.warning(self, self.tr("Compare failed"), f"{path}\n\n{exc}")
            return
        if not playlists:
            QMessageBox.information(
                self, self.tr("Compare playlists"), f"{path}\n\n" + self.tr("This file has no playlist.")
            )
            return
        names = list(playlists)
        choice = names[0]
        if len(names) > 1:
            own = self._selected_playlist_name()
            start = names.index(own) if own in names else 0
            choice, ok = QInputDialog.getItem(
                self, self.tr("Traktor playlist"), self.tr("Compare with:"), names, start, False
            )
            if not ok:
                return
        self.compare_playlist(playlist_id, self.tr("Traktor “{name}”").format(name=choice), playlists[choice])

    def _on_rename_playlist_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        current = self.playlist_list.currentItem().text().split("  (", 1)[0]
        name = self._ask_playlist_name(current)
        if name:
            self.db.rename_playlist(playlist_id, name)
            self._reload_playlists(select_id=playlist_id)

    # Smart playlists (issue #259): rules saved in the index, evaluated into
    # the playlist's tracks, so export/compare work on them unchanged.

    def create_smart_playlist(self, name: str, rules: smart_playlist.SmartRules) -> int:
        playlist_id = smart_playlist.create_smart_playlist(self.db, name, rules, self.table_model.rows())
        self._reload_playlists(select_id=playlist_id)
        self.side_tabs.setCurrentIndex(2)
        count = len(self.db.playlist_paths(playlist_id))
        self.status_label.setText(self.tr("Smart playlist “{name}”: {count} track(s).").format(name=name, count=count))
        return playlist_id

    def update_smart_playlist(self, playlist_id: int, rules: smart_playlist.SmartRules, name: str | None = None) -> int:
        if name:
            self.db.rename_playlist(playlist_id, name)
        count = smart_playlist.update_smart_playlist(self.db, playlist_id, rules, self.table_model.rows())
        self._reload_playlists(select_id=playlist_id)
        self._show_selected_playlist_tracks()
        self.status_label.setText(self.tr("Smart playlist updated: {count} track(s).").format(count=count))
        return count

    def refresh_smart_playlists(self) -> dict[int, int]:
        """Re-evaluate every smart playlist; returns playlist id -> size."""
        counts = smart_playlist.refresh_smart_playlists(self.db, self.table_model.rows())
        if counts:
            self._reload_playlists()
            self._show_selected_playlist_tracks()
        return counts

    def _show_selected_playlist_tracks(self) -> None:
        self._on_playlist_selected(self.playlist_list.currentItem(), None)

    def _ask_smart_rules(
        self, name: str, rules: smart_playlist.SmartRules
    ) -> tuple[str, smart_playlist.SmartRules] | None:
        dialog = SmartPlaylistDialog(name, rules, self.db.has_play_stats(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.name(), dialog.rules()

    def _on_new_smart_clicked(self) -> None:
        answer = self._ask_smart_rules(self.tr("Smart playlist"), smart_playlist.SmartRules())
        if answer is not None:
            self.create_smart_playlist(*answer)

    def _on_edit_smart_clicked(self) -> None:
        selected = self._selected_playlist()
        rules = smart_playlist.load_rules(self.db, selected[0]) if selected else None
        if selected is None or rules is None:
            self.status_label.setText(self.tr("Select a smart playlist first."))
            return
        answer = self._ask_smart_rules(selected[1], rules)
        if answer is not None:
            name, new_rules = answer
            self.update_smart_playlist(selected[0], new_rules, name if name != selected[1] else None)

    def _on_refresh_smart_clicked(self) -> None:
        counts = self.refresh_smart_playlists()
        if counts:
            self.status_label.setText(self.tr("Refreshed {count} smart playlist(s).").format(count=len(counts)))
        else:
            self.status_label.setText(self.tr("No smart playlist to refresh."))

    def export_smart_playlists(self, options: smart_playlist.SmartExportOptions) -> smart_playlist.SmartExportResult:
        result = smart_playlist.export_smart_playlists(self.db, options, self.table_model.rows())
        smart_playlist.save_export_options(self.db, options)
        self._reload_playlists()
        self._show_selected_playlist_tracks()
        message = self.tr("Exported {count} smart playlist(s): {files} file(s) in {folder}.").format(
            count=result.playlists, files=len(result.written), folder=options.folder
        )
        if result.failed:
            message += " " + self.tr("Failed: {names}.").format(names=", ".join(name for name, _ in result.failed))
        self.status_label.setText(message)
        return result

    def _on_export_smart_clicked(self) -> None:
        count = len(self.db.list_smart_rules())
        if not count:
            self.status_label.setText(self.tr("No smart playlist to export: create one with New smart playlist…."))
            return
        dialog = self.smart_export_dialog_factory(smart_playlist.load_export_options(self.db), count, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.export_smart_playlists(dialog.options())

    def _on_delete_playlist_clicked(self) -> None:
        playlist_id = self.selected_playlist_id()
        if playlist_id is None:
            return
        answer = QMessageBox.question(
            self,
            self.tr("Delete playlist"),
            self.tr("Delete this playlist from the app's library? Files and DJ-software playlists are not touched."),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_playlist(playlist_id)
            self._reload_playlists()


    # --- play history (issue #227) -------------------------------------------

    def load_history(self, dirs: dict[str, str | Path]) -> int:
        """Read the given ``{source: folder}`` history folders (read-only) and
        show them; returns the number of sessions read."""
        try:
            sessions = history.read_history(dirs)
        except OSError as exc:
            QMessageBox.warning(self, self.tr("History"), self.tr("Could not read the history.") + f"\n\n{exc}")
            return 0
        self._history_sessions = sessions
        # Issue #259: remember the play counts for smart playlists' "not
        # played for" rule (this app's index only; history stays read-only).
        # An empty read (wrong folder) keeps the previous counts.
        if sessions:
            self.db.set_play_stats(smart_playlist.play_stats_rows(history.summarize_plays(sessions)))
            self.refresh_smart_playlists()
        self._fill_history_tree()
        self._update_history_summary()
        self.side_tabs.setCurrentIndex(self._history_tab)
        return len(sessions)

    def _on_load_history_clicked(self) -> None:
        dirs = history.default_history_dirs()
        if not dirs:
            self.history_summary.setText(
                self.tr("No Serato or Traktor history folder found in ~/Music. Use “Load from folder…”.")
            )
            return
        self.load_history(dirs)

    def _on_history_folder_clicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr("Choose a Serato or Traktor history folder"))
        if not folder:
            return
        source = history.detect_source(folder)
        if source is None:
            QMessageBox.information(
                self, self.tr("History"), self.tr("This folder holds no Serato .session or Traktor history .nml file.")
            )
            return
        self.load_history({source: folder})

    def _fill_history_tree(self) -> None:
        self.history_tree.clear()
        indexed = {row.path: row for row in self.table_model.rows()}
        grey = QBrush(QColor("#888888"))
        for session in self._history_sessions:
            started = session.started_at
            when = started.strftime("%Y-%m-%d %H:%M") if started else ""
            top = QTreeWidgetItem([when, f"{session.name}  ({len(session.entries)})", ""])
            for entry in session.entries:
                label = " — ".join(filter(None, [entry.artist, entry.title])) or Path(entry.path).name
                item = QTreeWidgetItem(
                    [
                        entry.played_at.strftime("%H:%M") if entry.played_at else "",
                        label,
                        "" if entry.deck is None else str(entry.deck),
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, entry.path)
                notes = [entry.path]
                if not entry.played:
                    notes.append(self.tr("Loaded but not marked as played."))
                if entry.path not in indexed:
                    notes.append(self.tr("Not in the indexed folders."))
                if not entry.played or entry.path not in indexed:
                    for column in range(3):
                        item.setForeground(column, grey)
                item.setToolTip(1, "\n".join(notes))
                top.addChild(item)
            self.history_tree.addTopLevelItem(top)
        self.history_tree.resizeColumnToContents(0)

    def never_played_paths(self) -> list[str]:
        """Indexed, present tracks with no played row in the loaded history."""
        paths = [row.path for row in self.table_model.rows() if not row.missing]
        return history.never_played(paths, self._history_sessions)

    def _update_history_summary(self) -> None:
        if not self._history_sessions:
            self.history_summary.setText(self.tr("No history found in the chosen folder(s)."))
            self.select_never_played_button.setEnabled(False)
            return
        plays = history.summarize_plays(self._history_sessions)
        total = sum(p.play_count for p in plays.values())
        indexed = sum(1 for row in self.table_model.rows() if not row.missing)
        never = len(self.never_played_paths())
        self.history_summary.setText(
            self.tr(
                "{sessions} session(s), {plays} play(s) of {tracks} track(s). "
                "{never} of {indexed} indexed track(s) never played."
            ).format(
                sessions=len(self._history_sessions), plays=total, tracks=len(plays), never=never, indexed=indexed
            )
        )
        self.select_never_played_button.setEnabled(never > 0)

    def select_never_played(self) -> int:
        """Select the never-played tracks among the visible rows; returns how many."""
        never = set(self.never_played_paths())
        visible = [row.path for row in self.visible_rows() if row.path in never]
        self.table.clearSelection()
        self.select_paths(visible)
        self.status_label.setText(self.tr("{count} visible track(s) never played selected.").format(count=len(visible)))
        return len(visible)

    def _on_history_item_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and not self.select_path(path):
            self.status_label.setText(self.tr("That track isn't visible in the table (not indexed, or filtered out)."))


def _playlist_track_label(path: str, row: workspace.LibraryRow | None) -> str:
    if row is None or row.metadata is None or not row.metadata.title:
        return Path(path).name
    artist = f"{row.metadata.artist} — " if row.metadata.artist else ""
    details = " · ".join(filter(None, [_format_bpm(row.bpm), row.camelot_key or ""]))
    return f"{artist}{row.metadata.title}" + (f"  [{details}]" if details else "")


def _playlist_track_item(path: str, row: workspace.LibraryRow | None) -> QListWidgetItem:
    item = QListWidgetItem(_playlist_track_label(path, row))
    item.setToolTip(
        path
        if row is not None
        else QCoreApplication.translate("MusicLibraryView", "Not in the indexed folders: {path}").format(path=path)
    )
    if row is None:
        item.setForeground(QBrush(QColor("#888888")))
    return item
