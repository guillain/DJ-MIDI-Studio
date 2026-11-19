"""The console part of the Mix Together sound panel: the master section (level,
meter, beat-synced effects, headphones), each strip's gain and mute, and MIDI
mode. A mixin of `RemoteAudioPanel`; its strings keep that class's
translation context."""

from __future__ import annotations

import logging

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDial,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from djmidi.gui.led_meter import LedMeter
from djmidi.remote_mix import controls, eq, fx, table

_LOGGER = logging.getLogger(__name__)

MASTER_UNITY = 80  # master and headphones knobs: 0 dB at 80, a little headroom above



class ConsoleMixin:
    def _knob(self, value: int, tooltip: str) -> QDial:
        dial = QDial()
        dial.setRange(0, 100)
        dial.setValue(value)
        dial.setNotchesVisible(True)
        dial.setFixedSize(46, 46)
        dial.setToolTip(tooltip)
        return dial

    def _build_master(self) -> QFrame:
        """The console's master section: the program level and meter; your headphones."""
        self.master_dial = self._knob(MASTER_UNITY, QCoreApplication.translate("RemoteAudioPanel", "Level of the official mix (the régie applies it)"))
        self._sliders[controls.MASTER] = self.master_dial
        self.master_dial.valueChanged.connect(lambda value: self._on_local_move(controls.MASTER, value))
        self.master_meter = LedMeter()
        self.master_meter.setMinimumHeight(70)
        self.master_meter.setFixedHeight(70)
        self.phones_mix = self._knob(0, QCoreApplication.translate("RemoteAudioPanel", "Headphones: the cue to the left, the room's sound to the right"))
        self.phones_level = self._knob(MASTER_UNITY, QCoreApplication.translate("RemoteAudioPanel", "Headphones level"))
        learn, forget = self._learn_pair(controls.MASTER)
        # Beat-synced effects on the official mix (shared, applied by the régie).
        self.delay_dial = self._knob(0, QCoreApplication.translate("RemoteAudioPanel", "Delay: echoes on the beat, at the session's tempo"))
        self.reverb_dial = self._knob(0, QCoreApplication.translate("RemoteAudioPanel", "Reverb: a room around the official mix"))
        self.beats_combo = QComboBox()
        for label, beats in zip((QCoreApplication.translate("RemoteAudioPanel", "1/2 beat"), QCoreApplication.translate("RemoteAudioPanel", "3/4 beat"), QCoreApplication.translate("RemoteAudioPanel", "1 beat"), QCoreApplication.translate("RemoteAudioPanel", "2 beats")), fx.DELAY_BEATS, strict=True):
            self.beats_combo.addItem(label, beats)
        self.beats_combo.setCurrentIndex(1)
        self.beats_combo.setToolTip(QCoreApplication.translate("RemoteAudioPanel", "Delay time, in beats"))
        self.beats_combo.currentIndexChanged.connect(lambda index: self._on_local_move(table.FX_BEATS, index))
        for target, dial in ((controls.FX_DELAY, self.delay_dial), (controls.FX_REVERB, self.reverb_dial)):
            self._sliders[target] = dial
            dial.valueChanged.connect(lambda value, t=target: self._on_local_move(t, value))
        self.fx = fx.MasterFx()
        row = QHBoxLayout()
        for caption, widget in (
            (QCoreApplication.translate("RemoteAudioPanel", "Master"), self.master_dial),
            (None, self.master_meter),
            (QCoreApplication.translate("RemoteAudioPanel", "Delay"), self.delay_dial),
            (None, self.beats_combo),
            (QCoreApplication.translate("RemoteAudioPanel", "Reverb"), self.reverb_dial),
            (QCoreApplication.translate("RemoteAudioPanel", "Cue / mix"), self.phones_mix),
            (QCoreApplication.translate("RemoteAudioPanel", "Phones"), self.phones_level),
        ):
            column = QVBoxLayout()
            column.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
            if caption:
                label = QLabel(caption)
                label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                column.addWidget(label)
            row.addLayout(column)
        pair = QVBoxLayout()
        pair.addWidget(learn)
        pair.addWidget(forget)
        row.addLayout(pair)
        row.addStretch(1)
        frame = QFrame()
        frame.setObjectName("mixStrip")  # the console's look
        frame.setLayout(row)
        return frame

    def _trim(self, side: str) -> float:
        """A strip's gain knob: -12 dB to +12 dB, 0 dB at noon."""
        return float(10 ** ((self.dials[f"{side}_gain"].value() - eq.CENTRE) / eq.CENTRE * 12 / 20))

    def _on_midi_mode(self, on: bool) -> None:
        if on:
            self.controls_hint.setText(QCoreApplication.translate("RemoteAudioPanel", "MIDI mode: click the knob or fader to drive from your controller."))
        else:
            self.learning = None
            self.controls_hint.setText(QCoreApplication.translate("RemoteAudioPanel", "Learn: move a fader or knob on your controller and it drives this mixer control."))
            self._show_controls()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        target = self._midi_targets.get(watched) if hasattr(self, "_midi_targets") else None
        if target is None or not self.midi_button.isChecked():
            return super().eventFilter(watched, event)
        if event.type() in (QEvent.Type.MouseButtonRelease, QEvent.Type.MouseMove, QEvent.Type.MouseButtonDblClick):
            return True  # the whole click picks the control, it never moves it
        if event.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(watched, event)
        self.learning = None
        self.toggle_learn(target)
        if self.learning == target:
            self.controls_hint.setText(
                QCoreApplication.translate("RemoteAudioPanel", "Now move a fader or knob of your controller for: {control}").format(control=self._target_name(target))
            )
        return True  # the click picks the control, it doesn't move it

    def _target_name(self, target: str) -> str:
        wire = self._wire(target)
        return self._caption(wire) if wire is not None else target

    def _gain(self, side: str) -> float:
        """A strip's fader, or nothing when the host muted that DJ."""
        return 0.0 if self.mute_buttons[side].isChecked() else self.faders[side].value() / 100.0

