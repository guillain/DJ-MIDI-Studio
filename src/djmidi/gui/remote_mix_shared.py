"""The shared part of the Mix Together sound panel: the mixer every DJ moves
(phase 6, `SharedTable`), who is in the room (phase 9) and the régie that makes
and records the official mix (phase 7). A mixin of `RemoteAudioPanel`; its
strings keep that class's translation context."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QCoreApplication

from djmidi import user_paths
from djmidi.remote_mix import controls, recording, table

_LOGGER = logging.getLogger(__name__)

MASTER_UNITY = 80  # master and headphones knobs: 0 dB at 80, a little headroom above



class SharedMixerMixin:
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

    def _wire(self, target: str) -> str | None:
        """A local control ('them_low', 'x1', 'me_xf') → its name on the shared mixer ('dj2_low')."""
        if target in table.GLOBALS:
            return target  # the same name on every computer
        side, _, control = target.partition("_")
        dj = self.slot_dj.get(side)
        return None if dj is None else table.strip_control(dj, control or "volume")

    def _local(self, wire: str) -> str | None:
        if wire in table.GLOBALS:
            return wire
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
        if target == table.FX_BEATS:
            if 0 <= value < self.beats_combo.count():
                self.beats_combo.setCurrentIndex(value)
        elif target.endswith("_mute"):
            button = self.mute_buttons[target[:-5]]
            button.blockSignals(True)
            button.setChecked(bool(value))
            button.blockSignals(False)
        elif target.endswith("_xf"):
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
                self.names[side].setText(self._dj_name(dj, roster) if side != controls.ME else QCoreApplication.translate("RemoteAudioPanel", "Me"))
                if self.table is not None:  # what the room already set for this DJ
                    for control in ("volume", controls.GAIN, *controls.KNOBS, "mute"):
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
        return name or QCoreApplication.translate("RemoteAudioPanel", "DJ {number}").format(number=dj + 1)

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
            self.remote_label.setText(QCoreApplication.translate("RemoteAudioPanel", "Moved: {control}").format(control=self._caption(shown[-1])))

    @property
    def makes_the_mix(self) -> bool:
        """This computer makes the official mix: alone, or as the régie."""
        return self.table is None or self.table.regie_is_mine

    def claim_regie(self) -> None:
        if self.table is not None and self._send_mix is not None:
            self._send_mix(self.table.claim_regie())
        self._show_regie()

    def _show_regie(self) -> None:
        hosting = self.table is not None and self.table.me == table.HOST
        for button in self.mute_buttons.values():
            button.setEnabled(hosting)
            button.setVisible(self.table is not None)
        mine = self.makes_the_mix
        if self.table is None:
            self.regie_label.setText(QCoreApplication.translate("RemoteAudioPanel", "The official mix is made on this computer."))
        elif mine:
            self.regie_label.setText(QCoreApplication.translate("RemoteAudioPanel", "Control room: the official mix is made here."))
        else:
            self.regie_label.setText(
                QCoreApplication.translate("RemoteAudioPanel", "Control room: the official mix is made at {name}'s.").format(name=self._dj_name(self.table.regie))
            )
        self.regie_button.setVisible(self.table is not None and not mine)
        if not mine:
            self.stop_recording()
        self.record_button.setEnabled(mine and self.running)
        self.program_combo.setEnabled(mine and not self.running)
        self.record_button.setText(QCoreApplication.translate("RemoteAudioPanel", "Stop recording") if self.recorder is not None else QCoreApplication.translate("RemoteAudioPanel", "Record the mix"))

    def toggle_recording(self) -> None:
        if self.recorder is not None:
            self.stop_recording()
        elif self.running and self.makes_the_mix:
            folder = self._recordings_dir or user_paths.subfolder(user_paths.EXPORTS)
            started = datetime.now()  # noqa: DTZ005 - a local file name
            extension = self.format_combo.currentData()
            try:
                self.recorder = recording.open_recorder(folder / recording.recording_name(started, extension))
            except Exception as exc:  # noqa: BLE001 - a codec or disk problem must not stop the sound
                self.record_label.setText(QCoreApplication.translate("RemoteAudioPanel", "Recording not started: {error}").format(error=exc))
                self._show_regie()
                return
            if self.stems_checkbox.isChecked():
                self.stems = recording.StemsRecorder(folder, started, extension=extension)
            self.record_label.setText(QCoreApplication.translate("RemoteAudioPanel", "Recording to {path}").format(path=self.recorder.path))
        self._show_regie()

    def stop_recording(self) -> None:
        if self.recorder is None:
            return
        recorder, self.recorder = self.recorder, None
        recorder.close()
        text = QCoreApplication.translate("RemoteAudioPanel", "Recorded {minutes} min: {path}").format(minutes=round(recorder.seconds / 60, 1), path=recorder.path)
        if self.stems is not None:
            stems, self.stems = self.stems, None
            stems.close()
            text += " " + QCoreApplication.translate("RemoteAudioPanel", "(+ {count} track(s), one per DJ)").format(count=len(stems.paths))
        self.record_label.setText(text)
        if hasattr(self, "record_button"):
            self.record_button.setText(QCoreApplication.translate("RemoteAudioPanel", "Record the mix"))

    def _caption(self, wire: str) -> str:
        if wire == table.CROSSFADER:
            return QCoreApplication.translate("RemoteAudioPanel", "Crossfader")
        globals_ = {
            table.MASTER: QCoreApplication.translate("RemoteAudioPanel", "Master"),
            "fx_delay": QCoreApplication.translate("RemoteAudioPanel", "Delay"),
            table.FX_BEATS: QCoreApplication.translate("RemoteAudioPanel", "Delay time"),
            "fx_reverb": QCoreApplication.translate("RemoteAudioPanel", "Reverb"),
        }
        if wire in globals_:
            return globals_[wire]
        head, _, control = wire.partition("_")
        dj = int(head[2:]) if head[2:].isdigit() else None
        owner = QCoreApplication.translate("RemoteAudioPanel", "Me") if self.table is not None and dj == self.table.me else self._dj_name(dj or 0)
        names = {
            "low": QCoreApplication.translate("RemoteAudioPanel", "Low"),
            "mid": QCoreApplication.translate("RemoteAudioPanel", "Mid"),
            "high": QCoreApplication.translate("RemoteAudioPanel", "High"),
            "filter": QCoreApplication.translate("RemoteAudioPanel", "Filter"),
            "xf": QCoreApplication.translate("RemoteAudioPanel", "Crossfader side"),
            "mute": QCoreApplication.translate("RemoteAudioPanel", "Mute"),
            "gain": QCoreApplication.translate("RemoteAudioPanel", "Gain"),
        }
        return "{owner} · {control}".format(owner=owner, control=names.get(control, QCoreApplication.translate("RemoteAudioPanel", "Volume")))

