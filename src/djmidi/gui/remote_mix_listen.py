"""The listener's panel of Mix Together (remote mix, phase 8): no decks, just the
official mix from the control room, on the speakers or headphones of your choice.
"""

from __future__ import annotations

import queue
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.empty_state import EmptyState
from djmidi.gui.remote_mix_audio import (
    MAX_BLOCK,
    AudioBackend,
    AudioDeviceError,
    AudioOutput,
    QtAudioBackend,
)
from djmidi.remote_mix import audio, listen, probe, tracklist

ClientFactory = Callable[..., listen.ListenerClient]


class ListenerPanel(QFrame):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        backend: AudioBackend | None = None,
        client_factory: ClientFactory = listen.ListenerClient,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("remoteListen")
        self._backend = backend if backend is not None else QtAudioBackend()
        self._client_factory = client_factory
        self.client: listen.ListenerClient | None = None
        self.player: listen.StreamPlayer | None = None
        self._output: AudioOutput | None = None

        title = QLabel(self.tr("Listen to the mix"))
        title.setObjectName("remoteSoundTitle")
        hint = QLabel(
            self.tr(
                "No decks needed: you hear the official mix from the control room (the host, unless the "
                "other DJ took it). Type its address, pick your speakers or headphones, and listen."
            )
        )
        hint.setWordWrap(True)
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText(self.tr("e.g. 10.147.17.5"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(probe.DEFAULT_PORT)
        self.output_combo = QComboBox()
        for name in self._backend.outputs():
            self.output_combo.addItem(name, name)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 150)
        self.volume.setValue(100)
        self.volume.setToolTip(self.tr("Volume"))
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(10)
        form = QFormLayout()
        form.addRow(self.tr("Control room's address:"), self.address_edit)
        form.addRow(self.tr("Port:"), self.port_spin)
        form.addRow(self.tr("Play the mix on:"), self.output_combo)
        form.addRow(self.tr("Volume:"), self.volume)
        form.addRow(self.tr("Level:"), self.meter)
        self.start_button = QPushButton(self.tr("Listen"))
        self.start_button.clicked.connect(self.toggle)
        self.status_label = QLabel(self.tr("Not listening."))
        self.status_label.setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        # The tracklist the control room sends along (phase 12).
        tracks_title = QLabel(self.tr("Tracklist"))
        tracks_title.setObjectName("remoteSoundTitle")
        self.tracks_view = QListWidget()
        self.tracks_view.setMinimumHeight(120)
        self.tracks_empty = EmptyState(
            self.tracks_view, "♪", self.tr("No track yet"),
            self.tr("The tracks the DJs play show here, sent by the control room."),
        )
        self.tracks = tracklist.SharedTracklist(-1)
        self._who: dict[int, str] = {}
        layout.addWidget(tracks_title)
        layout.addWidget(self.tracks_view, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(5)
        self._timer.timeout.connect(self.pump)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(500)
        self._status_timer.timeout.connect(self._show_status)
        unavailable = getattr(self._backend, "unavailable", None)
        if unavailable:
            self.start_button.setEnabled(False)
            self.status_label.setText(
                self.tr("No sound on this computer: the system audio library is missing ({error}).").format(
                    error=unavailable
                )
            )

    @property
    def running(self) -> bool:
        return self.client is not None

    def toggle(self) -> None:
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self) -> bool:
        host = self.address_edit.text().strip()
        if not host:
            self.status_label.setText(self.tr("Type the control room's address first."))
            self.address_edit.setFocus()
            return False
        name = self.output_combo.currentData()
        if not name:
            self.status_label.setText(self.tr("No speakers or headphones found on this computer."))
            return False
        try:
            output = self._backend.open_output(name)
        except AudioDeviceError as exc:
            self.status_label.setText(self.tr("Sound device problem: {error}").format(error=exc))
            return False
        player = listen.StreamPlayer()
        try:
            client = self._client_factory(server=(host, self.port_spin.value() + listen.LISTEN_PORT_OFFSET), player=player)
        except OSError as exc:
            output.close()
            self.status_label.setText(self.tr("Could not start: {error}").format(error=exc))
            return False
        self._output, self.player, self.client = output, player, client
        self.tracks, self._who = tracklist.SharedTracklist(-1), {}
        self.tracks_view.clear()
        self.tracks_empty.refresh()
        for widget in (self.address_edit, self.port_spin, self.output_combo):
            widget.setEnabled(False)
        self.start_button.setText(self.tr("Stop listening"))
        self._timer.start()
        self._status_timer.start()
        self._show_status()
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._status_timer.stop()
        if self.client is not None:
            self.client.close()
        if self._output is not None:
            self._output.close()
        self.client = self.player = self._output = None
        for widget in (self.address_edit, self.port_spin, self.output_combo):
            widget.setEnabled(True)
        self.start_button.setText(self.tr("Listen"))
        self.status_label.setText(self.tr("Not listening."))
        self.meter.setValue(0)

    def pump(self) -> None:
        if self.player is None or self._output is None:
            return
        n = min(self._output.free_frames(), MAX_BLOCK)
        if n < audio.PACKET_FRAMES:
            return
        block = self.player.read(n)
        self.meter.setValue(int(self.player.last_peak * 100))
        self._output.write(block * (self.volume.value() / 100.0))

    def _read_tracks(self) -> None:
        inbox = getattr(self.client, "inbox", None)
        changed = False
        while inbox is not None:
            try:
                message = inbox.get_nowait()
            except queue.Empty:
                break
            row = self.tracks.receive(message)
            who = tracklist.listener_name(message)
            if who and isinstance(message.get("from"), int):
                changed |= self._who.get(message["from"]) != who
                self._who[message["from"]] = who
            changed |= row is not None
        if changed:
            self.tracks_view.clear()
            for row in self.tracks.rows:
                self.tracks_view.addItem(
                    self.tr("{time}  {name} — {track}").format(
                        time=f"{datetime.fromtimestamp(row.at):%H:%M}",  # noqa: DTZ006
                        name=self._who.get(row.dj) or self.tr("DJ {number}").format(number=row.dj + 1),
                        track=row.label(),
                    )
                )
            self.tracks_view.scrollToBottom()
            self.tracks_empty.refresh()

    def _show_status(self) -> None:
        if self.player is None or self.client is None:
            return
        self._read_tracks()
        if self.client.error:
            self.status_label.setText(self.tr("Network error: {error}").format(error=self.client.error))
        elif self.player.received == 0:
            self.status_label.setText(
                self.tr("Waiting for the mix… The control room must have started its sound.")
            )
        else:
            self.status_label.setText(
                self.tr("Listening to the official mix. Gaps: {gaps:.1f} %").format(gaps=self.player.gap_ratio() * 100)
            )

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)


__all__ = ["ListenerPanel"]
