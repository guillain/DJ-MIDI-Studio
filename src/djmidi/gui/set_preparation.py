"""Set preparation panel (issue #221), the Music Library tab's *Set* side tab.

A thin binding over the Qt-free `djmidi.library.set_prep`: the draft is an
ordered list of paths (`SetPreparationPanel.paths()`), filled by dragging
rows from the library table (`SET_TRACKS_MIME`, produced by
`LibraryTableModel.mimeData`) or with *Add selection*, reordered by drag
and drop inside the list or with the up/down buttons. Every change re-runs
`set_prep.analyze_set`, recolours the list (a red item = its incoming
transition breaks the BPM tolerance or the Camelot rule) and redraws
`SetCurveWidget`, then saves the draft in the library index.

The panel never owns the database: `MusicLibraryView` passes a `db`
callable plus the current rows, and handles *Save as playlist* (so the new
playlist shows up in its Playlists panel) through `saveRequested`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from djmidi import user_paths
from djmidi.gui import help_texts
from djmidi.gui.help_button import help_row
from djmidi.library import set_prep, workspace
from djmidi.library.db import LibraryDB

# Drag payload from the library table: newline-separated track paths.
SET_TRACKS_MIME = "application/x-djmidi-track-paths"

PATH_ROLE = Qt.ItemDataRole.UserRole + 10

_BPM_COLOR = QColor("#2f8fd8")
_ENERGY_COLOR = QColor("#e08a1e")
_INCOMPATIBLE_COLOR = QColor("#d64545")
_UNKNOWN_COLOR = QColor("#8a8a8a")


def encode_paths(paths: Sequence[str]) -> bytes:
    return "\n".join(paths).encode("utf-8")


def decode_paths(data: bytes) -> list[str]:
    return [line for line in bytes(data).decode("utf-8").split("\n") if line]


def _format_bpm(bpm: float | None) -> str:
    if bpm is None:
        return ""
    return f"{bpm:g}" if bpm == int(bpm) else f"{bpm:.1f}"


def item_text(position: int, track: set_prep.SetTrack, incoming: set_prep.Transition | None) -> str:
    details = [_format_bpm(track.bpm), track.camelot_key or ""]
    if track.energy is not None:
        details.append(f"E{track.energy}")
    detail = " · ".join(filter(None, details))
    marker = "⚠ " if incoming is not None and incoming.status == set_prep.STATUS_INCOMPATIBLE else ""
    return f"{marker}{position}. {track.label}" + (f"  [{detail}]" if detail else "")


class SetCurveWidget(QWidget):
    """BPM (left scale) and energy (1-10, right scale) across the draft,
    with each transition's segment drawn red when incompatible and dashed
    grey when it can't be checked. Read-only."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tracks: list[set_prep.SetTrack] = []
        self.transitions: list[set_prep.Transition] = []
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_data(self, tracks: Sequence[set_prep.SetTrack], transitions: Sequence[set_prep.Transition]) -> None:
        self.tracks = list(tracks)
        self.transitions = list(transitions)
        self.setToolTip(self._tooltip())
        self.update()

    def _tooltip(self) -> str:
        if not self.tracks:
            return self.tr("Add tracks to see the set's BPM and energy curve.")
        lines = [self.tr("Blue: BPM · Orange: energy (1-10) · Red: incompatible transition")]
        for transition in self.transitions:
            if transition.status == set_prep.STATUS_INCOMPATIBLE:
                lines.append(f"{transition.index + 1} → {transition.index + 2}: " + "; ".join(transition.issues))
        return "\n".join(lines)

    def bpm_range(self) -> tuple[float, float] | None:
        values = [track.bpm for track in self.tracks if track.bpm]
        if not values:
            return None
        low, high = min(values), max(values)
        pad = max((high - low) * 0.1, 2.0)
        return low - pad, high + pad

    def _x(self, plot: QRectF, index: int) -> float:
        if len(self.tracks) <= 1:
            return plot.center().x()
        return plot.left() + plot.width() * index / (len(self.tracks) - 1)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().color(QPalette.ColorRole.WindowText)
        plot = QRectF(self.rect()).adjusted(36, 10, -26, -18)
        painter.setPen(QPen(text_color, 1))
        painter.drawRect(plot)
        bpm_range = self.bpm_range()
        if not self.tracks or plot.width() <= 0 or plot.height() <= 0:
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, self.tr("Empty set"))
            return
        if bpm_range is not None:
            low, high = bpm_range
            painter.drawText(QRectF(0, plot.top() - 6, 34, 14), Qt.AlignmentFlag.AlignRight, f"{high:.0f}")
            painter.drawText(QRectF(0, plot.bottom() - 8, 34, 14), Qt.AlignmentFlag.AlignRight, f"{low:.0f}")
        painter.drawText(QRectF(plot.right() + 3, plot.top() - 6, 24, 14), Qt.AlignmentFlag.AlignLeft, "E10")
        painter.drawText(QRectF(plot.right() + 3, plot.bottom() - 8, 24, 14), Qt.AlignmentFlag.AlignLeft, "E1")

        energy_points = self._energy_points(plot)
        if len(energy_points) > 1:
            path = QPainterPath(energy_points[0])
            for point in energy_points[1:]:
                path.lineTo(point)
            painter.setPen(QPen(_ENERGY_COLOR, 1.5, Qt.PenStyle.DashLine))
            painter.drawPath(path)
        painter.setPen(QPen(_ENERGY_COLOR, 1))
        painter.setBrush(QBrush(_ENERGY_COLOR))
        for point in energy_points:
            painter.drawEllipse(point, 2.5, 2.5)

        if bpm_range is None:
            return
        bpm_points = self._bpm_points(plot, bpm_range)
        for transition in self.transitions:
            start, end = bpm_points.get(transition.index), bpm_points.get(transition.index + 1)
            if start is None or end is None:
                continue
            if transition.status == set_prep.STATUS_INCOMPATIBLE:
                pen = QPen(_INCOMPATIBLE_COLOR, 3)
            elif transition.status == set_prep.STATUS_UNKNOWN:
                pen = QPen(_UNKNOWN_COLOR, 2, Qt.PenStyle.DashLine)
            else:
                pen = QPen(_BPM_COLOR, 2)
            painter.setPen(pen)
            painter.drawLine(start, end)
        painter.setPen(QPen(_BPM_COLOR, 1))
        painter.setBrush(QBrush(_BPM_COLOR))
        for point in bpm_points.values():
            painter.drawEllipse(point, 3, 3)

    def _bpm_points(self, plot: QRectF, bpm_range: tuple[float, float]) -> dict[int, QPointF]:
        low, high = bpm_range
        points = {}
        for index, track in enumerate(self.tracks):
            if track.bpm:
                y = plot.bottom() - plot.height() * (track.bpm - low) / (high - low)
                points[index] = QPointF(self._x(plot, index), y)
        return points

    def _energy_points(self, plot: QRectF) -> list[QPointF]:
        low, high = set_prep.ENERGY_RANGE
        return [
            QPointF(self._x(plot, index), plot.bottom() - plot.height() * (track.energy - low) / (high - low))
            for index, track in enumerate(self.tracks)
            if track.energy is not None
        ]


class SetListWidget(QListWidget):
    """The draft's list: drag inside to reorder, drop library rows in to
    insert them where they land."""

    pathsDropped = Signal(list, int)
    orderChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAcceptDrops(True)

    def _is_external(self, event) -> bool:
        return event.source() is not self and event.mimeData().hasFormat(SET_TRACKS_MIME)

    def dragEnterEvent(self, event) -> None:
        if self._is_external(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._is_external(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def drop_row(self, position) -> int:
        """The row a drop at `position` (viewport coordinates) inserts before."""
        item = self.itemAt(position)
        if item is None:
            return self.count()
        row = self.row(item)
        rect = self.visualItemRect(item)
        return row + 1 if position.y() > rect.center().y() else row

    def dropEvent(self, event) -> None:
        if self._is_external(event):
            paths = decode_paths(event.mimeData().data(SET_TRACKS_MIME).data())
            event.acceptProposedAction()
            self.pathsDropped.emit(paths, self.drop_row(event.position().toPoint()))
            return
        super().dropEvent(event)
        self.orderChanged.emit()


class SetPreparationPanel(QWidget):
    saveRequested = Signal(str, list)

    def __init__(
        self,
        db: Callable[[], LibraryDB],
        selected_rows: Callable[[], list[workspace.LibraryRow]],
        selected_playlist: Callable[[], tuple[int, str] | None],
        status: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._selected_rows = selected_rows
        self._selected_playlist = selected_playlist
        self._status = status
        self._paths: list[str] = []
        self._rows: dict[str, workspace.LibraryRow] = {}
        self._loaded = False
        self.tracks: list[set_prep.SetTrack] = []
        self.transitions: list[set_prep.Transition] = []

        box = QVBoxLayout(self)
        box.addLayout(help_row(self, *help_texts.LIBRARY_SET))
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        box.addWidget(self.summary_label)
        self.curve = SetCurveWidget()
        box.addWidget(self.curve)
        self.list = SetListWidget()
        self.list.setToolTip(self.tr("Drag tracks here from the table; drag inside the list to reorder."))
        self.list.pathsDropped.connect(self.insert_paths)
        self.list.orderChanged.connect(self._sync_from_list)
        box.addWidget(self.list, 1)

        tolerance_row = QHBoxLayout()
        tolerance_row.addWidget(QLabel(self.tr("BPM tolerance ±")))
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(*set_prep.BPM_TOLERANCE_RANGE)
        self.tolerance_spin.setSingleStep(0.5)
        self.tolerance_spin.setSuffix(" %")
        self.tolerance_spin.setValue(set_prep.DEFAULT_BPM_TOLERANCE_PCT)
        self.tolerance_spin.valueChanged.connect(self._on_changed)
        tolerance_row.addWidget(self.tolerance_spin)
        tolerance_row.addStretch(1)
        box.addLayout(tolerance_row)

        grid = QGridLayout()
        specs: list[tuple[str, str, Callable[[], None], str]] = [
            ("add_button", self.tr("Add selection"), self.add_selection,
             self.tr("Appends the tracks selected in the table (each track once).")),
            ("remove_button", self.tr("Remove"), self.remove_selected, ""),
            ("clear_button", self.tr("Clear"), self.clear, ""),
            ("up_button", self.tr("Move up"), lambda: self.move_selected(-1), ""),
            ("down_button", self.tr("Move down"), lambda: self.move_selected(1), ""),
            ("load_button", self.tr("Load playlist"), self.load_selected_playlist,
             self.tr("Replaces the draft with the playlist selected in the Playlists tab.")),
            ("save_button", self.tr("Save as playlist…"), self._on_save_clicked,
             self.tr("Saves the draft, in this order, as an app playlist.")),
            ("export_serato_button", self.tr("Export as Serato crate…"), self._on_export_serato_clicked,
             self.tr("Writes a new .crate file where you choose.")),
            ("export_traktor_button", self.tr("Export as Traktor playlist…"), self._on_export_traktor_clicked,
             self.tr("Writes a new single-playlist .nml where you choose.")),
        ]
        for index, (attr, label, handler, tip) in enumerate(specs):
            button = QPushButton(label)
            if tip:
                button.setToolTip(tip)
            button.clicked.connect(handler)
            setattr(self, attr, button)
            # Two columns: the export labels are long and the side panel narrow.
            grid.addWidget(button, index // 2, index % 2)
        box.addLayout(grid)
        self._refresh(save=False)

    # --- state --------------------------------------------------------

    def paths(self) -> list[str]:
        return list(self._paths)

    def set_rows(self, rows: Sequence[workspace.LibraryRow]) -> None:
        """New library rows (after a scan or a tag edit). The first call
        also restores the draft remembered in the index."""
        self._rows = {row.path: row for row in rows}
        if not self._loaded:
            self._loaded = True
            draft = set_prep.load_set_draft(self._db())
            self._paths = list(draft.paths)
            self.tolerance_spin.blockSignals(True)
            self.tolerance_spin.setValue(draft.bpm_tolerance_pct)
            self.tolerance_spin.blockSignals(False)
        self._refresh(save=False)

    def set_paths(self, paths: Sequence[str]) -> None:
        self._paths = set_prep.insert_paths([], paths)
        self._refresh()

    def insert_paths(self, paths: Sequence[str], index: int | None = None) -> int:
        before = len(self._paths)
        self._paths = set_prep.insert_paths(self._paths, paths, index)
        self._refresh()
        return len(self._paths) - before

    def selected_list_rows(self) -> list[int]:
        return sorted(self.list.row(item) for item in self.list.selectedItems())

    def add_selection(self) -> None:
        rows = self._selected_rows()
        if not rows:
            self._status(self.tr("Select tracks in the table first."))
            return
        added = self.insert_paths([row.path for row in rows])
        skipped = len(rows) - added
        self._status(
            self.tr("Added {count} track(s) to the set.").format(count=added)
            + (self.tr(" {count} already in it.").format(count=skipped) if skipped else "")
        )

    def remove_selected(self) -> None:
        self._paths = set_prep.remove_rows(self._paths, self.selected_list_rows())
        self._refresh()

    def clear(self) -> None:
        self._paths = []
        self._refresh()

    def move_selected(self, offset: int) -> None:
        self._paths, moved = set_prep.move_rows(self._paths, self.selected_list_rows(), offset)
        self._refresh()
        for row in moved:
            self.list.item(row).setSelected(True)

    def load_selected_playlist(self) -> None:
        selected = self._selected_playlist()
        if selected is None:
            self._status(self.tr("Select a playlist in the Playlists tab first."))
            return
        playlist_id, name = selected
        self.set_paths(self._db().playlist_paths(playlist_id))
        self._status(self.tr("Loaded “{name}” into the set.").format(name=name))

    def _sync_from_list(self) -> None:
        """After an internal drag: the list's order becomes the draft's."""
        self._paths = [self.list.item(row).data(PATH_ROLE) for row in range(self.list.count())]
        self._refresh()

    def _on_changed(self, *_args: object) -> None:
        self._refresh()

    def _refresh(self, save: bool = True) -> None:
        tolerance = self.tolerance_spin.value()
        self.tracks = set_prep.resolve_set_tracks(self._paths, self._rows)
        self.transitions = set_prep.analyze_set(self.tracks, tolerance)
        self.list.blockSignals(True)
        self.list.clear()
        for index, track in enumerate(self.tracks):
            incoming = self.transitions[index - 1] if index > 0 else None
            self.list.addItem(self._item(index, track, incoming))
        self.list.blockSignals(False)
        self.curve.set_data(self.tracks, self.transitions)
        self.summary_label.setText(set_prep.summarize(self.tracks, self.transitions).text)
        has_tracks = bool(self._paths)
        for button in (self.save_button, self.export_serato_button, self.export_traktor_button, self.clear_button):
            button.setEnabled(has_tracks)
        if save and self._loaded:
            set_prep.save_set_draft(self._db(), set_prep.SetDraft(tuple(self._paths), tolerance))

    @staticmethod
    def _item(index: int, track: set_prep.SetTrack, incoming: set_prep.Transition | None) -> QListWidgetItem:
        item = QListWidgetItem(item_text(index + 1, track, incoming))
        item.setData(PATH_ROLE, track.path)
        tips = [
            track.path
            if track.indexed
            else QCoreApplication.translate("SetPreparationPanel", "Not in the indexed folders: {path}").format(
                path=track.path
            )
        ]
        if incoming is not None:
            tips.append(
                QCoreApplication.translate("SetPreparationPanel", "From track {index}: ").format(index=index)
                + ("; ".join(incoming.issues) or QCoreApplication.translate("SetPreparationPanel", "compatible"))
            )
            if incoming.status == set_prep.STATUS_INCOMPATIBLE:
                item.setForeground(QBrush(_INCOMPATIBLE_COLOR))
        if not track.indexed:
            item.setForeground(QBrush(_UNKNOWN_COLOR))
        item.setToolTip("\n".join(tips))
        return item

    # --- save & export --------------------------------------------------

    def _ask_name(self) -> str | None:
        name, ok = QInputDialog.getText(self, self.tr("Save set"), self.tr("Playlist name:"), text=self.tr("Set"))
        return name.strip() if ok and name.strip() else None

    def _on_save_clicked(self) -> None:
        if not self._paths:
            return
        name = self._ask_name()
        if name:
            self.saveRequested.emit(name, self.paths())

    def export_crate(self, crate_path: str) -> None:
        workspace.export_serato_crate(crate_path, self._paths)
        self._status(self.tr("Exported {name}.").format(name=Path(crate_path).name))

    def export_nml(self, nml_path: str, name: str) -> None:
        workspace.export_traktor_playlist(nml_path, name, self._paths, db=self._db())
        self._status(self.tr("Exported {name}.").format(name=Path(nml_path).name))

    def _export(self, title: str, suffix: str, file_filter: str, write: Callable[[str], None]) -> None:
        if not self._paths:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, title, str(user_paths.subfolder(user_paths.EXPORTS) / f"Set{suffix}"), file_filter
        )
        if not path:
            return
        try:
            write(path)
        except OSError as exc:
            QMessageBox.warning(self, self.tr("Export failed"), f"{path}\n\n{exc}")

    def _on_export_serato_clicked(self) -> None:
        self._export(
            self.tr("Export set as Serato crate"), ".crate", self.tr("Serato crates (*.crate)"), self.export_crate
        )

    def _on_export_traktor_clicked(self) -> None:
        self._export(
            self.tr("Export set as Traktor playlist"),
            ".nml",
            self.tr("Traktor playlists (*.nml)"),
            lambda path: self.export_nml(path, Path(path).stem),
        )
