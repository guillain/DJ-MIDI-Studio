"""The display layers of every controller view, as one row of checkboxes.

Controller Images, the By Channel / By Deck / By Controller layouts and every
Controller Emulator draw up to three layers:

- **Controller**: the clean photo of the device (``reference.png``);
- **MIDI**: the same device with its MIDI message list callouts printed on it
  (``reference-midi.png``), when the controller ships one;
- **Layout**: the app's own markers at each control's measured position.

Only one photo shows at a time, so Controller and MIDI exclude each other
(either may also be off). The Layout markers were measured on the Controller
photo; a MIDI picture is a different crop, so Layout is greyed out while MIDI
is shown rather than drawn misaligned. That leaves photo only, layout only,
photo + layout, or MIDI only -- the maintainer's chosen rule.

A view tells the row which layers exist for the controller it shows
(``set_available``) and reads the effective layers back (``state``): a
layer counts only when it's both ticked and available. A ticked MIDI layer
on a controller without a MIDI picture falls back to the Controller photo,
so switching controllers never leaves an empty view by surprise.
"""

from __future__ import annotations

from typing import NamedTuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSizePolicy, QWidget


class LayerState(NamedTuple):
    photo: bool
    midi: bool
    layout: bool


class LayerToggles(QWidget):
    changed = Signal()

    def __init__(
        self,
        *,
        controller: bool = True,
        midi: bool = False,
        layout: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller_box = QCheckBox("Controller")
        self.controller_box.setToolTip("The real photo of the controller.")
        self.midi_box = QCheckBox("MIDI")
        self.midi_box.setToolTip("The controller photo with its MIDI information printed on it.")
        self.layout_box = QCheckBox("Layout")
        self.layout_box.setToolTip("The app's MIDI layout: a marker on every modeled control.")
        self.controller_box.setChecked(controller)
        self.midi_box.setChecked(midi and not controller)
        self.layout_box.setChecked(layout)
        self._available = LayerState(photo=True, midi=True, layout=True)

        # Packed together, never stretched across a wide row.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        for box in (self.controller_box, self.midi_box, self.layout_box):
            row.addWidget(box)
        self.controller_box.toggled.connect(self._on_controller_toggled)
        self.midi_box.toggled.connect(self._on_midi_toggled)
        self.layout_box.toggled.connect(lambda _checked: self.changed.emit())
        self._sync_enabled()

    def _on_controller_toggled(self, checked: bool) -> None:
        if checked and self.midi_box.isChecked():
            self.midi_box.blockSignals(True)
            self.midi_box.setChecked(False)
            self.midi_box.blockSignals(False)
        self._sync_enabled()
        self.changed.emit()

    def _on_midi_toggled(self, checked: bool) -> None:
        if checked and self.controller_box.isChecked():
            self.controller_box.blockSignals(True)
            self.controller_box.setChecked(False)
            self.controller_box.blockSignals(False)
        self._sync_enabled()
        self.changed.emit()

    def set_available(self, *, photo: bool, midi: bool, layout: bool) -> None:
        """Which layers the current controller can show at all."""
        self._available = LayerState(photo=photo, midi=midi, layout=layout)
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        available = self._available
        self.controller_box.setEnabled(available.photo)
        self.controller_box.setToolTip(
            "The real photo of the controller."
            if available.photo
            else "No measured layout to show a photo behind for this controller."
            " Controller Images shows its picture."
        )
        self.midi_box.setEnabled(available.midi)
        self.midi_box.setToolTip(
            "The controller photo with its MIDI information printed on it."
            if available.midi
            else "No MIDI picture is bundled for this controller."
        )
        midi_on = self.state().midi
        self.layout_box.setEnabled(available.layout and not midi_on)
        if not available.layout:
            self.layout_box.setToolTip("No layout has been measured for this controller yet.")
        elif midi_on:
            self.layout_box.setToolTip("The layout only lines up with the Controller photo: untick MIDI to show it.")
        else:
            self.layout_box.setToolTip("The app's MIDI layout: a marker on every modeled control.")

    def state(self) -> LayerState:
        """The layers to draw: ticked, available, and following the rules above."""
        available = self._available
        midi = self.midi_box.isChecked() and available.midi
        photo = available.photo and not midi and (
            self.controller_box.isChecked() or self.midi_box.isChecked()
        )
        layout = self.layout_box.isChecked() and available.layout and not midi
        return LayerState(photo=photo, midi=midi, layout=layout)


__all__ = ["LayerState", "LayerToggles"]
