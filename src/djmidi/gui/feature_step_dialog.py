"""Pick a controller feature and an LED action to add as macro steps
(Atelier, issue #413, step 3): instead of typing channel / note / velocity,
choose "BEAT SYNC (deck 1)" and "LED on".

Only controls with an LED message (notes) are listed, and only LED actions
offered: the macro's output port is the controller itself, so a step drives
it. Simulating presses towards the DJ software is a later slice.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi.atelier.actions import (
    LED_OFF,
    LED_ON,
    LED_VALUE,
    VERB_LABELS,
    FeatureAction,
    compile_action,
)
from djmidi.atelier.features import Feature, features_for
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.midi_macros import MacroStep
from djmidi.search_text import tokenize

_FEATURE_ROLE = Qt.ItemDataRole.UserRole + 1
_DECK_IN_NAME = re.compile(r"\bDeck\s+[1-4A-D]\b", re.IGNORECASE)
_LED_VERBS = (LED_ON, LED_OFF, LED_VALUE)
_verb_translate = translator("FeatureActions")


class FeatureStepDialog(QDialog):
    def __init__(self, controller: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Add steps from {controller}").format(controller=controller))
        self.controller = controller
        self._features = [feature for feature in features_for(controller) if feature.led is not None]

        intro = QLabel(
            self.tr("Pick a control and what its LED should do; the step's MIDI message is filled in for you.")
        )
        intro.setWordWrap(True)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("Filter controls: name, deck, pad mode…"))
        self.filter_edit.textChanged.connect(self._fill)
        self.feature_list = QListWidget()
        usable_minimum(self.feature_list, 360, 200)
        self.feature_list.currentItemChanged.connect(lambda *_args: self._update_ok())

        self.verb_combo = QComboBox()
        for verb in _LED_VERBS:
            self.verb_combo.addItem(_verb_translate(VERB_LABELS[verb]), verb)
        self.verb_combo.currentIndexChanged.connect(lambda _index: self._update_value())
        self.value_spin = QSpinBox()
        self.value_spin.setRange(0, 127)
        self.value_spin.setValue(64)
        form = QFormLayout()
        form.addRow(self.tr("Action"), self.verb_combo)
        form.addRow(self.tr("Value"), self.value_spin)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Add step"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.feature_list, 1)
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self._fill()
        self._update_value()
        fit_to_screen(self, 560, 520)
        keep_wrapped_text_visible(self)

    def _fill(self) -> None:
        # Word prefixes, accent-insensitive (the function search's tokenizer):
        # "pad 3" finds Pad 3, not Pad 13.
        query = tokenize(self.filter_edit.text())
        self.feature_list.clear()
        for feature in self._features:
            words = tokenize(f"{feature.name} {feature.section}")
            if all(any(word.startswith(token) for word in words) for token in query):
                item = QListWidgetItem(self._row_text(feature))
                item.setData(_FEATURE_ROLE, feature)
                item.setToolTip(feature.id)
                self.feature_list.addItem(item)
        self._update_ok()

    def _row_text(self, feature: Feature) -> str:
        if feature.deck is None:
            return feature.label
        if _DECK_IN_NAME.search(feature.name):  # "Deck 1 Pad 3 ..." already says it
            return feature.name
        return self.tr("{name} (deck {deck})").format(name=feature.name, deck=feature.deck)

    def _update_value(self) -> None:
        self.value_spin.setEnabled(self.verb_combo.currentData() == LED_VALUE)

    def _update_ok(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.selected_feature() is not None)

    def selected_feature(self) -> Feature | None:
        item = self.feature_list.currentItem()
        return item.data(_FEATURE_ROLE) if item is not None else None

    def select(self, feature_id: str) -> bool:
        for row in range(self.feature_list.count()):
            if self.feature_list.item(row).data(_FEATURE_ROLE).id == feature_id:
                self.feature_list.setCurrentRow(row)
                return True
        return False

    def action(self) -> FeatureAction | None:
        feature = self.selected_feature()
        if feature is None:
            return None
        verb = self.verb_combo.currentData()
        return FeatureAction(feature.id, verb, self.value_spin.value() if verb == LED_VALUE else None)

    def steps(self) -> list[MacroStep]:
        action = self.action()
        if action is None:
            return []
        return [MacroStep(message) for message in compile_action(self.controller, action)]


__all__ = ["FeatureStepDialog"]
