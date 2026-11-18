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
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDial,
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

from djmidi import user_paths
from djmidi.remote_mix import audio, controls, eq, listen, opus, recording, table
from djmidi.remote_mix.probe import LinkSnapshot, local_beat_at

if TYPE_CHECKING:
    from djmidi.midi_io import MidiEvent

_LOGGER = logging.getLogger(__name__)

PICKUP_STEPS = 3  # a controller picks a control up within this many steps of it
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
        self.unavailable: str | None = None
        try:
            from PySide6.QtMultimedia import QAudioFormat
        except ImportError as exc:  # e.g. Linux without PulseAudio
            _LOGGER.warning("Qt Multimedia unavailable, no sound for Mix Together: %s", exc)
            self.unavailable = str(exc)
            return
        self._format = QAudioFormat()
        self._format.setSampleRate(audio.RATE)
        self._format.setChannelCount(audio.CHANNELS)
        self._format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

    @staticmethod
    def _devices(kind: str):
        from PySide6.QtMultimedia import QMediaDevices

        return QMediaDevices.audioInputs() if kind == "in" else QMediaDevices.audioOutputs()

    def inputs(self) -> list[str]:
        return [] if self.unavailable else [d.description() for d in self._devices("in")]

    def outputs(self) -> list[str]:
        return [] if self.unavailable else [d.description() for d in self._devices("out")]

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
        ensure_listening: Callable[[], bool] | None = None,
        controls_path: Path | None = None,
        recordings_dir: Path | None = None,
        listen_server_factory: Callable[..., listen.ListenerServer] = listen.ListenerServer,
    ) -> None:
        super().__init__(parent)
        self._recordings_dir = recordings_dir
        self._listen_server_factory = listen_server_factory
        self.listen_server: listen.ListenerServer | None = None
        self.setObjectName("remoteSound")
        self._ensure_listening = ensure_listening
        self._controls_path = controls_path or user_paths.workspace_dir() / controls.FILE_NAME
        self.controls = controls.MixerControls.load(self._controls_path)
        self.learning: str | None = None
        self._context = context
        self._backend = backend if backend is not None else QtAudioBackend()
        self._link_factory = link_factory
        self.players = audio.PlayerBank()
        self._roster: dict[int, str] = {}
        self.table: table.SharedTable | None = None
        self._applying_remote = False
        self.link: audio.AudioLink | None = None
        self._input: AudioInput | None = None
        self._monitor: AudioOutput | None = None
        self._program: AudioOutput | None = None
        self._reader: Callable[[], LinkSnapshot | None] | None = None
        self._position = 0
        self._send_buffer = audio.SendBuffer()
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
        if opus.unavailable() is None:
            self.quality_combo.addItem(self.tr("Compressed, Opus (about 0.25 Mb/s)"), audio.CODEC_OPUS)
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

        # The mixer table (shown at the centre of the Mix Together tab): one vertical
        # channel strip per DJ, like a club mixer, and the crossfader underneath.
        self.crossfader = QSlider(Qt.Orientation.Horizontal)
        self.crossfader.setRange(0, 100)
        self.crossfader.setValue(50)
        self.crossfader.setToolTip(self.tr("Program mix: strips on A to the left, on B to the right"))
        self.learn_buttons: dict[str, QPushButton] = {}
        self.forget_buttons: dict[str, QPushButton] = {}
        self.dials: dict[str, QDial] = {}
        self.flat_buttons: dict[str, QPushButton] = {}
        self.faders: dict[str, QSlider] = {}
        self.meters: dict[str, QProgressBar] = {}
        self.eqs: dict[str, eq.ChannelStrip] = {}
        self.names: dict[str, QLabel] = {}
        self.assigns: dict[str, QComboBox] = {}
        self.slot_frames: dict[str, QFrame] = {}
        # Slot → DJ id shown in it: me, the first other DJ, then up to two more (phase 9).
        self.slot_dj: dict[str, int | None] = {controls.ME: 0, controls.THEM: 1, "x1": None, "x2": None}
        self._sliders: dict[str, QWidget] = {controls.CROSSFADER: self.crossfader}
        captions = {"high": self.tr("High"), "mid": self.tr("Mid"), "low": self.tr("Low"), "filter": self.tr("Filter")}
        strips = QHBoxLayout()
        strips.setSpacing(18)
        for side in controls.SIDES:
            strip = self.eqs[side] = eq.ChannelStrip()
            fader, meter = self._fader(), self._meter()
            self.faders[side], self.meters[side] = fader, meter
            self._sliders[side] = fader
            name = self.names[side] = QLabel(self.tr("Me") if side == controls.ME else self.tr("Them"))
            column = self.slot_frames[side] = QFrame()
            column.setObjectName("mixStrip")
            box = QVBoxLayout(column)
            name.setObjectName("mixStripName")
            name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            box.addWidget(name)
            knobs = QGridLayout()
            knobs.setHorizontalSpacing(4)
            for row, knob in enumerate(("high", "mid", "low", "filter")):  # top to bottom, as on a mixer
                target = f"{side}_{knob}"
                dial = QDial()
                dial.setRange(0, 100)
                dial.setValue(eq.CENTRE)
                dial.setNotchesVisible(True)
                dial.setFixedSize(46, 46)
                dial.setToolTip(
                    self.tr("Filter: low-pass to the left, high-pass to the right, off at noon")
                    if knob == "filter"
                    else self.tr("Full cut to the left, +6 dB to the right, flat at noon")
                )
                dial.valueChanged.connect(lambda value, s=strip, k=knob: setattr(s, k, float(value)))
                self.dials[target] = dial
                learn, forget = self._learn_pair(target)
                knobs.addWidget(QLabel(captions[knob]), row, 0)
                knobs.addWidget(dial, row, 1)
                knobs.addWidget(learn, row, 2)
                knobs.addWidget(forget, row, 3)
            box.addLayout(knobs)
            flat = QPushButton(self.tr("Flat"))
            flat.setToolTip(self.tr("Back to noon: EQ flat, filter off"))
            flat.clicked.connect(lambda _checked=False, s=side: self.flatten(s))
            self.flat_buttons[side] = flat
            box.addWidget(flat)
            level = QHBoxLayout()
            level.addStretch(1)
            level.addWidget(meter)
            level.addWidget(fader)
            level.addStretch(1)
            box.addLayout(level, 1)
            assign = self.assigns[side] = QComboBox()
            for label, value in ((self.tr("A"), table.XF_A), (self.tr("Thru"), table.XF_THRU), (self.tr("B"), table.XF_B)):
                assign.addItem(label, value)
            assign.setToolTip(self.tr("Crossfader side for this strip: A (left), B (right) or Thru (not crossfaded)"))
            assign.currentIndexChanged.connect(lambda index, s=side: self._on_assign_changed(s, index))
            box.addWidget(assign)
            learn, forget = self._learn_pair(side)
            pair = QHBoxLayout()
            pair.addWidget(learn, 1)
            pair.addWidget(forget)
            box.addLayout(pair)
            strips.addWidget(column, 1)
            column.setVisible(side in (controls.ME, controls.THEM))
        self._set_default_assigns()
        cross = QHBoxLayout()
        cross.addWidget(QLabel(self.tr("Crossfader")))
        cross.addWidget(self.crossfader, 1)
        learn, forget = self._learn_pair(controls.CROSSFADER)
        cross.addWidget(learn)
        cross.addWidget(forget)
        self._sliders.update(self.dials)
        # The shared mixer (phase 6): every move here goes to the other DJ.
        self.table: table.SharedTable | None = None
        self._send_mix: Callable[[dict], None] | None = None
        self._applying_remote = False
        self._needs_pickup: set[str] = set()
        self._hardware_last: dict[str, int] = {}
        for target, widget in self._sliders.items():
            widget.valueChanged.connect(lambda value, t=target: self._on_local_move(t, value))
        self.remote_label = QLabel()
        self.remote_label.setObjectName("remoteMove")
        self.remote_label.setWordWrap(True)
        self.controls_hint = QLabel(
            self.tr("Learn: move a fader or knob on your controller and it drives this mixer control.")
        )
        self.controls_hint.setWordWrap(True)
        self._show_controls()
        self.table_widget = QFrame()
        self.table_widget.setObjectName("mixTable")
        table_box = QVBoxLayout(self.table_widget)
        table_title = QLabel(self.tr("The mixer"))
        table_title.setObjectName("remoteSoundTitle")
        table_box.addWidget(table_title)
        # The régie (phase 7): the one computer that makes the official mix.
        self.recorder: recording.ProgramRecorder | None = None
        self.regie_label = QLabel()
        self.regie_label.setObjectName("regieLabel")
        self.regie_label.setWordWrap(True)
        self.regie_button = QPushButton(self.tr("Make this computer the control room"))
        self.regie_button.setToolTip(
            self.tr("The official mix (program output and recording) is then made here, not at the other DJ's")
        )
        self.regie_button.clicked.connect(self.claim_regie)
        self.record_button = QPushButton(self.tr("Record the mix"))
        self.record_button.setToolTip(self.tr("Records the official mix to a WAV file in your Exports folder"))
        self.record_button.clicked.connect(self.toggle_recording)
        self.record_label = QLabel()
        self.record_label.setWordWrap(True)
        self.record_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        regie_row = QHBoxLayout()
        regie_row.addWidget(self.regie_label, 1)
        regie_row.addWidget(self.regie_button)
        regie_row.addWidget(self.record_button)
        self.listeners_label = QLabel()
        self.listeners_label.setObjectName("listenersLabel")
        regie_row.addWidget(self.listeners_label)
        table_box.addLayout(regie_row)
        table_box.addWidget(self.record_label)
        self._show_regie()
        table_box.addLayout(strips, 1)
        table_box.addLayout(cross)
        table_box.addWidget(self.remote_label)
        table_box.addWidget(self.controls_hint)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table_widget)  # the Mix Together tab moves it to its centre

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

    def _fader(self) -> QSlider:
        slider = QSlider(Qt.Orientation.Vertical)
        slider.setMinimumHeight(140)
        slider.setRange(0, 150)
        slider.setValue(100)
        slider.setToolTip(self.tr("Volume"))
        return slider

    @staticmethod
    def _meter() -> QProgressBar:
        meter = QProgressBar()
        meter.setRange(0, 100)
        meter.setTextVisible(False)
        meter.setOrientation(Qt.Orientation.Vertical)
        meter.setFixedWidth(10)
        meter.setMinimumHeight(140)
        return meter

    def _learn_pair(self, target: str) -> tuple[QPushButton, QPushButton]:
        learn = QPushButton()
        learn.setObjectName("chip")
        learn.clicked.connect(lambda _checked=False, t=target: self.toggle_learn(t))
        forget = QPushButton("✕")
        forget.setObjectName("chip")
        forget.setToolTip(self.tr("Forget this controller assignment"))
        forget.setAccessibleName(self.tr("Forget this controller assignment"))
        forget.setMaximumWidth(40)
        forget.clicked.connect(lambda _checked=False, t=target: self.forget(t))
        self.learn_buttons[target] = learn
        self.forget_buttons[target] = forget
        return learn, forget

    def flatten(self, side: str) -> None:
        for knob in controls.KNOBS:
            self.dials[f"{side}_{knob}"].setValue(eq.CENTRE)

    def _show_controls(self) -> None:
        for target in controls.TARGETS:
            trigger = self.controls.bindings.get(target)
            button = self.learn_buttons[target]
            if self.learning == target:
                button.setText(self.tr("Move it now…"))
                button.setToolTip(self.tr("Move a fader or knob on your controller, or click again to cancel"))
            elif trigger is None:
                button.setText(self.tr("Learn"))
                button.setToolTip(self.tr("Drive this mixer control from a fader or knob of your controller"))
            else:
                button.setText(trigger.label())
                button.setToolTip(self.tr("Driven by your controller. Click to learn another control"))
            self.forget_buttons[target].setEnabled(trigger is not None)

    def toggle_learn(self, target: str) -> None:
        if self.learning == target:
            self.learning = None
        else:
            self.learning = target
            if self._ensure_listening is not None and not self._ensure_listening():
                self.learning = None
                self.controls_hint.setText(
                    self.tr("No controller is plugged in: plug one in, then press Learn again.")
                )
        self._show_controls()

    def forget(self, target: str) -> None:
        self.controls.forget(target)
        self._save_controls()
        self._show_controls()

    def _save_controls(self) -> None:
        try:
            self.controls.save(self._controls_path)
        except OSError as exc:
            _LOGGER.warning("Mix Together controls not saved: %s", exc)

    def listen_to_controller(self) -> None:
        """Make sure assigned controls reach the mixer (the Live Monitor listens)."""
        if self.controls.bindings and self._ensure_listening is not None:
            self._ensure_listening()

    def feed_midi_event(self, event: MidiEvent) -> bool:
        """A live MIDI event: learn it, or move the mixer. True when it was used."""
        if self.learning is not None:
            trigger = controls.trigger_from_event(event)
            if trigger is None:
                return False
            target, self.learning = self.learning, None
            self.controls.bind(target, trigger)
            self._save_controls()
            self.controls_hint.setText(
                self.tr("{control} now drives this mixer control.").format(control=trigger.label())
            )
            self._show_controls()
        moves = self.controls.moves(event)
        for target, value in moves:
            slider = self._sliders[target]
            top = 100 if target != controls.CROSSFADER else slider.maximum()
            wanted = round(value * top)
            last, self._hardware_last[target] = self._hardware_last.get(target), wanted
            if target in self._needs_pickup:
                # The other DJ moved it: wait until your control reaches it, so the sound doesn't jump.
                current = slider.value()
                crossed = last is not None and (last - current) * (wanted - current) <= 0
                if abs(wanted - current) > PICKUP_STEPS and not crossed:
                    continue
                self._needs_pickup.discard(target)
            slider.setValue(wanted)
        return bool(moves)

    # -- the shared mixer (phase 6) ---------------------------------------

    def attach_table(self, me: int, send: Callable[[dict], None]) -> None:
        """Share this mixer with the other DJs (``me`` is this computer's DJ id)."""
        self.table = table.SharedTable(me)
        self._send_mix = send
        if self.slot_dj[controls.ME] != me:
            self.set_roster(me, {})
        self._show_regie()

    def detach_table(self) -> None:
        self.table = None
        self._send_mix = None
        self._needs_pickup.clear()
        self.remote_label.setText("")
        self._show_regie()

    # -- slots ↔ DJs (phase 9) ----------------------------------------------

    def _wire(self, target: str) -> str | None:
        """A local control ('them_low', 'x1', 'me_xf') → its name on the shared mixer ('dj2_low')."""
        if target == controls.CROSSFADER:
            return table.CROSSFADER
        side, _, control = target.partition("_")
        dj = self.slot_dj.get(side)
        return None if dj is None else table.strip_control(dj, control or "volume")

    def _local(self, wire: str) -> str | None:
        if wire == table.CROSSFADER:
            return controls.CROSSFADER
        head, _, control = wire.partition("_")
        for side, dj in self.slot_dj.items():
            if dj is not None and head == f"dj{dj}":
                return side if control == "volume" else f"{side}_{control}"
        return None

    def _widget_value(self, target: str) -> int:
        if target.endswith("_xf"):
            return self.assigns[target[:-3]].currentData()
        return self._sliders[target].value()

    def _set_widget(self, target: str, value: int) -> None:
        if target.endswith("_xf"):
            combo = self.assigns[target[:-3]]
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)
        elif target in self._sliders:
            self._sliders[target].setValue(value)

    def _set_default_assigns(self) -> None:
        self._applying_remote = True
        try:
            for side, dj in self.slot_dj.items():
                if dj is not None:
                    known = self.table.values.get(table.strip_control(dj, "xf")) if self.table is not None else None
                    self._set_widget(f"{side}_xf", table.default_assign(dj) if known is None else known)
        finally:
            self._applying_remote = False

    def set_roster(self, me: int, roster: dict[int, str]) -> None:
        """Who is in the room: your strip, then the others by DJ id (up to three)."""
        others = sorted(dj for dj in roster if dj != me) or [dj for dj in (1, 0) if dj != me][:1]
        slots = {controls.ME: me}
        for side, dj in zip((controls.THEM, "x1", "x2"), [*others, None, None, None], strict=False):
            slots[side] = dj
        if slots == self.slot_dj and all(self.names[s].text() == self._dj_name(d, roster) for s, d in slots.items() if d is not None):
            return
        self.slot_dj = slots
        self._roster = dict(roster)
        self._applying_remote = True
        try:
            for side, dj in slots.items():
                self.slot_frames[side].setVisible(dj is not None and (side in (controls.ME, controls.THEM) or bool(roster)))
                if dj is None:
                    continue
                self.names[side].setText(self._dj_name(dj, roster) if side != controls.ME else self.tr("Me"))
                if self.table is not None:  # what the room already set for this DJ
                    for control in ("volume", *controls.KNOBS):
                        value = self.table.values.get(table.strip_control(dj, control))
                        if value is not None:
                            self._set_widget(side if control == "volume" else f"{side}_{control}", value)
        finally:
            self._applying_remote = False
        self._set_default_assigns()
        self._show_regie()

    def _dj_name(self, dj: int, roster: dict[int, str] | None = None) -> str:
        roster = self._roster if roster is None else roster
        name = (roster or {}).get(dj) or ""
        return name or self.tr("DJ {number}").format(number=dj + 1)

    def _on_assign_changed(self, side: str, _index: int) -> None:
        self._on_local_move(f"{side}_xf", self.assigns[side].currentData())

    def _on_local_move(self, target: str, value: int) -> None:
        if self._applying_remote or self.table is None or self._send_mix is None:
            return
        wire = self._wire(target)
        if wire is not None:
            self._send_mix(self.table.local_change(wire, value))

    def send_snapshot(self) -> None:
        if self.table is not None and self._send_mix is not None:
            message = self.table.snapshot()
            if message is not None:
                self._send_mix(message)

    def apply_remote(self, message: dict) -> None:
        """Another DJ moved the shared mixer: show it here."""
        if self.table is None:
            return
        changes = self.table.receive(message)
        self._show_regie()
        shown = []
        self._applying_remote = True
        try:
            for wire, value in changes:
                target = self._local(wire)
                if target is None:
                    continue
                self._set_widget(target, value)
                self._needs_pickup.add(target)
                shown.append(wire)
        finally:
            self._applying_remote = False
        if shown:
            self.remote_label.setText(self.tr("Moved: {control}").format(control=self._caption(shown[-1])))

    # -- the régie (phase 7) ----------------------------------------------

    @property
    def makes_the_mix(self) -> bool:
        """This computer makes the official mix: alone, or as the régie."""
        return self.table is None or self.table.regie_is_mine

    def claim_regie(self) -> None:
        if self.table is not None and self._send_mix is not None:
            self._send_mix(self.table.claim_regie())
        self._show_regie()

    def _show_regie(self) -> None:
        mine = self.makes_the_mix
        if self.table is None:
            self.regie_label.setText(self.tr("The official mix is made on this computer."))
        elif mine:
            self.regie_label.setText(self.tr("Control room: the official mix is made here."))
        else:
            self.regie_label.setText(
                self.tr("Control room: the official mix is made at {name}'s.").format(name=self._dj_name(self.table.regie))
            )
        self.regie_button.setVisible(self.table is not None and not mine)
        if not mine:
            self.stop_recording()
        self.record_button.setEnabled(mine and self.running)
        self.program_combo.setEnabled(mine and not self.running)
        self.record_button.setText(self.tr("Stop recording") if self.recorder is not None else self.tr("Record the mix"))

    def toggle_recording(self) -> None:
        if self.recorder is not None:
            self.stop_recording()
        elif self.running and self.makes_the_mix:
            folder = self._recordings_dir or user_paths.subfolder(user_paths.EXPORTS)
            started = datetime.now()  # noqa: DTZ005 - a local file name
            self.recorder = recording.ProgramRecorder(folder / recording.recording_name(started))
            self.record_label.setText(self.tr("Recording to {path}").format(path=self.recorder.path))
        self._show_regie()

    def stop_recording(self) -> None:
        if self.recorder is None:
            return
        recorder, self.recorder = self.recorder, None
        recorder.close()
        self.record_label.setText(
            self.tr("Recorded {minutes} min: {path}").format(minutes=round(recorder.seconds / 60, 1), path=recorder.path)
        )
        if hasattr(self, "record_button"):
            self.record_button.setText(self.tr("Record the mix"))

    def _caption(self, wire: str) -> str:
        if wire == table.CROSSFADER:
            return self.tr("Crossfader")
        head, _, control = wire.partition("_")
        dj = int(head[2:]) if head[2:].isdigit() else None
        owner = self.tr("Me") if self.table is not None and dj == self.table.me else self._dj_name(dj or 0)
        names = {
            "low": self.tr("Low"),
            "mid": self.tr("Mid"),
            "high": self.tr("High"),
            "filter": self.tr("Filter"),
            "xf": self.tr("Crossfader side"),
        }
        return "{owner} · {control}".format(owner=owner, control=names.get(control, self.tr("Volume")))

    # -- compatibility names for the first two strips ----------------------

    @property
    def me_volume(self) -> QSlider:
        return self.faders[controls.ME]

    @property
    def them_volume(self) -> QSlider:
        return self.faders[controls.THEM]

    @property
    def me_meter(self) -> QProgressBar:
        return self.meters[controls.ME]

    @property
    def them_meter(self) -> QProgressBar:
        return self.meters[controls.THEM]

    @property
    def me_strip(self) -> eq.ChannelStrip:
        return self.eqs[controls.ME]

    @property
    def them_strip(self) -> eq.ChannelStrip:
        return self.eqs[controls.THEM]

    @property
    def them_name(self) -> QLabel:
        return self.names[controls.THEM]

    @property
    def player(self) -> audio.BarAlignedPlayer | None:
        """The first other DJ's player, while the sound runs."""
        dj = self.slot_dj[controls.THEM]
        return None if self._reader is None or dj is None else self.players.get(dj)

    @property
    def running(self) -> bool:
        return self._reader is not None

    def set_peer_name(self, name: str) -> None:
        self.them_name.setText(name)
        dj = self.slot_dj[controls.THEM]
        if dj is not None:
            self._roster = {**self._roster, dj: name}
        self._show_regie()

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
        host, port, reader, *rest = context
        session = rest[0] if rest else None
        self.players = audio.PlayerBank()
        try:
            if session is None:  # two DJs, the plain way
                link = self._link_factory(port=port, peer=(host, port), player=self.players.get(self.slot_dj[controls.THEM] or 1))
            else:  # a star around the host (phase 9)
                link = self._link_factory(
                    port=port,
                    peer=(host, port),
                    players=self.players,
                    peer_ids=session.peer_ids,
                    hub=session.peer_ids is not None and session.my_id == table.HOST,
                    me=lambda: session.my_id,
                )
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
        self.link, self._reader = link, reader
        try:  # listeners hear the official mix on the test port + 2 (phase 8)
            self.listen_server = self._listen_server_factory(port=port - audio.AUDIO_PORT_OFFSET + listen.LISTEN_PORT_OFFSET)
        except OSError as exc:
            _LOGGER.warning("Mix Together: no listener port: %s", exc)
            self.listen_server = None
        self._position = 0
        self._send_buffer = audio.SendBuffer()
        self._me_fifo = np.zeros((0, audio.CHANNELS), dtype=np.float32)
        for widget in (self.input_combo, self.monitor_combo, self.program_combo, self.quality_combo):
            widget.setEnabled(False)
        self.start_button.setText(self.tr("Stop the sound"))
        self._timer.start()
        self._status_timer.start()
        self._show_status()
        self.listen_to_controller()
        self._show_regie()
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._status_timer.stop()
        for device in (self._input, self._monitor, self._program):
            if device is not None:
                device.close()
        if self.link is not None:
            self.link.close()
        if self.listen_server is not None:
            self.listen_server.close()
            self.listen_server = None
        self._input = self._monitor = self._program = None
        self.link = self._reader = None
        for widget in (self.input_combo, self.monitor_combo, self.program_combo, self.quality_combo):
            widget.setEnabled(True)
        self.start_button.setText(self.tr("Start the sound"))
        self.stop_recording()
        self._show_regie()
        self.status_label.setText(self.tr("Sound off."))
        for meter in self.meters.values():
            meter.setValue(0)

    def pump(self) -> None:
        if self._reader is None:
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
                packets = self._send_buffer.add(
                    block, self._position, start_beat, snapshot.tempo, self.quality_combo.currentData()
                )
                self._position += len(block)
                if self.link is not None:
                    self.link.send(packets)
                if self._mixing():
                    self._me_fifo = np.concatenate([self._me_fifo, block])[-audio.RATE :]
        driver = self._monitor or self._program
        if driver is None:
            return
        n = min(driver.free_frames(), MAX_BLOCK)
        if n < audio.PACKET_FRAMES:
            return
        delay_frames = driver.queued_frames() + self.nudge_spin.value() * audio.RATE // 1000
        heard_beat = now_beat + delay_frames * beats_per_frame
        others: list[tuple[str, np.ndarray]] = []  # each other DJ, one bar late, through their strip's EQ
        for side, dj in self.slot_dj.items():
            if side == controls.ME or dj is None:
                continue
            player = self.players.get(dj)
            others.append((side, self.eqs[side].process(player.read(n, heard_beat))))
            self.meters[side].setValue(int(player.last_peak * 100))
        if self._monitor is not None:
            monitor = np.zeros((n, audio.CHANNELS), dtype=np.float32)
            for side, samples in others:
                monitor += samples * (self.faders[side].value() / 100.0)
            self._monitor.write(np.clip(monitor, -1.0, 1.0))
        if self._mixing() and self.makes_the_mix:
            me = self._me_fifo[:n]
            self._me_fifo = self._me_fifo[n:]
            if len(me) < n:
                me = np.concatenate([me, np.zeros((n - len(me), audio.CHANNELS), dtype=np.float32)])
            strips = [(self.me_strip.process(me), self.me_volume.value() / 100.0, self.assigns[controls.ME].currentData())]
            strips += [(samples, self.faders[side].value() / 100.0, self.assigns[side].currentData()) for side, samples in others]
            mix = audio.mix_strips(strips, self.crossfader.value() / 100.0, n)
            if self._program is not None and self._program.free_frames() >= len(mix):
                self._program.write(mix)
            if self.recorder is not None:
                self.recorder.write(mix)
            if self.listen_server is not None:
                self.listen_server.send_mix(mix)

    def _mixing(self) -> bool:
        """Whether the official mix is needed: an output, a recording or listeners."""
        listeners = self.listen_server is not None and bool(self.listen_server.listeners())
        return self._program is not None or self.recorder is not None or listeners

    def _show_status(self) -> None:
        if self._reader is None:
            return
        count = len(self.listen_server.listeners()) if self.listen_server is not None else 0
        self.listeners_label.setText(
            self.tr("{count} listening").format(count=count) if count and self.makes_the_mix else ""
        )
        players = [player for _dj, player in self.players.items()]
        received = sum(player.received for player in players)
        played = sum(player.played for player in players)
        missing = sum(player.missing for player in players)
        if self.link is not None and self.link.error:
            self.status_label.setText(self.tr("Network error: {error}").format(error=self.link.error))
        elif received == 0:
            self.status_label.setText(self.tr("Sound on. Nothing from the other DJ yet."))
        else:
            self.status_label.setText(
                self.tr("Their sound lands one bar late, on your grid. Gaps: {gaps:.1f} %").format(
                    gaps=(missing / played * 100) if played else 0.0
                )
            )

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)


__all__ = ["AudioDeviceError", "QtAudioBackend", "RemoteAudioPanel"]
