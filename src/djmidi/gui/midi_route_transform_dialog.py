from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
)

from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.i18n import QT_TRANSLATE_NOOP
from djmidi.midi_learn import LEARN_TIMEOUT_MS, trigger_from_event
from djmidi.midi_router import BLOCK, CC, NOTE, MidiValueTransform, RemapRule

_REMAP_COLUMNS = (
    QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "From"),
    QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "Ch"),
    QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "No."),
    QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "To"),
    QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "Ch"),
    QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "No."),
)
_KINDS = ((NOTE, QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "Note")), (CC, "CC"))
_BLOCKED = QT_TRANSLATE_NOOP("MidiRouteTransformDialog", "Blocked")


class MidiRouteTransformDialog(QDialog):
    """Edit a route's optional MidiValueTransform: the stream-wide channel
    remap, note/CC offset and value inversion, plus per-control remaps
    (issue #368) -- one control in, another out (or blocked), with MIDI
    Learn for the control pressed. Learn opens no port: the routing view
    passes ``ensure_listening`` and the main window feeds live events to
    :meth:`feed_learn_event`."""

    def __init__(
        self,
        transform: MidiValueTransform | None,
        parent=None,
        ensure_listening: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit route transform"))
        transform = transform or MidiValueTransform()
        self._ensure_listening = ensure_listening
        self._learn_row: int | None = None
        self._learn_timer = QTimer(self)
        self._learn_timer.setSingleShot(True)
        self._learn_timer.setInterval(LEARN_TIMEOUT_MS)
        self._learn_timer.timeout.connect(lambda: self.cancel_learn(self.tr("No control pressed — Learn timed out.")))

        self._channel = QComboBox()
        self._channel.addItem(self.tr("(unchanged)"), None)
        for channel in range(1, 17):
            self._channel.addItem(str(channel), channel)
        self._channel.setCurrentIndex(max(self._channel.findData(transform.channel_override), 0))

        self._data1_offset = QLineEdit(str(transform.data1_offset))

        self._invert_data2 = QCheckBox(self.tr("Invert value (127 - value)"))
        self._invert_data2.setChecked(transform.invert_data2)

        form = QFormLayout()
        form.addRow(self.tr("Channel override:"), self._channel)
        form.addRow(self.tr("Note/CC offset:"), self._data1_offset)
        form.addRow(self._invert_data2)

        remap_title = QLabel(
            self.tr(
                "Remap controls: each row sends another note or CC instead of one control (or blocks it); "
                "the value is kept. Rows win over the settings above. Route the controller to "
                "“DJ MIDI Studio Remap” and pick that port in your DJ software instead of the controller."
            )
        )
        remap_title.setWordWrap(True)
        self.remap_table = QTableWidget(0, len(_REMAP_COLUMNS))
        self.remap_table.setHorizontalHeaderLabels([self.tr(column) for column in _REMAP_COLUMNS])
        self.remap_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.remap_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.remap_table.verticalHeader().setVisible(False)
        # Rows as tall as their combos and spin boxes need.
        self.remap_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header = self.remap_table.horizontalHeader()
        for column in range(len(_REMAP_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        # No stretched column: a narrow window scrolls the table sideways
        # instead of squeezing a combo below its text.
        usable_minimum(self.remap_table, 420, 140)
        self.add_button = QPushButton(self.tr("Add remap"))
        self.add_button.clicked.connect(lambda: self.add_rule(None))
        self.learn_button = QPushButton(self.tr("Learn"))
        self.learn_button.setToolTip(self.tr("Press the control to remap on your controller"))
        self.learn_button.setEnabled(ensure_listening is not None)
        self.learn_button.clicked.connect(self._on_learn_clicked)
        self.remove_button = QPushButton(self.tr("Remove"))
        self.remove_button.clicked.connect(self._remove_selected)
        remap_buttons = QHBoxLayout()
        for button in (self.add_button, self.learn_button, self.remove_button):
            remap_buttons.addWidget(button)
        remap_buttons.addStretch(1)
        self.status = QLabel("")
        self.status.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(remap_title)
        layout.addWidget(self.remap_table, 1)
        layout.addLayout(remap_buttons)
        layout.addWidget(self.status)
        layout.addWidget(buttons)

        for rule in transform.remaps:
            self.add_rule(rule)
        self._result: MidiValueTransform | None = None
        fit_to_screen(self, 640, 520)
        keep_wrapped_text_visible(self)

    # --- remap rows -------------------------------------------------------------

    def _kind_combo(self, blockable: bool, value: str) -> QComboBox:
        combo = QComboBox()
        for key, label in _KINDS:
            combo.addItem(self.tr(label), key)
        if blockable:
            combo.addItem(self.tr(_BLOCKED), BLOCK)
        combo.setCurrentIndex(max(combo.findData(value), 0))
        return combo

    @staticmethod
    def _spin(low: int, high: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        return spin

    def add_rule(self, rule: RemapRule | None) -> int:
        rule = rule or RemapRule(NOTE, 1, 0, NOTE, 1, 0)
        row = self.remap_table.rowCount()
        self.remap_table.insertRow(row)
        widgets = (
            self._kind_combo(False, rule.source_kind),
            self._spin(1, 16, rule.source_channel),
            self._spin(0, 127, rule.source_data1),
            self._kind_combo(True, rule.target_kind),
            self._spin(1, 16, rule.target_channel),
            self._spin(0, 127, rule.target_data1),
        )
        for column, widget in enumerate(widgets):
            self.remap_table.setCellWidget(row, column, widget)
        self.remap_table.selectRow(row)
        return row

    def rules(self) -> tuple[RemapRule, ...]:
        rules = []
        for row in range(self.remap_table.rowCount()):
            cells = [self.remap_table.cellWidget(row, column) for column in range(len(_REMAP_COLUMNS))]
            rules.append(
                RemapRule(
                    cells[0].currentData(),
                    cells[1].value(),
                    cells[2].value(),
                    cells[3].currentData(),
                    cells[4].value(),
                    cells[5].value(),
                )
            )
        return tuple(rules)

    def _remove_selected(self) -> None:
        row = self.remap_table.currentRow()
        if row >= 0:
            self.cancel_learn(None)
            self.remap_table.removeRow(row)

    # --- MIDI Learn -------------------------------------------------------------

    @property
    def is_learning(self) -> bool:
        return self._learn_row is not None

    def _on_learn_clicked(self) -> None:
        if self.is_learning:
            self.cancel_learn()
            return
        if self._ensure_listening is None:
            return
        if not self._ensure_listening():
            self.status.setText(self.tr("No MIDI input is open: connect a controller, or pick one in Live Monitor."))
            return
        row = self.remap_table.currentRow()
        if row < 0:
            row = self.add_rule(None)
        self._learn_row = row
        self.learn_button.setText(self.tr("Cancel"))
        self.status.setText(self.tr("Press the control to remap…"))
        self._learn_timer.start()

    def cancel_learn(self, message: str | None = "") -> None:
        if not self.is_learning:
            return
        self._learn_row = None
        self._learn_timer.stop()
        self.learn_button.setText(self.tr("Learn"))
        if message == "":
            message = self.tr("Learn cancelled.")
        if message is not None:
            self.status.setText(message)

    def feed_learn_event(self, event) -> bool:
        """Every live event while the dialog is open; True when Learn used it."""
        if not self.is_learning:
            return False
        learned = trigger_from_event(event)
        if learned is None:
            return False
        row = self._learn_row
        self.cancel_learn(None)
        if row is None or row >= self.remap_table.rowCount():
            return True
        kind = NOTE if learned.event_type == "Note On" else CC
        source_kind = self.remap_table.cellWidget(row, 0)
        source_kind.setCurrentIndex(max(source_kind.findData(kind), 0))
        self.remap_table.cellWidget(row, 1).setValue(int(learned.channel))
        self.remap_table.cellWidget(row, 2).setValue(int(learned.control))
        self.status.setText(
            self.tr("Learned {kind} {number} on channel {channel}.").format(
                kind=self.tr("Note") if kind == NOTE else "CC", number=learned.control, channel=learned.channel
            )
        )
        return True

    # --- result -------------------------------------------------------------------

    def done(self, result: int) -> None:
        self.cancel_learn(None)
        super().done(result)

    def _on_accept(self) -> None:
        try:
            data1_offset = int(self._data1_offset.text().strip())
        except ValueError:
            data1_offset = None
        if data1_offset is None or not -127 <= data1_offset <= 127:
            QMessageBox.warning(
                self,
                self.tr("Invalid transform"),
                self.tr("Note/CC offset must be a whole number from -127 to 127."),
            )
            return
        rules = self.rules()
        sources = [(rule.source_kind, rule.source_channel, rule.source_data1) for rule in rules]
        if len(set(sources)) != len(sources):
            self.status.setText(self.tr("Two rows remap the same control: keep one."))
            return
        transform = MidiValueTransform(
            channel_override=self._channel.currentData(),
            data1_offset=data1_offset,
            invert_data2=self._invert_data2.isChecked(),
            remaps=rules,
        )
        # A transform equal to the no-op default behaves exactly like no
        # transform at all, so store None to keep the routes table's
        # "Transform" column reading "-" instead of a misleading entry.
        self._result = transform if transform != MidiValueTransform() else None
        self.accept()

    def result_transform(self) -> MidiValueTransform | None:
        return self._result


__all__ = ["MidiRouteTransformDialog"]
