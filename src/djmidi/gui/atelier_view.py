"""The Atelier tab (issue #413, step 4): design a controller's LED state for a
sync scene on its photo, instead of recording or typing MIDI messages.

Pick a scene and a controller, click a control on the photo (pad-mode
buttons and SHIFT work as in the emulator, `PhotoPicker`), choose what its
LED does -- not set, off, on, or a value -- and save: the scene becomes the
controller's sync set for that scene (`atelier.scene.Scene`), so the next
Sync (or plug-in, or launch) puts the controller in that state. Messages
the scene doesn't understand are kept as they were.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.atelier.actions import LED_OFF, LED_ON, LED_VALUE, FeatureAction
from djmidi.atelier.describe import describe_action
from djmidi.atelier.features import Feature, feature_by_id
from djmidi.atelier.led_data import LedRecord, save_led_record
from djmidi.atelier.scene import Scene
from djmidi.controller_sync import DEFAULT_SCENE, ControllerSyncSet
from djmidi.gui import help_texts
from djmidi.gui import layout as layout_mod
from djmidi.gui.controller_emulator import EmulatorLayoutView
from djmidi.gui.feature_card import FeatureCard
from djmidi.gui.help_button import help_button
from djmidi.gui.led_probe_dialog import LedProbeDialog
from djmidi.gui.photo_picker import FEATURE, PAD_MODE, SHIFT, PhotoPicker
from djmidi.gui.translation import translator
from djmidi.midi_io import list_output_ports

_verb_translate = translator("FeatureActions")
_FEATURE_ROLE = Qt.ItemDataRole.UserRole + 1
# LED choices (radio ids)
_UNSET, _OFF, _ON, _VALUE = range(4)

SyncSetProvider = Callable[[str, str], "ControllerSyncSet | None"]


class AtelierView(QWidget):
    """`sync_set_provider(controller, scene)` reads the stored set; saving
    emits `saveRequested(ControllerSyncSet)` and sending
    `sendRequested(ControllerSyncSet)` -- MainWindow stores / sends them."""

    saveRequested = Signal(object)
    sendRequested = Signal(object)

    def __init__(
        self,
        sync_set_provider: SyncSetProvider | None = None,
        scene_names_provider: Callable[[], list[str]] | None = None,
        active_scene_provider: Callable[[], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sync_set_provider = sync_set_provider or (lambda _controller, _scene: None)
        self.ports_provider: Callable[[], list[str]] = list_output_ports
        self.led_probe_dialog_factory = LedProbeDialog
        self._scene_names_provider = scene_names_provider or (lambda: [DEFAULT_SCENE])
        self._active_scene_provider = active_scene_provider or (lambda: DEFAULT_SCENE)
        self.scene: Scene | None = None
        self.feature: Feature | None = None
        self._dirty = False

        self.controller_combo = QComboBox()
        self.scene_combo = QComboBox()
        self.controller_combo.currentTextChanged.connect(lambda _text: self.load())
        self.scene_combo.currentTextChanged.connect(lambda _text: self.load())
        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Controller")))
        top.addWidget(self.controller_combo, 1)
        top.addWidget(QLabel(self.tr("Scene")))
        top.addWidget(self.scene_combo, 1)
        top.addWidget(help_button(self, *help_texts.ATELIER))

        self._photo_scroll = QScrollArea()
        self._photo_scroll.setWidgetResizable(True)
        self._photo_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.photo: EmulatorLayoutView | None = None
        self._picker: PhotoPicker | None = None

        self.feature_card = FeatureCard()
        led_box = QGroupBox(self.tr("LED in this scene"))
        led_layout = QFormLayout(led_box)
        self.led_group = QButtonGroup(self)
        radios = QVBoxLayout()
        for choice, label in (
            (_UNSET, self.tr("Not set (left as it is)")),
            (_OFF, self.tr("Off")),
            (_ON, self.tr("On")),
            (_VALUE, self.tr("Value")),
        ):
            radio = QRadioButton(label)
            self.led_group.addButton(radio, choice)
            radios.addWidget(radio)
        self.value_spin = QSpinBox()
        self.value_spin.setRange(0, 127)
        self.value_spin.setValue(64)
        led_layout.addRow(radios)
        led_layout.addRow(self.tr("Value"), self.value_spin)
        # Step 5: check this LED on the hardware and record what it does.
        self.probe_button = QPushButton(self.tr("Probe this LED…"))
        self.probe_button.setToolTip(
            self.tr("With the controller plugged in, check where this LED answers and record its values and colours.")
        )
        self.probe_button.clicked.connect(self.probe_led)
        self.probe_button.setEnabled(False)
        led_layout.addRow(self.probe_button)
        self.led_group.idClicked.connect(lambda _id: self._apply_led())
        self.value_spin.valueChanged.connect(lambda _value: self._on_value_changed())

        self.state_list = QListWidget()
        self.state_list.itemClicked.connect(self._on_state_item_clicked)
        self.load_button = QPushButton(self.tr("Reload saved"))
        self.load_button.clicked.connect(self.load)
        self.clear_button = QPushButton(self.tr("Clear LEDs"))
        self.clear_button.clicked.connect(self.clear_leds)
        self.save_button = QPushButton(self.tr("Save to sync set"))
        self.save_button.clicked.connect(self.save)
        self.send_button = QPushButton(self.tr("Send to controller"))
        self.send_button.setToolTip(self.tr("Sends this scene's messages to the controller now, without saving."))
        self.send_button.clicked.connect(lambda: self.sendRequested.emit(self.current_sync_set()))
        buttons = QHBoxLayout()
        for button in (self.load_button, self.clear_button, self.save_button, self.send_button):
            buttons.addWidget(button)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(self.feature_card)
        side_layout.addWidget(led_box)
        side_layout.addWidget(QLabel(self.tr("Scene state")))
        side_layout.addWidget(self.state_list, 1)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setWidget(side)
        side_scroll.setMinimumWidth(300)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._photo_scroll)
        splitter.addWidget(side_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        self.refresh_controllers()
        self.refresh_scenes()

    # -- lists ------------------------------------------------------------

    def refresh_controllers(self) -> None:
        current = self.controller_combo.currentText()
        self.controller_combo.blockSignals(True)
        self.controller_combo.clear()
        self.controller_combo.addItems(list(catalog.CONTROLLER_NAMES))
        if current:
            self.controller_combo.setCurrentText(current)
        self.controller_combo.blockSignals(False)
        self.load()

    def refresh_scenes(self) -> None:
        current = self.scene_combo.currentText() or self._active_scene_provider()
        names = list(dict.fromkeys([*self._scene_names_provider(), self._active_scene_provider()]))
        self.scene_combo.blockSignals(True)
        self.scene_combo.clear()
        self.scene_combo.addItems(names)
        self.scene_combo.setCurrentText(current if current in names else self._active_scene_provider())
        self.scene_combo.blockSignals(False)
        self.load()

    @property
    def controller(self) -> str:
        return self.controller_combo.currentText()

    # -- scene ------------------------------------------------------------

    def load(self) -> None:
        """(Re)reads the stored sync set of the chosen controller and scene."""
        controller = self.controller
        if not controller:
            return
        if self.photo is None or self.photo.controller != controller:
            self.photo = EmulatorLayoutView(controller)
            self.photo.controlPressed.connect(self.pick_key)
            self._photo_scroll.setWidget(self.photo)
            self._picker = PhotoPicker(self.photo)
        stored = self._sync_set_provider(controller, self.scene_combo.currentText() or DEFAULT_SCENE)
        self.scene = Scene.from_sync_set(stored, controller)
        self._set_feature(None)
        self._dirty = False
        self._refresh_state()
        self.status_label.setText(
            self.tr("Loaded the {scene} sync set: {count} LED(s) set.").format(
                scene=self.scene_combo.currentText(), count=len(self.scene.lit)
            )
            if stored is not None
            else self.tr("No sync set saved for this controller and scene yet: click a control to start one.")
        )

    def pick_key(self, key) -> Feature | None:
        pick = self._picker.click(key)
        if pick.kind == SHIFT:
            self.status_label.setText(
                self.tr("SHIFT held: clicks pick the SHIFT layer.") if pick.shift_held else self.tr("SHIFT released.")
            )
            return None
        if pick.kind == PAD_MODE:
            self.status_label.setText(self.tr("Pad mode set: {mode}. Now click a pad.").format(mode=pick.mode))
            return None
        if pick.kind != FEATURE or pick.feature.led is None:
            self.status_label.setText(self.tr("{control}: no LED message known for this control.").format(control=key[2]))
            return None
        self._picker.mark_picked(key)
        self._set_feature(pick.feature)
        return pick.feature

    def select_feature(self, feature_id: str) -> bool:
        feature = feature_by_id(self.controller, feature_id) if self.controller else None
        if feature is None:
            return False
        self._set_feature(feature)
        return True

    def _set_feature(self, feature: Feature | None) -> None:
        self.feature = feature
        self.feature_card.set_feature(feature)
        value = self.scene.led_value(feature.id) if (feature is not None and self.scene is not None) else None
        for button in self.led_group.buttons():
            button.setEnabled(feature is not None)
        self.probe_button.setEnabled(feature is not None and feature.led is not None)
        self.value_spin.blockSignals(True)
        if value is None:
            self.led_group.button(_UNSET).setChecked(True)
        elif feature is not None and feature.led is not None and value == feature.led.on_value:
            self.led_group.button(_ON).setChecked(True)
        elif feature is not None and feature.led is not None and value == feature.led.off_value:
            self.led_group.button(_OFF).setChecked(True)
        else:
            self.led_group.button(_VALUE).setChecked(True)
            self.value_spin.setValue(value)
        self.value_spin.blockSignals(False)
        self.value_spin.setEnabled(feature is not None and self.led_group.checkedId() == _VALUE)

    def set_led_choice(self, choice: int, value: int | None = None) -> None:
        """What the LED choice radios do (also for tests): 0 not set, 1 off,
        2 on, 3 value (`value`, else the spin box's)."""
        if value is not None:
            self.value_spin.blockSignals(True)
            self.value_spin.setValue(value)
            self.value_spin.blockSignals(False)
        self.led_group.button(choice).setChecked(True)
        self._apply_led()

    def _on_value_changed(self) -> None:
        if self.led_group.checkedId() == _VALUE:
            self._apply_led()

    def _apply_led(self) -> None:
        feature = self.feature
        choice = self.led_group.checkedId()
        self.value_spin.setEnabled(feature is not None and choice == _VALUE)
        if feature is None or self.scene is None or feature.led is None:
            return
        value = {
            _UNSET: None,
            _OFF: feature.led.off_value,
            _ON: feature.led.on_value,
            _VALUE: self.value_spin.value(),
        }[choice]
        self.scene.set_led(feature.id, value)
        self._dirty = True
        self._refresh_state()
        self.status_label.setText(self.tr("Not saved yet: click Save to sync set to keep it."))

    def clear_leds(self) -> None:
        if self.scene is None:
            return
        self.scene.clear()
        self._dirty = True
        self._set_feature(self.feature)
        self._refresh_state()

    def _refresh_state(self) -> None:
        """The list of what the scene sets, and the lit controls on the photo."""
        self.state_list.clear()
        if self.photo is not None:
            self.photo.clear_leds()
        if self.scene is None:
            return
        for item in self.scene.items:
            if isinstance(item, str):
                verb = self._verb_for(item)
                text = describe_action(self.controller, verb, _verb_translate) or item
                entry = QListWidgetItem(text)
                entry.setData(_FEATURE_ROLE, item)
                self.state_list.addItem(entry)
                if self.scene.values[item] > 0:
                    for key in self._cell_keys(item):
                        self.photo.set_led(key, True)
            else:
                entry = QListWidgetItem(
                    self.tr("{type} · ch {channel} · {data1} · {data2} (kept as is)").format(
                        type=item.event_type, channel=item.channel, data1=item.data1, data2=item.data2
                    )
                )
                entry.setForeground(self.palette().placeholderText())
                self.state_list.addItem(entry)

    def _verb_for(self, feature_id: str) -> FeatureAction:
        feature = feature_by_id(self.controller, feature_id)
        value = self.scene.values[feature_id]
        if feature is not None and feature.led is not None and value == feature.led.on_value:
            return FeatureAction(feature_id, LED_ON)
        if feature is not None and feature.led is not None and value == feature.led.off_value:
            return FeatureAction(feature_id, LED_OFF)
        return FeatureAction(feature_id, LED_VALUE, value)

    def _cell_keys(self, feature_id: str) -> list:
        feature = feature_by_id(self.controller, feature_id)
        if feature is None:
            return []
        event = "Note On" if feature.input.kind == "NOTE" else "Control Change"
        channel = str(feature.input.channel)
        hits = catalog.lookup(channel, event, str(feature.input.number))
        # Narrowed to this feature's own channel: an entry listing every deck
        # channel would otherwise land on the wrong side of the photo.
        return [
            layout_mod.presentation_key_for_hit(dataclasses.replace(hit, channels=(channel,)))
            for hit in hits
            if hit.controller == self.controller and hit.name == feature.name
        ]

    def _on_state_item_clicked(self, item: QListWidgetItem) -> None:
        feature_id = item.data(_FEATURE_ROLE)
        if feature_id:
            self.select_feature(feature_id)

    def probe_led(self) -> LedRecord | None:
        """Opens the LED probe for the selected control; a saved result is
        recorded (verified) and the scene reloaded with it."""
        if self.feature is None or self.feature.led is None:
            return None
        dialog = self.led_probe_dialog_factory(self.feature, self.ports_provider(), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        record = dialog.record()
        save_led_record(self.controller, record)
        feature_id = self.feature.id
        dirty, unsaved = self._dirty, self.scene
        self.load()  # features now carry the verified LED
        if dirty and unsaved is not None:  # keep the edits in progress
            self.scene = Scene.from_messages(self.controller, unsaved.messages())
            self._dirty = True
            self._refresh_state()
        self.select_feature(feature_id)
        self.status_label.setText(self.tr("LED recorded as verified for {control}.").format(control=self.feature.name))
        return record

    # -- save / send ------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def current_sync_set(self) -> ControllerSyncSet | None:
        if self.scene is None or not self.controller:
            return None
        scene_name = self.scene_combo.currentText() or DEFAULT_SCENE
        return self.scene.to_sync_set(self._sync_set_provider(self.controller, scene_name), scene_name)

    def save(self) -> ControllerSyncSet | None:
        sync_set = self.current_sync_set()
        if sync_set is None:
            return None
        self.saveRequested.emit(sync_set)
        self._dirty = False
        self.status_label.setText(
            self.tr("Saved: {count} message(s) in the {scene} sync set of {controller}.").format(
                count=len(sync_set.messages), scene=sync_set.scene, controller=sync_set.controller
            )
        )
        return sync_set


__all__ = ["AtelierView"]
