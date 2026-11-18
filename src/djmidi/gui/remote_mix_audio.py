"""The sound panel of Mix Together (remote mix, phase 2): send your master,
hear the other DJ one bar late on your grid, and a small mixer for the
program mix (both DJs through a crossfader) sent to an output of your choice
(a virtual device for OBS or a recorder).

Devices come through an injectable ``AudioBackend``; the real one wraps
QtMultimedia (48 kHz, stereo, 16-bit). A 5 ms timer pumps the audio: Python
never runs inside an audio callback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi.remote_mix import audio
from djmidi.remote_mix.probe import LinkSnapshot, local_beat_at

_LOGGER = logging.getLogger(__name__)

MAX_BLOCK = 1920  # never write more than 40 ms at once
OUTPUT_BUFFER_FRAMES = 2880  # 60 ms of device buffer


class AudioInput(Protocol):
    def read(self) -> np.ndarray: ...

    def close(self) -> None: ...


class AudioOutput(Protocol):
    def free_frames(self) -> int: ...

    def queued_frames(self) -> int: ...

    def write(self, samples: np.ndarray) -> None: ...

    def close(self) -> None: ...


class AudioBackend(Protocol):
    def inputs(self) -> list[str]: ...

    def outputs(self) -> list[str]: ...

    def open_input(self, name: str) -> AudioInput: ...

    def open_output(self, name: str) -> AudioOutput: ...


class AudioDeviceError(RuntimeError):
    pass


class QtAudioBackend:
    """QtMultimedia devices at 48 kHz, stereo, 16-bit."""

    def __init__(self) -> None:
        from PySide6.QtMultimedia import QAudioFormat

        self._format = QAudioFormat()
        self._format.setSampleRate(audio.RATE)
        self._format.setChannelCount(audio.CHANNELS)
        self._format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

    @staticmethod
    def _devices(kind: str):
        from PySide6.QtMultimedia import QMediaDevices

        return QMediaDevices.audioInputs() if kind == "in" else QMediaDevices.audioOutputs()

    def inputs(self) -> list[str]:
        return [d.description() for d in self._devices("in")]

    def outputs(self) -> list[str]:
        return [d.description() for d in self._devices("out")]

    def _device(self, kind: str, name: str):
        for device in self._devices(kind):
            if device.description() == name:
                if not device.isFormatSupported(self._format):
                    raise AudioDeviceError(f"{name}: 48 kHz stereo not supported")
                return device
        raise AudioDeviceError(f"{name}: not found")

    def open_input(self, name: str) -> AudioInput:
        from PySide6.QtMultimedia import QAudioSource

        source = QAudioSource(self._device("in", name), self._format)
        io = source.start()
        if io is None:
            raise AudioDeviceError(f"{name}: could not start")
        return _QtInput(source, io)

    def open_output(self, name: str) -> AudioOutput:
        from PySide6.QtMultimedia import QAudioSink

        sink = QAudioSink(self._device("out", name), self._format)
        sink.setBufferSize(OUTPUT_BUFFER_FRAMES * audio.CHANNELS * 2)
        io = sink.start()
        if io is None:
            raise AudioDeviceError(f"{name}: could not start")
        return _QtOutput(sink, io)


class _QtInput:
    def __init__(self, source, io) -> None:
        self._source, self._io = source, io
        self._rest = b""

    def read(self) -> np.ndarray:
        data = self._rest + bytes(self._io.readAll().data())
        usable = len(data) // 4 * 4
        self._rest = data[usable:]
        pcm = np.frombuffer(data[:usable], dtype="<i2").astype(np.float32) / 32767.0
        return pcm.reshape(-1, audio.CHANNELS)

    def close(self) -> None:
        self._source.stop()


class _QtOutput:
    def __init__(self, sink, io) -> None:
        self._sink, self._io = sink, io

    def free_frames(self) -> int:
        return self._sink.bytesFree() // 4

    def queued_frames(self) -> int:
        return (self._sink.bufferSize() - self._sink.bytesFree()) // 4

    def write(self, samples: np.ndarray) -> None:
        self._io.write((np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())

    def close(self) -> None:
        self._sink.stop()


# Context the dialog gives: (peer host, audio port, Link reader) once connected with Link, else None.
AudioContext = Callable[[], "tuple[str, int, Callable[[], LinkSnapshot | None]] | None"]
LinkFactory = Callable[..., audio.AudioLink]


class RemoteAudioPanel(QFrame):
    def __init__(
        self,
        context: AudioContext,
        parent: QWidget | None = None,
        *,
        backend: AudioBackend | None = None,
        link_factory: LinkFactory = audio.AudioLink,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("remoteSound")
        self._context = context
        self._backend = backend if backend is not None else QtAudioBackend()
        self._link_factory = link_factory
        self.player: audio.BarAlignedPlayer | None = None
        self.link: audio.AudioLink | None = None
        self._input: AudioInput | None = None
        self._monitor: AudioOutput | None = None
        self._program: AudioOutput | None = None
        self._reader: Callable[[], LinkSnapshot | None] | None = None
        self._position = 0
        self._me_fifo = np.zeros((0, audio.CHANNELS), dtype=np.float32)

        title = QLabel(self.tr("Hear each other on the grid"))
        title.setObjectName("remoteSoundTitle")
        hint = QLabel(
            self.tr(
                "The other DJ's sound plays one bar after its beat, so it lands on your grid. "
                "Your own sound stays in your room as usual."
            )
        )
        hint.setWordWrap(True)

        none = self.tr("Nowhere")
        self.input_combo = QComboBox()
        self.input_combo.addItem(self.tr("Don't send my sound"), None)
        self.monitor_combo = QComboBox()
        self.monitor_combo.addItem(none, None)
        self.program_combo = QComboBox()
        self.program_combo.addItem(none, None)
        for name in self._backend.inputs():
            self.input_combo.addItem(name, name)
        for name in self._backend.outputs():
            self.monitor_combo.addItem(name, name)
            self.program_combo.addItem(name, name)
        if self.monitor_combo.count() > 1:
            self.monitor_combo.setCurrentIndex(1)
        self.quality_combo = QComboBox()
        self.quality_combo.addItem(self.tr("Full, 48 kHz (about 1.5 Mb/s)"), audio.CODEC_PCM48)
        self.quality_combo.addItem(self.tr("Light, 24 kHz (about 0.8 Mb/s)"), audio.CODEC_PCM24)
        self.nudge_spin = QSpinBox()
        self.nudge_spin.setRange(-200, 200)
        self.nudge_spin.setSuffix(self.tr(" ms"))
        self.nudge_spin.setToolTip(
            self.tr("Move their sound earlier (−) or later (+) if it still sounds off the beat: sound cards add their own delay")
        )
        form = QFormLayout()
        form.addRow(self.tr("Send my sound from:"), self.input_combo)
        form.addRow(self.tr("Play their sound on:"), self.monitor_combo)
        form.addRow(self.tr("Program mix to:"), self.program_combo)
        form.addRow(self.tr("Quality:"), self.quality_combo)
        form.addRow(self.tr("Fine-tune:"), self.nudge_spin)

        self.start_button = QPushButton(self.tr("Start the sound"))
        self.start_button.clicked.connect(self.toggle)
        self.status_label = QLabel(self.tr("Sound off."))
        self.status_label.setWordWrap(True)

        mixer = QGridLayout()
        self.me_volume = self._fader()
        self.them_volume = self._fader()
        self.me_meter = self._meter()
        self.them_meter = self._meter()
        self.crossfader = QSlider(Qt.Orientation.Horizontal)
        self.crossfader.setRange(0, 100)
        self.crossfader.setValue(50)
        self.crossfader.setToolTip(self.tr("Program mix: you on the left, the other DJ on the right"))
        mixer.addWidget(QLabel(self.tr("Me")), 0, 0)
        mixer.addWidget(self.me_volume, 0, 1)
        mixer.addWidget(self.me_meter, 0, 2)
        self.them_name = QLabel(self.tr("Them"))
        mixer.addWidget(self.them_name, 1, 0)
        mixer.addWidget(self.them_volume, 1, 1)
        mixer.addWidget(self.them_meter, 1, 2)
        mixer.addWidget(QLabel(self.tr("Crossfader")), 2, 0)
        mixer.addWidget(self.crossfader, 2, 1, 1, 2)
        mixer.setColumnStretch(1, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addLayout(mixer)

        self._timer = QTimer(self)
        self._timer.setInterval(5)
        self._timer.timeout.connect(self.pump)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(500)
        self._status_timer.timeout.connect(self._show_status)

    def _fader(self) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 150)
        slider.setValue(100)
        slider.setToolTip(self.tr("Volume"))
        return slider

    @staticmethod
    def _meter() -> QProgressBar:
        meter = QProgressBar()
        meter.setRange(0, 100)
        meter.setTextVisible(False)
        meter.setFixedWidth(80)
        meter.setFixedHeight(10)
        return meter

    @property
    def running(self) -> bool:
        return self.player is not None

    def set_peer_name(self, name: str) -> None:
        self.them_name.setText(name)

    def toggle(self) -> None:
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self) -> bool:
        context = self._context()
        if context is None:
            self.status_label.setText(self.tr("Connect first, with Link on in both DJ programs."))
            return False
        host, port, reader = context
        player = audio.BarAlignedPlayer()
        try:
            link = self._link_factory(port=port, peer=(host, port), player=player)
        except OSError as exc:
            self.status_label.setText(self.tr("Could not open the sound port: {error}").format(error=exc))
            return False
        opened: list = []
        try:
            name = self.input_combo.currentData()
            self._input = self._backend.open_input(name) if name else None
            opened.append(self._input)
            name = self.monitor_combo.currentData()
            self._monitor = self._backend.open_output(name) if name else None
            opened.append(self._monitor)
            name = self.program_combo.currentData()
            self._program = self._backend.open_output(name) if name else None
        except AudioDeviceError as exc:
            for device in opened:
                if device is not None:
                    device.close()
            link.close()
            self._input = self._monitor = self._program = None
            self.status_label.setText(self.tr("Sound device problem: {error}").format(error=exc))
            return False
        self.player, self.link, self._reader = player, link, reader
        self._position = 0
        self._me_fifo = np.zeros((0, audio.CHANNELS), dtype=np.float32)
        for widget in (self.input_combo, self.monitor_combo, self.program_combo, self.quality_combo):
            widget.setEnabled(False)
        self.start_button.setText(self.tr("Stop the sound"))
        self._timer.start()
        self._status_timer.start()
        self._show_status()
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._status_timer.stop()
        for device in (self._input, self._monitor, self._program):
            if device is not None:
                device.close()
        if self.link is not None:
            self.link.close()
        self._input = self._monitor = self._program = None
        self.player = self.link = self._reader = None
        for widget in (self.input_combo, self.monitor_combo, self.program_combo, self.quality_combo):
            widget.setEnabled(True)
        self.start_button.setText(self.tr("Start the sound"))
        self.status_label.setText(self.tr("Sound off."))
        self.me_meter.setValue(0)
        self.them_meter.setValue(0)

    def pump(self) -> None:
        if self.player is None or self._reader is None:
            return
        snapshot = self._reader()
        if snapshot is None or snapshot.tempo <= 0:
            return
        now_beat = local_beat_at(snapshot, snapshot.at)
        beats_per_frame = snapshot.tempo / 60.0 / audio.RATE
        if self._input is not None:
            block = self._input.read()
            if len(block):
                self.me_meter.setValue(int(audio.peak(block) * 100))
                start_beat = now_beat - len(block) * beats_per_frame
                packets = audio.packetize(
                    block, self._position, start_beat, snapshot.tempo, self.quality_combo.currentData()
                )
                self._position += len(block)
                if self.link is not None:
                    self.link.send(packets)
                if self._program is not None:
                    self._me_fifo = np.concatenate([self._me_fifo, block])[-audio.RATE :]
        driver = self._monitor or self._program
        if driver is None:
            return
        n = min(driver.free_frames(), MAX_BLOCK)
        if n < audio.PACKET_FRAMES:
            return
        delay_frames = driver.queued_frames() + self.nudge_spin.value() * audio.RATE // 1000
        them = self.player.read(n, now_beat + delay_frames * beats_per_frame)
        self.them_meter.setValue(int(self.player.last_peak * 100))
        if self._monitor is not None:
            self._monitor.write(them * (self.them_volume.value() / 100.0))
        if self._program is not None:
            me = self._me_fifo[:n]
            self._me_fifo = self._me_fifo[n:]
            if len(me) < n:
                me = np.concatenate([me, np.zeros((n - len(me), audio.CHANNELS), dtype=np.float32)])
            mix = audio.program_mix(
                me,
                them,
                self.me_volume.value() / 100.0,
                self.them_volume.value() / 100.0,
                self.crossfader.value() / 100.0,
            )
            if self._program.free_frames() >= len(mix):
                self._program.write(mix)

    def _show_status(self) -> None:
        player = self.player
        if player is None:
            return
        if self.link is not None and self.link.error:
            self.status_label.setText(self.tr("Network error: {error}").format(error=self.link.error))
        elif player.received == 0:
            self.status_label.setText(self.tr("Sound on. Nothing from the other DJ yet."))
        else:
            self.status_label.setText(
                self.tr("Their sound lands one bar late, on your grid. Gaps: {gaps:.1f} %").format(
                    gaps=player.gap_ratio() * 100
                )
            )

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)


__all__ = ["AudioDeviceError", "QtAudioBackend", "RemoteAudioPanel"]
