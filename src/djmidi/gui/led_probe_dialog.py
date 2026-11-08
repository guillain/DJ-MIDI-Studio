"""Check one control's LED on the hardware and record what it does (Atelier,
issue #413, step 5).

The feature model only *assumes* where an LED answers (same channel and
note as the button). With the controller plugged in, this dialog sends LED
messages to it -- a value on the address being checked -- and lets you
record what you saw: the address that lights, the values for on and off,
and a name for each value that gives a colour. Saving writes a verified
`atelier.led_data.LedRecord`; the Atelier, the feature card and macros then
use it. Nothing is sent until you click a send button.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi.atelier.features import Feature
from djmidi.atelier.led_data import LedRecord, probe_source
from djmidi.controller_sync import ControllerSyncSet, resolve_output_port
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.midi_io import send_midi_message

Sender = Callable[..., None]  # send_midi_message's keyword arguments
_VALUE_ROLE = Qt.ItemDataRole.UserRole + 1


def _spin(low: int, high: int, value: int) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(value)
    return spin


class LedProbeDialog(QDialog):
    def __init__(
        self,
        feature: Feature,
        ports: Sequence[str],
        sender: Sender | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Probe the LED of {control}").format(control=feature.name))
        self.feature = feature
        self._sender = sender or send_midi_message
        led = feature.led

        intro = QLabel(
            self.tr(
                "With the controller plugged in, send a value and look at the control. Record what lights: "
                "the note that answers, the values for on and off, and a name for each value that gives a "
                "colour. Saving marks this LED as verified."
            )
        )
        intro.setWordWrap(True)

        self.port_combo = QComboBox()
        self.port_combo.addItems(list(ports))
        guess = resolve_output_port(ControllerSyncSet(feature.controller), list(ports))
        if guess:
            self.port_combo.setCurrentText(guess)

        self.channel_spin = _spin(1, 16, led.channel if led else feature.input.channel)
        self.note_spin = _spin(0, 127, led.note if led else feature.input.number)
        self.value_spin = _spin(0, 127, led.on_value if led else 127)
        self.on_spin = _spin(0, 127, led.on_value if led else 127)
        self.off_spin = _spin(0, 127, led.off_value if led else 0)
        self.send_button = QPushButton(self.tr("Send this value"))
        self.send_button.clicked.connect(lambda: self.send(self.value_spin.value()))
        self.off_button = QPushButton(self.tr("Send off"))
        self.off_button.clicked.connect(lambda: self.send(self.off_spin.value()))
        send_row = QHBoxLayout()
        send_row.addWidget(self.value_spin)
        send_row.addWidget(self.send_button)
        send_row.addWidget(self.off_button)

        self.colour_edit = QLineEdit()
        self.colour_edit.setPlaceholderText(self.tr("e.g. red, dim blue"))
        self.name_button = QPushButton(self.tr("Name this value"))
        self.name_button.clicked.connect(self._name_value)
        colour_row = QHBoxLayout()
        colour_row.addWidget(self.colour_edit, 1)
        colour_row.addWidget(self.name_button)
        self.colour_list = QListWidget()
        usable_minimum(self.colour_list, 260, 80)
        self.remove_button = QPushButton(self.tr("Remove colour"))
        self.remove_button.clicked.connect(self._remove_colour)
        if led is not None:
            for value, name in led.colours:
                self._add_colour(value, name)

        form = QFormLayout()
        form.addRow(self.tr("Output port"), self.port_combo)
        form.addRow(self.tr("Channel"), self.channel_spin)
        form.addRow(self.tr("Note"), self.note_spin)
        form.addRow(self.tr("Value to send"), send_row)
        form.addRow(self.tr("On value"), self.on_spin)
        form.addRow(self.tr("Off value"), self.off_spin)
        form.addRow(self.tr("Colour at this value"), colour_row)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.colour_list, 1)
        layout.addWidget(self.remove_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.status_label)
        layout.addWidget(self.buttons)
        fit_to_screen(self, 560, 560)
        keep_wrapped_text_visible(self)

    def send(self, value: int) -> bool:
        port = self.port_combo.currentText().strip()
        if not port:
            self.status_label.setText(self.tr("Pick the controller's output port first."))
            return False
        try:
            self._sender(
                output_port_name=port,
                event_type="Note On",
                channel_1_based=self.channel_spin.value(),
                data1=self.note_spin.value(),
                data2=value,
            )
        except Exception as exc:  # noqa: BLE001 - a test send must never crash the dialog
            self.status_label.setText(self.tr("Could not send: {error}").format(error=exc))
            return False
        self.status_label.setText(
            self.tr("Sent value {value} to channel {channel}, note {note}. What do you see?").format(
                value=value, channel=self.channel_spin.value(), note=self.note_spin.value()
            )
        )
        return True

    def _add_colour(self, value: int, name: str) -> None:
        for row in range(self.colour_list.count()):
            if self.colour_list.item(row).data(_VALUE_ROLE) == value:
                self.colour_list.takeItem(row)
                break
        item = QListWidgetItem(f"{value} — {name}")
        item.setData(_VALUE_ROLE, value)
        item.setData(_VALUE_ROLE + 1, name)
        self.colour_list.addItem(item)

    def _name_value(self) -> None:
        name = self.colour_edit.text().strip()
        if not name:
            return
        self._add_colour(self.value_spin.value(), name)
        self.colour_edit.clear()

    def _remove_colour(self) -> None:
        row = self.colour_list.currentRow()
        if row >= 0:
            self.colour_list.takeItem(row)

    def colours(self) -> dict[int, str]:
        return {
            self.colour_list.item(row).data(_VALUE_ROLE): self.colour_list.item(row).data(_VALUE_ROLE + 1)
            for row in range(self.colour_list.count())
        }

    def record(self) -> LedRecord:
        return LedRecord(
            self.feature.id,
            self.channel_spin.value(),
            self.note_spin.value(),
            self.on_spin.value(),
            self.off_spin.value(),
            self.colours(),
            probe_source(),
        )


__all__ = ["LedProbeDialog"]
