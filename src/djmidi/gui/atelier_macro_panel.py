"""The Atelier's Macros tab (issue #428): a macro's steps beside the
controller's photo. Clicking a control on the photo (routed here by
`AtelierView` while this tab is shown) appends steps for the chosen verb;
steps can be reordered, removed and given a delay, and the list saved,
without opening Macros → Manage Macros….

Qt-free edits in `atelier.macro_edit`. The panel works on a copy of the
macro list (`set_macros`) and emits `macrosSaved(list)`; MainWindow stores
them like the macro editor does.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from djmidi.atelier.actions import AS_CONTROLLER, VERB_LABELS
from djmidi.atelier.describe import macro_target
from djmidi.atelier.features import Feature
from djmidi.atelier.macro_edit import (
    VALUED_VERBS,
    append_steps,
    describe_step,
    move_step,
    remove_step,
    set_delay,
    steps_for,
    steps_of,
    verbs_for,
    wait_step_for,
)
from djmidi.gui.translation import translator
from djmidi.midi_macros import MAX_DELAY_MS, MidiMacro, annotate_with_features

_verb_translate = translator("FeatureActions")
_edit_translate = translator("MacroEdit")
# A click that adds a wait for a press of that control (issue #435).
WAIT = "wait"


class AtelierMacroPanel(QWidget):
    macrosSaved = Signal(object)
    # The controller the selected macro is about ("" for none): the Atelier
    # shows that controller's photo.
    targetChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.macros: list[MidiMacro] = []
        self._dirty = False

        self.macro_combo = QComboBox()
        self.macro_combo.currentIndexChanged.connect(lambda _index: self._on_macro_changed())
        self.target_label = QLabel()
        self.target_label.setWordWrap(True)

        self.verb_combo = QComboBox()
        self.verb_combo.currentIndexChanged.connect(lambda _index: self._update_value())
        self.value_spin = QSpinBox()
        self.value_spin.setRange(0, 127)
        self.value_spin.setValue(127)
        click_row = QHBoxLayout()
        click_row.addWidget(self.verb_combo, 1)
        click_row.addWidget(self.value_spin)
        # Issue #435: a toggle macro plays its second list every other time.
        self.list_combo = QComboBox()
        self.list_combo.addItem(self.tr("Main steps"), False)
        self.list_combo.addItem(self.tr("Second steps (toggle)"), True)
        self.list_combo.setToolTip(
            self.tr("A macro with second steps is a toggle: it plays them every other time.")
        )
        self.list_combo.currentIndexChanged.connect(lambda _index: self._refresh_steps())
        form = QFormLayout()
        form.addRow(self.tr("Macro"), self.macro_combo)
        form.addRow(self.tr("Steps"), self.list_combo)
        form.addRow(self.tr("A click adds"), click_row)

        self.step_list = QListWidget()
        self.step_list.currentRowChanged.connect(lambda _row: self._on_step_changed())
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, MAX_DELAY_MS)
        self.delay_spin.setSingleStep(50)
        self.delay_spin.setSuffix(self.tr(" ms"))
        self.delay_spin.valueChanged.connect(self._on_delay_changed)
        self.up_button = QPushButton(self.tr("Up"))
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button = QPushButton(self.tr("Down"))
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        self.remove_button = QPushButton(self.tr("Remove"))
        self.remove_button.clicked.connect(self.remove_selected)
        step_row = QHBoxLayout()
        self.delay_label = QLabel(self.tr("Delay"))
        step_row.addWidget(self.delay_label)
        step_row.addWidget(self.delay_spin)
        step_row.addWidget(self.up_button)
        step_row.addWidget(self.down_button)
        step_row.addWidget(self.remove_button)

        self.save_button = QPushButton(self.tr("Save macros"))
        self.save_button.clicked.connect(self.save)
        self.revert_button = QPushButton(self.tr("Revert"))
        self.revert_button.setToolTip(self.tr("Drops the changes made here since the last save."))
        self.revert_button.clicked.connect(self.revert)
        bottom = QHBoxLayout()
        bottom.addWidget(self.save_button)
        bottom.addWidget(self.revert_button)
        bottom.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.target_label)
        layout.addWidget(self.step_list, 1)
        layout.addLayout(step_row)
        layout.addLayout(bottom)
        self._saved: list[MidiMacro] = []
        self._refresh_all()

    # -- macros -----------------------------------------------------------

    def set_macros(self, macros: list[MidiMacro]) -> None:
        """The stored macros (the panel's unsaved changes are dropped)."""
        self._saved = list(macros)
        self.macros = list(macros)
        self._dirty = False
        current = self.macro_combo.currentText()
        self.macro_combo.blockSignals(True)
        self.macro_combo.clear()
        self.macro_combo.addItems([macro.name for macro in self.macros])
        index = self.macro_combo.findText(current)
        self.macro_combo.setCurrentIndex(max(index, 0))
        self.macro_combo.blockSignals(False)
        self._on_macro_changed()

    @property
    def macro(self) -> MidiMacro | None:
        index = self.macro_combo.currentIndex()
        return self.macros[index] if 0 <= index < len(self.macros) else None

    @property
    def target(self) -> tuple[str, str] | None:
        macro = self.macro
        return macro_target(macro.output_port, macro.simulates) if macro is not None else None

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def alternate(self) -> bool:
        """Whether the toggle's second step list is being edited."""
        return bool(self.list_combo.currentData())

    @property
    def steps(self) -> tuple:
        return steps_of(self.macro, self.alternate) if self.macro is not None else ()

    def _replace(self, macro: MidiMacro, row: int | None = None) -> None:
        self.macros[self.macro_combo.currentIndex()] = macro
        self._dirty = True
        self._refresh_steps(row)

    def _on_macro_changed(self) -> None:
        target = self.target
        self._refresh_all()
        self.targetChanged.emit(target[0] if target is not None else "")

    def _refresh_all(self) -> None:
        macro = self.macro
        target = self.target
        if macro is None:
            self.target_label.setText(self.tr("No macro yet: create one in Macros → Manage Macros…"))
        elif target is None:
            self.target_label.setText(
                self.tr(
                    "This macro sends plain MIDI: give it a controller as output, or the controller it "
                    "simulates, in Macros → Manage Macros… to add steps by clicking."
                )
            )
        elif target[1] == AS_CONTROLLER:
            self.target_label.setText(
                self.tr("Clicks add presses imitating the {controller}.").format(controller=target[0])
            )
        else:
            self.target_label.setText(self.tr("Clicks add LED changes on the {controller}.").format(controller=target[0]))
        self._set_verbs(())
        self._refresh_steps()

    def _refresh_steps(self, row: int | None = None) -> None:
        macro = self.macro
        self.step_list.blockSignals(True)
        self.step_list.clear()
        for step in self.steps:
            self.step_list.addItem(describe_step(macro, step, _edit_translate_both))
        self.step_list.blockSignals(False)
        if row is not None and 0 <= row < self.step_list.count():
            self.step_list.setCurrentRow(row)
        self._on_step_changed()
        self.save_button.setEnabled(self._dirty)
        self.revert_button.setEnabled(self._dirty)

    def _on_step_changed(self) -> None:
        row = self.step_list.currentRow()
        steps = self.steps
        selected = 0 <= row < len(steps)
        for widget in (self.delay_spin, self.up_button, self.down_button, self.remove_button):
            widget.setEnabled(selected)
        waiting = selected and steps[row].wait
        # A wait step's "delay" is how long it waits at most (0: the longest).
        self.delay_label.setText(self.tr("Wait at most") if waiting else self.tr("Delay"))
        self.delay_spin.blockSignals(True)
        self.delay_spin.setValue(steps[row].delay_ms if selected else 0)
        self.delay_spin.blockSignals(False)

    # -- verbs ------------------------------------------------------------

    def _set_verbs(self, verbs: tuple[str, ...]) -> None:
        current = self.verb_combo.currentData()
        self.verb_combo.blockSignals(True)
        self.verb_combo.clear()
        for verb in verbs:
            label = self.tr("wait for a press") if verb == WAIT else _verb_translate(VERB_LABELS[verb])
            self.verb_combo.addItem(label, verb)
        if current in verbs:
            self.verb_combo.setCurrentIndex(verbs.index(current))
        self.verb_combo.blockSignals(False)
        self.verb_combo.setEnabled(bool(verbs))
        self._update_value()

    def _update_value(self) -> None:
        self.value_spin.setEnabled(self.verb_combo.currentData() in VALUED_VERBS)

    def show_feature(self, feature: Feature | None) -> None:
        """A control was selected: offers what a click on it can add."""
        self._set_verbs(self._verbs(feature))

    def _verbs(self, feature: Feature | None) -> tuple[str, ...]:
        target = self.target
        if feature is None or target is None:
            return ()
        return (*verbs_for(feature, target[1]), WAIT)

    # -- edits ------------------------------------------------------------

    def add_feature(self, controller: str, feature: Feature, verb: str | None = None) -> bool:
        """Appends the steps for `feature` (the selected verb unless given).
        False when the macro isn't about `controller` or the verb doesn't fit."""
        macro, target = self.macro, self.target
        if macro is None or target is None or target[0] != controller:
            return False
        self.show_feature(feature)
        verb = verb or self.verb_combo.currentData()
        if verb not in self._verbs(feature):
            return False
        if verb == WAIT:
            steps = [wait_step_for(feature)]
        else:
            steps = steps_for(controller, feature, verb, self.value_spin.value())
        count = len(self.steps)
        self._replace(append_steps(macro, steps, self.alternate), count + len(steps) - 1)
        return True

    def remove_selected(self) -> None:
        row = self.step_list.currentRow()
        count = len(self.steps)
        if 0 <= row < count:
            self._replace(remove_step(self.macro, row, self.alternate), min(row, count - 2))

    def move_selected(self, offset: int) -> None:
        row = self.step_list.currentRow()
        if 0 <= row < len(self.steps):
            macro, row = move_step(self.macro, row, offset, self.alternate)
            self._replace(macro, row)

    def _on_delay_changed(self, value: int) -> None:
        row = self.step_list.currentRow()
        if 0 <= row < len(self.steps):
            self._replace(set_delay(self.macro, row, value, self.alternate), row)

    def save(self) -> list[MidiMacro]:
        macros = [annotate_with_features(macro) for macro in self.macros]
        self.macrosSaved.emit(macros)
        self.set_macros(macros)
        return macros

    def revert(self) -> None:
        self.set_macros(self._saved)


def _edit_translate_both(text: str) -> str:
    """Step texts mix MacroEdit templates and FeatureActions verb labels."""
    translated = _edit_translate(text)
    return translated if translated != text else _verb_translate(text)


__all__ = ["AtelierMacroPanel"]
