"""The shared tracklist of Mix Together (remote mix, phase 11): every DJ's played
tracks, read from their own DJ software's history (read-only) or typed by hand.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import user_paths
from djmidi.gui.empty_state import EmptyState
from djmidi.library import history
from djmidi.remote_mix import tracklist

POLL_MS = 3000


class TracklistPanel(QFrame):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        name_of: Callable[[int], str] = lambda dj: f"DJ {dj + 1}",
        history_dirs: Callable[[], dict[str, Path]] = history.default_history_dirs,
        exports_dir: Path | None = None,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        wall: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("remoteTracklist")
        self._name_of = name_of
        self._history_dirs = history_dirs
        self._exports_dir = exports_dir
        self._now = now
        self._wall = wall
        self.list: tracklist.SharedTracklist | None = None
        self._send: Callable[[dict], None] | None = None
        self.watcher: tracklist.HistoryWatcher | None = None
        self._chosen: Path | None = None
        self._started: datetime | None = None
        self.last_export: Path | None = None

        title = QLabel(self.tr("Tracklist"))
        title.setObjectName("remoteSoundTitle")
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.choose_button = QPushButton(self.tr("Choose the history folder…"))
        self.choose_button.setToolTip(self.tr("Serato's History folder or Traktor's History folder: read only, never changed"))
        self.choose_button.clicked.connect(self.choose_folder)
        self.view = QListWidget()
        self.view.setMinimumHeight(140)
        self.empty = EmptyState(
            self.view, "♪", self.tr("No track yet"),
            self.tr("Each track you play shows here for everyone, read from your DJ software's history."),
        )
        self.track_edit = QLineEdit()
        self.track_edit.setPlaceholderText(self.tr("Artist – Title"))
        self.track_edit.returnPressed.connect(self.add_typed)
        self.add_button = QPushButton(self.tr("Add"))
        self.add_button.setToolTip(self.tr("Add a track by hand, when your DJ software doesn't write its history live"))
        self.add_button.clicked.connect(self.add_typed)
        typed = QHBoxLayout()
        typed.addWidget(self.track_edit, 1)
        typed.addWidget(self.add_button)
        self.find_button = QPushButton(self.tr("Find this track"))
        self.find_button.setToolTip(self.tr("Look the selected track up (opens your browser)"))
        self.find_menu = QMenu(self)
        self.find_button.setMenu(self.find_menu)
        self.find_button.setEnabled(False)
        self.view.currentRowChanged.connect(self._on_row)
        self.copy_button = QPushButton(self.tr("Copy the tracklist"))
        self.copy_button.clicked.connect(self.copy)
        self.save_button = QPushButton(self.tr("Save the tracklist"))
        self.save_button.setToolTip(self.tr("A text file in your Exports folder"))
        self.save_button.clicked.connect(self.save)
        actions = QHBoxLayout()
        actions.addWidget(self.find_button)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.source_label)
        layout.addWidget(self.choose_button, 0)
        layout.addWidget(self.view, 1)
        layout.addLayout(typed)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.poll)
        self._ticks = 0
        self._enable()
        self.source_label.setText(
            self.tr("Once connected, the tracks you play are read from your DJ software's history (never changed).")
        )

    # --- session ---------------------------------------------------------

    def attach(self, me: int, send: Callable[[dict], None]) -> None:
        if self.list is None or self.list.me != me:
            self.list = tracklist.SharedTracklist(me)
            self._started = self._now()
            self._watch()
            self._show_rows()
        self._send = send
        self._enable()
        self._timer.start()

    def detach(self) -> None:
        """The session ended: the list stays on screen (to copy or save it), nothing more is read."""
        self._timer.stop()
        self._send = None
        self.watcher = None
        self._enable()

    def reset(self) -> None:
        self.detach()
        self.list = None
        self._show_rows()

    def _enable(self) -> None:
        connected = self._send is not None
        self.track_edit.setEnabled(connected)
        self.add_button.setEnabled(connected)
        has_rows = self.list is not None and bool(self.list.rows)
        self.copy_button.setEnabled(has_rows)
        self.save_button.setEnabled(has_rows)

    # --- reading the history --------------------------------------------

    def _folders(self) -> dict[str, Path]:
        if self._chosen is not None:
            found = tracklist.watchable_folder(self._chosen)
            return {found[0]: found[1]} if found else {}
        folders = {}
        for source, folder in self._history_dirs().items():
            found = tracklist.watchable_folder(folder)
            if found is not None and found[0] == source:
                folders[source] = found[1]
        return folders

    def _watch(self) -> None:
        folders = self._folders()
        self.watcher = tracklist.HistoryWatcher(folders, self._started or self._now()) if folders else None
        self._show_source()

    def _show_source(self) -> None:
        folders = self.watcher.folders if self.watcher is not None else {}
        if not folders:
            self.source_label.setText(
                self.tr("No Serato or Traktor history found on this computer: choose its folder, or type your tracks below.")
            )
            return
        names = {history.SOURCE_SERATO: "Serato", history.SOURCE_TRAKTOR: "Traktor"}
        text = ", ".join(f"{names[source]} ({folder})" for source, folder in folders.items())
        self.source_label.setText(self.tr("Your tracks come from your history: {folders}").format(folders=text))

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr("Your DJ software's History folder"))
        if folder:
            self.use_folder(Path(folder))

    def use_folder(self, folder: Path) -> bool:
        if tracklist.watchable_folder(folder) is None:
            self.status_label.setText(self.tr("No Serato or Traktor history in {folder}.").format(folder=folder))
            return False
        self._chosen = folder
        if self.list is not None and self._send is not None:
            self._watch()
        self.status_label.setText(self.tr("History folder chosen: {folder}").format(folder=folder))
        return True

    def poll(self) -> None:
        if self.list is None or self._send is None:
            return
        if self.watcher is not None:
            for entry in self.watcher.poll():
                title, artist = tracklist.entry_texts(entry)
                self._share(self.list.add(title, artist, entry.played_at.timestamp()))
            if self.watcher.error:
                self.status_label.setText(self.tr("History not read: {error}").format(error=self.watcher.error))

    def resend(self) -> None:
        """Our rows again (a DJ who joined late, a lost packet)."""
        if self.list is not None and self._send is not None:
            for message in self.list.own_messages():
                self._send(message)

    # --- rows -------------------------------------------------------------

    def add_typed(self) -> None:
        text = self.track_edit.text().strip()
        if self.list is None or self._send is None or not text:
            return
        artist, _, title = text.partition(" – ") if " – " in text else text.partition(" - ")
        if not title:
            artist, title = "", text
        self._share(self.list.add(title, artist, self._wall()))
        self.track_edit.clear()

    def _share(self, message: dict | None) -> None:
        if message is None:
            return
        if self._send is not None:
            self._send(message)
        self._show_rows()

    def receive(self, message: dict) -> None:
        if self.list is not None and self.list.receive(message) is not None:
            self._show_rows()

    def _show_rows(self) -> None:
        self.view.clear()
        for row in self.list.rows if self.list is not None else []:
            self.view.addItem(
                self.tr("{time}  {name} — {track}").format(
                    time=f"{datetime.fromtimestamp(row.at):%H:%M}",  # noqa: DTZ006
                    name=self._name_of(row.dj),
                    track=row.label(),
                )
            )
        if self.view.count():
            self.view.scrollToBottom()
        self.empty.refresh()
        self._enable()

    def _on_row(self, index: int) -> None:
        rows = self.list.rows if self.list is not None else []
        row = rows[index] if 0 <= index < len(rows) else None
        self.find_menu.clear()
        self.find_button.setEnabled(row is not None)
        if row is None:
            return
        for site, url in tracklist.search_urls(row):
            action = self.find_menu.addAction(self.tr("On {site}").format(site=site))
            action.triggered.connect(lambda _checked=False, u=url: self._open(u))

    def _open(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def text(self) -> str:
        return tracklist.text_export(self.list.rows if self.list else [], self._name_of, self._started)

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.text())
        self.status_label.setText(self.tr("Tracklist copied: paste it in a post or a description."))

    def save(self) -> Path | None:
        if self.list is None or not self.list.rows:
            return None
        folder = self._exports_dir or user_paths.subfolder(user_paths.EXPORTS)
        path = Path(folder) / tracklist.tracklist_name(self._started or self._now())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.text(), encoding="utf-8")
        except OSError as exc:
            self.status_label.setText(self.tr("Tracklist not saved: {error}").format(error=exc))
            return None
        self.last_export = path
        self.status_label.setText(self.tr("Tracklist saved: {path}").format(path=path))
        return path


__all__ = ["TracklistPanel"]
