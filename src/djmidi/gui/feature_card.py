"""The Atelier's feature card (issue #413, step 2): what the Controller
Emulator shows for the control you click -- the feature as an object (its
stable id, kind, deck, layer) with the raw MIDI it sends and the LED message
underneath. Read-only.
"""

from __future__ import annotations

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from djmidi.atelier.actions import verbs_for
from djmidi.atelier.features import NOTE, Feature

_KINDS = {
    "button": QT_TRANSLATE_NOOP("FeatureCard", "Button"),
    "pad": QT_TRANSLATE_NOOP("FeatureCard", "Pad"),
    "knob": QT_TRANSLATE_NOOP("FeatureCard", "Knob"),
    "fader": QT_TRANSLATE_NOOP("FeatureCard", "Fader"),
    "jog": QT_TRANSLATE_NOOP("FeatureCard", "Jog"),
}
_VERBS = {
    "tap": QT_TRANSLATE_NOOP("FeatureCard", "tap"),
    "press": QT_TRANSLATE_NOOP("FeatureCard", "press"),
    "release": QT_TRANSLATE_NOOP("FeatureCard", "release"),
    "value": QT_TRANSLATE_NOOP("FeatureCard", "value"),
    "led_on": QT_TRANSLATE_NOOP("FeatureCard", "LED on"),
    "led_off": QT_TRANSLATE_NOOP("FeatureCard", "LED off"),
    "led_value": QT_TRANSLATE_NOOP("FeatureCard", "LED value"),
}


class FeatureCard(QGroupBox):
    """Shows one `atelier.Feature`, or a prompt when there is none."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(self.tr("Feature"), parent)
        self.feature: Feature | None = None
        self._prompt = QLabel(self.tr("Click a control to see it as a feature."))
        self._prompt.setWordWrap(True)
        self._fields = QWidget()
        form = QFormLayout(self._fields)
        form.setContentsMargins(0, 0, 0, 0)
        self.id_label = self._value_label(selectable=True)
        self.control_label = self._value_label()
        self.kind_label = self._value_label()
        self.layer_label = self._value_label()
        self.sends_label = self._value_label(selectable=True)
        self.led_label = self._value_label(selectable=True)
        self.actions_label = self._value_label()
        form.addRow(self.tr("Id"), self.id_label)
        form.addRow(self.tr("Control"), self.control_label)
        form.addRow(self.tr("Kind"), self.kind_label)
        form.addRow(self.tr("Layer"), self.layer_label)
        form.addRow(self.tr("Sends"), self.sends_label)
        form.addRow(self.tr("LED"), self.led_label)
        form.addRow(self.tr("Actions"), self.actions_label)
        layout = QVBoxLayout(self)
        layout.addWidget(self._prompt)
        layout.addWidget(self._fields)
        self.set_feature(None)

    @staticmethod
    def _value_label(selectable: bool = False) -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        if selectable:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def set_feature(self, feature: Feature | None, *, unresolved: str | None = None) -> None:
        """`unresolved`: a control was clicked but matches no feature (the
        prompt then says so instead of asking for a click)."""
        self.feature = feature
        self._fields.setVisible(feature is not None)
        self._prompt.setVisible(feature is None)
        if feature is None:
            self._prompt.setText(
                self.tr("{control}: no feature (no raw MIDI trigger known for it).").format(control=unresolved)
                if unresolved
                else self.tr("Click a control to see it as a feature.")
            )
            return
        self.id_label.setText(feature.id)
        self.control_label.setText(feature.name)
        kind = self.tr(_KINDS[feature.kind]) if feature.kind in _KINDS else feature.kind
        self.kind_label.setText(
            self.tr("{kind}, deck {deck}").format(kind=kind, deck=feature.deck) if feature.deck else kind
        )
        layer = self.tr("SHIFT") if feature.shift else self.tr("plain")
        self.layer_label.setText(
            self.tr("{layer}, pad mode {bank}").format(layer=layer, bank=feature.bank) if feature.bank else layer
        )
        source = feature.input
        if source.kind == NOTE:
            self.sends_label.setText(
                self.tr("Note On / Off · ch {channel} · note {number}").format(
                    channel=source.channel, number=source.number
                )
            )
        else:
            self.sends_label.setText(
                self.tr("Control Change · ch {channel} · CC {number}").format(
                    channel=source.channel, number=source.number
                )
            )
        led = feature.led
        if led is None:
            self.led_label.setText(self.tr("none"))
        else:
            text = self.tr("Note On · ch {channel} · note {note} · on {on} / off {off}").format(
                channel=led.channel, note=led.note, on=led.on_value, off=led.off_value
            )
            if not led.verified:
                text += " — " + self.tr("assumed (same note as the button), not verified on the hardware")
            self.led_label.setText(text)
        self.actions_label.setText(", ".join(self.tr(_VERBS.get(verb, verb)) for verb in verbs_for(feature)))


__all__ = ["FeatureCard"]
