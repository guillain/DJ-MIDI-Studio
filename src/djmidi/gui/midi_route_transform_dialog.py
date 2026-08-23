from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from djmidi.midi_router import MidiValueTransform
from djmidi.session_player import _parse_int


class MidiRouteTransformDialog(QDialog):
    """Edit a route's optional MidiValueTransform (channel remap, note/CC
    offset, invert value) — deliberately just these three knobs, see
    MidiValueTransform's docstring for the scope this stays within."""

    def __init__(self, transform: MidiValueTransform | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit route transform")
        transform = transform or MidiValueTransform()

        self._channel = QComboBox()
        self._channel.addItem("(unchanged)", None)
        for channel in range(1, 17):
            self._channel.addItem(str(channel), channel)
        self._channel.setCurrentIndex(max(self._channel.findData(transform.channel_override), 0))

        self._data1_offset = QLineEdit(str(transform.data1_offset))

        self._invert_data2 = QCheckBox("Invert value (127 - value)")
        self._invert_data2.setChecked(transform.invert_data2)

        form = QFormLayout()
        form.addRow("Channel override:", self._channel)
        form.addRow("Note/CC offset:", self._data1_offset)
        form.addRow(self._invert_data2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._result: MidiValueTransform | None = None

    def _on_accept(self) -> None:
        try:
            data1_offset = _parse_int(self._data1_offset.text(), "Note/CC offset", -127, 127)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid transform", str(exc))
            return
        transform = MidiValueTransform(
            channel_override=self._channel.currentData(),
            data1_offset=data1_offset,
            invert_data2=self._invert_data2.isChecked(),
        )
        # A transform equal to the no-op default behaves exactly like no
        # transform at all, so store None to keep the routes table's
        # "Transform" column reading "-" instead of a misleading entry.
        self._result = transform if transform != MidiValueTransform() else None
        self.accept()

    def result_transform(self) -> MidiValueTransform | None:
        return self._result


__all__ = ["MidiRouteTransformDialog"]
