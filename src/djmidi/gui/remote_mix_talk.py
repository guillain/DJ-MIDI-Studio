"""Talkback in Mix Together (remote mix, phase 14): hold to talk to the other DJs,
from a button or a pad of your controller; their voices play in your headphones.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import user_paths
from djmidi.remote_mix import audio, opus, signals, talkback


class TalkPanel(QFrame):
    def __init__(
        self,
        backend,
        parent: QWidget | None = None,
        *,
        pad_path: Path | None = None,
        name_of: Callable[[int], str] = lambda dj: f"DJ {dj + 1}",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("remoteTalk")
        self._backend = backend
        self._name_of = name_of
        self._pad_path = pad_path or user_paths.workspace_dir() / talkback.FILE_NAME
        self.pad = talkback.load_pad(self._pad_path)
        self.learning = False
        self.receiver = talkback.TalkReceiver()
        self._link = None
        self._mic = None
        self._buffer = audio.SendBuffer()
        self._position = 0
        self.talking = False

        title = QLabel(self.tr("Talkback"))
        title.setObjectName("remoteSoundTitle")
        hint = QLabel(self.tr("Hold to talk to the other DJs: only in their headphones, never in the mix."))
        hint.setWordWrap(True)
        self.mic_combo = QComboBox()
        self.mic_combo.addItem(self.tr("No microphone"), None)
        for name in backend.inputs():
            self.mic_combo.addItem(name, name)
        form = QFormLayout()
        form.addRow(self.tr("Talk with:"), self.mic_combo)
        self.talk_button = QPushButton(self.tr("Hold to talk"))
        self.talk_button.setToolTip(self.tr("Your microphone goes to the other DJs while you hold it"))
        self.talk_button.pressed.connect(lambda: self.set_talking(True))
        self.talk_button.released.connect(lambda: self.set_talking(False))
        self.learn_button = QPushButton()
        self.learn_button.setToolTip(self.tr("Hold a pad of your controller to talk"))
        self.learn_button.clicked.connect(self.learn)
        self.forget_button = QPushButton("✕")
        self.forget_button.setObjectName("chip")
        self.forget_button.setToolTip(self.tr("Forget this pad"))
        self.forget_button.setAccessibleName(self.tr("Forget this pad"))
        self.forget_button.clicked.connect(self.forget)
        row = QHBoxLayout()
        row.addWidget(self.talk_button, 1)
        row.addWidget(self.learn_button)
        row.addWidget(self.forget_button)
        self.status_label = QLabel()
        self.status_label.setObjectName("talkStatus")
        self.status_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addWidget(self.status_label)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._show_status)
        self._show_pad()
        self._enable()

    # -- session -------------------------------------------------------------

    def open(self, link) -> str | None:
        """The sound started: listen for voices, open the microphone. An error text, or None."""
        self._link = link
        self.receiver = talkback.TalkReceiver()
        if hasattr(link, "talk_sink"):
            link.talk_sink = self.receiver.push
        error = None
        name = self.mic_combo.currentData()
        if name:
            try:
                self._mic = self._backend.open_input(name)
            except Exception as exc:  # noqa: BLE001 - a device problem must not stop the sound
                self._mic, error = None, str(exc)
        self._buffer, self._position = audio.SendBuffer(), 0
        self.mic_combo.setEnabled(False)
        self._enable()
        self._timer.start()
        return error

    def close_session(self) -> None:
        self._timer.stop()
        self.set_talking(False)
        if self._mic is not None:
            self._mic.close()
        self._mic = self._link = None
        self.mic_combo.setEnabled(True)
        self.status_label.clear()
        self._enable()

    def _enable(self) -> None:
        self.talk_button.setEnabled(self._link is not None and self._mic is not None)

    def set_talking(self, on: bool) -> None:
        on = on and self._link is not None and self._mic is not None
        if on == self.talking:
            return
        self.talking = on
        self.talk_button.setText(self.tr("Talking…") if on else self.tr("Hold to talk"))
        self._show_status()

    # -- sound -------------------------------------------------------------

    def send_mic(self) -> None:
        """Read the microphone; while talking, send it as a voice."""
        if self._mic is None:
            return
        block = self._mic.read()
        if not len(block) or not self.talking or self._link is None:
            return
        codec = audio.CODEC_OPUS if opus.unavailable() is None else audio.CODEC_PCM24
        packets = self._buffer.add(block, self._position, 0.0, 120.0, codec)
        self._position += len(block)
        send = getattr(self._link, "send_talk", None)
        if callable(send):
            send(packets)

    def voices(self, n: int) -> np.ndarray:
        return self.receiver.read(n)

    def _show_status(self) -> None:
        names = [self._name_of(dj) for dj in self.receiver.talking()]
        if names:
            self.status_label.setText(self.tr("🎙 {names} talking…").format(names=", ".join(names)))
        elif self.talking:
            self.status_label.setText(self.tr("🎙 You're talking to the other DJs."))
        elif self._link is not None and self._mic is None:
            self.status_label.setText(self.tr("Pick a microphone before starting the sound to talk."))
        else:
            self.status_label.clear()

    # -- the pad -------------------------------------------------------------

    def learn(self) -> None:
        self.learning = not self.learning
        self._show_pad()

    def forget(self) -> None:
        self.pad = None
        self._save_pad()
        self._show_pad()

    def feed_midi_event(self, event) -> bool:
        if self.learning:
            trigger = signals.pad_from_event(event)
            if trigger is None:
                return False
            self.pad, self.learning = trigger, False
            self._save_pad()
            self._show_pad()
            return True
        action = talkback.pad_event(event, self.pad)
        if action is None:
            return False
        self.set_talking(action == talkback.PRESS)
        return True

    def _save_pad(self) -> None:
        try:
            talkback.save_pad(self._pad_path, self.pad)
        except OSError as exc:
            self.status_label.setText(self.tr("Pad not saved: {error}").format(error=exc))

    def _show_pad(self) -> None:
        if self.learning:
            self.learn_button.setText(self.tr("Press a pad…"))
        else:
            self.learn_button.setText(self.pad.label() if self.pad else self.tr("Learn a pad"))
        self.forget_button.setVisible(self.pad is not None)

    def closeEvent(self, event) -> None:
        self.close_session()
        super().closeEvent(event)


__all__ = ["TalkPanel"]
