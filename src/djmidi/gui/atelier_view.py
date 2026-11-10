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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.atelier.actions import LED_OFF, LED_ON, LED_VALUE, FeatureAction
from djmidi.atelier.describe import describe_action
from djmidi.atelier.features import Feature, feature_by_id
from djmidi.atelier.led_data import LedRecord, save_led_record
from djmidi.atelier.remap import describe_remap, remap_rule, with_remap, without_remap
from djmidi.atelier.scene import Scene, scene_coverage
from djmidi.controller_sync import DEFAULT_SCENE, ControllerSyncSet
from djmidi.gui import help_texts
from djmidi.gui import layout as layout_mod
from djmidi.gui.atelier_macro_panel import AtelierMacroPanel
from djmidi.gui.controller_emulator import EmulatorLayoutView
from djmidi.gui.feature_card import FeatureCard
from djmidi.gui.help_button import help_button
from djmidi.gui.led_probe_dialog import LedProbeDialog
from djmidi.gui.photo_picker import FEATURE, PAD_MODE, SHIFT, PhotoPicker
from djmidi.gui.translation import translator
from djmidi.midi_io import list_output_ports
from djmidi.midi_router import MidiValueTransform, RemapRule

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
    # Issue #427: every controller's set for the scene, sent in one go.
    sendAllRequested = Signal(object)
    # (route index, new MidiValueTransform): a remap added or removed
    routeTransformChanged = Signal(int, object)

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
        # Step 6: the MIDI Routing tab's routes (labels, and a route's transform).
        self.route_labels_provider: Callable[[], list[str]] = list
        self.route_transform_provider: Callable[[int], MidiValueTransform | None] = lambda _index: None
        self._remap_source: Feature | None = None
        self.led_probe_dialog_factory = LedProbeDialog
        self._scene_names_provider = scene_names_provider or (lambda: [DEFAULT_SCENE])
        self._active_scene_provider = active_scene_provider or (lambda: DEFAULT_SCENE)
        self.scene: Scene | None = None
        self.feature: Feature | None = None
        # Issue #427: unsaved scenes per (controller, scene name), so switching
        # controller or scene never loses an edit; the scene on screen is the
        # one of `_loaded_key`.
        self._drafts: dict[tuple[str, str], Scene] = {}
        self._loaded_key: tuple[str, str] | None = None

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
        self.coverage_label = QLabel()
        self.coverage_label.setWordWrap(True)

        self._photo_scroll = QScrollArea()
        self._photo_scroll.setWidgetResizable(True)
        self._photo_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.photo: EmulatorLayoutView | None = None
        self._picker: PhotoPicker | None = None

        self.feature_card = FeatureCard()
        self.led_box = led_box = QGroupBox(self.tr("LED in this scene"))
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
        self.load_button.setToolTip(self.tr("Drops this controller's unsaved changes for this scene."))
        self.load_button.clicked.connect(self.reload_saved)
        self.clear_button = QPushButton(self.tr("Clear LEDs"))
        self.clear_button.clicked.connect(self.clear_leds)
        self.save_button = QPushButton(self.tr("Save to sync set"))
        self.save_button.clicked.connect(self.save)
        self.send_button = QPushButton(self.tr("Send to controller"))
        self.send_button.setToolTip(self.tr("Sends this scene's messages to the controller now, without saving."))
        self.send_button.clicked.connect(lambda: self.sendRequested.emit(self.current_sync_set()))
        self.save_all_button = QPushButton(self.tr("Save all"))
        self.save_all_button.setToolTip(self.tr("Saves this scene's unsaved changes for every controller."))
        self.save_all_button.clicked.connect(self.save_all)
        self.send_all_button = QPushButton(self.tr("Send all"))
        self.send_all_button.setToolTip(
            self.tr("Sends this scene to every controller it covers, saved or not, in one go.")
        )
        self.send_all_button.clicked.connect(self.send_all)
        buttons = QHBoxLayout()
        for button in (self.load_button, self.clear_button, self.save_button, self.send_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_all_button)
        buttons.addWidget(self.send_all_button)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(self.feature_card)
        side_layout.addWidget(led_box)
        # The scene's state and the remap panel share the space below as two
        # tabs: stacked, they didn't fit a normal window's height.
        self.lower_tabs = QTabWidget()
        self.lower_tabs.addTab(self.state_list, self.tr("Scene state"))
        self.lower_tabs.addTab(self._build_remap_box(), self.tr("Remap"))
        # Issue #428: while this tab shows, photo clicks add macro steps.
        self.macro_panel = AtelierMacroPanel()
        self.macro_panel.targetChanged.connect(self._on_macro_target_changed)
        self.lower_tabs.addTab(self.macro_panel, self.tr("Macros"))
        # The scene's LED choices mean nothing while editing a macro, and the
        # macro's step list needs their room.
        self.lower_tabs.currentChanged.connect(lambda _index: self.led_box.setVisible(not self.editing_macros))
        self.lower_tabs.setMinimumHeight(200)
        side_layout.addWidget(self.lower_tabs, 1)
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
        layout.addWidget(self.coverage_label)
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

    @property
    def scene_name(self) -> str:
        return self.scene_combo.currentText() or DEFAULT_SCENE

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
        key = (controller, self.scene_name)
        stored = self._sync_set_provider(*key)
        draft = self._drafts.get(key)
        self.scene = draft if draft is not None else Scene.from_sync_set(stored, controller)
        self._loaded_key = key
        self._set_feature(None)
        self._refresh_state()
        self._refresh_coverage()
        if draft is not None:
            self.status_label.setText(
                self.tr("Unsaved changes kept for {controller}: click Save to sync set to keep them.").format(
                    controller=controller
                )
            )
        elif stored is not None:
            self.status_label.setText(
                self.tr("Loaded the {scene} sync set: {count} LED(s) set.").format(
                    scene=self.scene_name, count=len(self.scene.lit)
                )
            )
        else:
            self.status_label.setText(
                self.tr("No sync set saved for this controller and scene yet: click a control to start one.")
            )

    def reload_saved(self) -> None:
        """Drops the unsaved changes of the controller and scene on screen."""
        if self._loaded_key is not None:
            self._drafts.pop(self._loaded_key, None)
        self.load()

    def _mark_dirty(self) -> None:
        if self._loaded_key is not None and self.scene is not None:
            self._drafts[self._loaded_key] = self.scene
        self._refresh_coverage()

    def unsaved_controllers(self, scene: str | None = None) -> list[str]:
        scene = scene or self.scene_name
        return [controller for controller, name in self._drafts if name == scene]

    def coverage(self):
        """The controllers the scene on screen covers (`SceneCoverage`)."""
        return scene_coverage(
            catalog.CONTROLLER_NAMES, self.scene_name, self._sync_set_provider, self.unsaved_controllers()
        )

    def _refresh_coverage(self) -> None:
        covered = self.coverage()
        names = {entry.controller for entry in covered}
        for index in range(self.controller_combo.count()):
            font = self.controller_combo.font()
            font.setBold(self.controller_combo.itemText(index) in names)
            self.controller_combo.setItemData(index, font, Qt.ItemDataRole.FontRole)
        if not covered:
            self.coverage_label.setText(self.tr("No controller has a set for this scene yet."))
        else:
            parts = [
                self.tr("{controller} (unsaved)").format(controller=entry.controller)
                if entry.unsaved
                else entry.controller
                for entry in covered
            ]
            self.coverage_label.setText(
                self.tr("This scene covers: {controllers}").format(controllers=", ".join(parts))
            )
        self.save_all_button.setEnabled(bool(self.unsaved_controllers()))
        self.send_all_button.setEnabled(bool(covered))

    def _build_remap_box(self) -> QWidget:
        """Step 6: make one control act as another (or block it) on a MIDI
        Routing route, by clicking the two controls."""
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.addWidget(QLabel(self.tr("Remap through a route")))
        self.route_combo = QComboBox()
        self.route_combo.currentIndexChanged.connect(lambda _index: self._refresh_remaps())
        layout.addWidget(self.route_combo)
        row = QHBoxLayout()
        self.remap_button = QPushButton(self.tr("Remap from this control"))
        self.remap_button.setToolTip(self.tr("Then click the control it should act as."))
        self.remap_button.clicked.connect(self.start_remap)
        self.block_button = QPushButton(self.tr("Block this control"))
        self.block_button.clicked.connect(lambda: self.add_remap(self.feature, None))
        row.addWidget(self.remap_button)
        row.addWidget(self.block_button)
        layout.addLayout(row)
        self.remap_list = QListWidget()
        self.remap_list.setMaximumHeight(80)
        layout.addWidget(self.remap_list)
        self.remove_remap_button = QPushButton(self.tr("Remove remap"))
        self.remove_remap_button.clicked.connect(self.remove_selected_remap)
        layout.addWidget(self.remove_remap_button, 0, Qt.AlignmentFlag.AlignLeft)
        return box

    def refresh_routes(self) -> None:
        current = self.route_combo.currentIndex()
        self.route_combo.blockSignals(True)
        self.route_combo.clear()
        labels = self.route_labels_provider()
        self.route_combo.addItems(labels)
        if labels:
            self.route_combo.setCurrentIndex(min(max(current, 0), len(labels) - 1))
        else:
            self.route_combo.addItem(self.tr("No route yet: add one in MIDI Routing"))
        self.route_combo.setEnabled(bool(labels))
        self.route_combo.blockSignals(False)
        self._refresh_remaps()

    def _route_index(self) -> int:
        return self.route_combo.currentIndex() if self.route_combo.isEnabled() else -1

    def _refresh_remaps(self) -> None:
        self.remap_list.clear()
        index = self._route_index()
        transform = self.route_transform_provider(index) if index >= 0 else None
        for rule in transform.remaps if transform is not None else ():
            item = QListWidgetItem(describe_remap(self.controller, rule, _verb_translate))
            item.setData(_FEATURE_ROLE, rule)
            self.remap_list.addItem(item)
        self._update_remap_buttons()

    def _update_remap_buttons(self) -> None:
        ready = self._route_index() >= 0 and self.feature is not None
        self.remap_button.setEnabled(ready)
        self.block_button.setEnabled(ready)
        self.remove_remap_button.setEnabled(self.remap_list.count() > 0)

    def start_remap(self) -> None:
        if self.feature is None or self._route_index() < 0:
            return
        self._remap_source = self.feature
        self.status_label.setText(
            self.tr("Now click the control {control} should act as.").format(control=self.feature.name)
        )

    def add_remap(self, source: Feature | None, target: Feature | None) -> RemapRule | None:
        index = self._route_index()
        if source is None or index < 0:
            return None
        rule = remap_rule(source, target)
        transform = with_remap(self.route_transform_provider(index), rule)
        self.routeTransformChanged.emit(index, transform)
        self._refresh_remaps()
        self.status_label.setText(
            self.tr("Remap added: {remap}.").format(remap=describe_remap(self.controller, rule, _verb_translate))
        )
        return rule

    def remove_selected_remap(self) -> None:
        item = self.remap_list.currentItem()
        index = self._route_index()
        if item is None or index < 0:
            return
        self.routeTransformChanged.emit(index, without_remap(self.route_transform_provider(index), item.data(_FEATURE_ROLE)))
        self._refresh_remaps()

    @property
    def editing_macros(self) -> bool:
        return self.lower_tabs.currentWidget() is self.macro_panel

    def _on_macro_target_changed(self, controller: str) -> None:
        """Shows the photo of the controller the selected macro is about."""
        if controller and controller != self.controller and self.controller_combo.findText(controller) >= 0:
            self.controller_combo.setCurrentText(controller)

    def _pick_for_macro(self, key) -> Feature | None:
        pick = self._picker.click(key)
        if pick.kind == SHIFT:
            self.status_label.setText(
                self.tr("SHIFT held: clicks pick the SHIFT layer.") if pick.shift_held else self.tr("SHIFT released.")
            )
            return None
        if pick.kind == PAD_MODE:
            self.status_label.setText(self.tr("Pad mode set: {mode}. Now click a pad.").format(mode=pick.mode))
            return None
        if pick.kind != FEATURE:
            self.status_label.setText(self.tr("{control}: no MIDI message known for this control.").format(control=key[2]))
            return None
        target = self.macro_panel.target
        if target is None:
            self.status_label.setText(self.tr("Pick a macro that drives or simulates a controller first."))
            return None
        if target[0] != self.controller:
            self.status_label.setText(
                self.tr("This macro is about the {controller}: switch the controller to add steps.").format(
                    controller=target[0]
                )
            )
            return None
        self._picker.mark_picked(key)
        self.feature = pick.feature
        self.feature_card.set_feature(pick.feature)
        if not self.macro_panel.add_feature(self.controller, pick.feature):
            self.status_label.setText(
                self.tr("{control}: nothing this macro can do with it.").format(control=pick.feature.name)
            )
            return None
        self.status_label.setText(self.tr("Step added: click Save macros to keep it."))
        return pick.feature

    def pick_key(self, key) -> Feature | None:
        if self.editing_macros and self._remap_source is None:
            return self._pick_for_macro(key)
        if self._remap_source is not None:
            pick = self._picker.click(key)
            if pick.kind == FEATURE:
                source, self._remap_source = self._remap_source, None
                self.add_remap(source, pick.feature)
                return pick.feature
            if pick.kind == PAD_MODE or pick.kind == SHIFT:
                self.status_label.setText(self.tr("Pad mode or SHIFT set: now click the target control."))
            return None
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
        if hasattr(self, "remap_button"):
            self._update_remap_buttons()
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
        self._mark_dirty()
        self._refresh_state()
        self.status_label.setText(self.tr("Not saved yet: click Save to sync set to keep it."))

    def clear_leds(self) -> None:
        if self.scene is None:
            return
        self.scene.clear()
        self._mark_dirty()
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
        # Features now carry the verified LED; an unsaved draft keeps its
        # edits (it stores feature ids, compiled with the new data on save).
        self.load()
        self.select_feature(feature_id)
        self.status_label.setText(self.tr("LED recorded as verified for {control}.").format(control=self.feature.name))
        return record

    # -- save / send ------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        return self._loaded_key is not None and self._loaded_key in self._drafts

    def current_sync_set(self) -> ControllerSyncSet | None:
        if self.scene is None or not self.controller:
            return None
        return self.scene.to_sync_set(self._sync_set_provider(self.controller, self.scene_name), self.scene_name)

    def scene_sync_sets(self) -> list[ControllerSyncSet]:
        """Every covered controller's set for the scene on screen: its
        unsaved draft when there is one, else what is stored."""
        result = []
        for entry in self.coverage():
            stored = self._sync_set_provider(entry.controller, self.scene_name)
            draft = self._drafts.get((entry.controller, self.scene_name))
            result.append(draft.to_sync_set(stored, self.scene_name) if draft is not None else stored)
        return result

    def send_all(self) -> list[ControllerSyncSet]:
        sets = self.scene_sync_sets()
        if sets:
            self.sendAllRequested.emit(sets)
        return sets

    def save_all(self) -> list[ControllerSyncSet]:
        """Saves every unsaved controller of the scene on screen."""
        saved = []
        for controller in self.unsaved_controllers():
            draft = self._drafts.pop((controller, self.scene_name))
            sync_set = draft.to_sync_set(self._sync_set_provider(controller, self.scene_name), self.scene_name)
            saved.append(sync_set)
            self.saveRequested.emit(sync_set)
        self._refresh_coverage()
        if saved:
            self.status_label.setText(
                self.tr("Saved the {scene} scene for {count} controller(s).").format(
                    scene=self.scene_name, count=len(saved)
                )
            )
        return saved

    def save(self) -> ControllerSyncSet | None:
        sync_set = self.current_sync_set()
        if sync_set is None:
            return None
        # Dropped before emitting: saving reloads the scene list, which reloads
        # this scene, and must find it saved.
        self._drafts.pop(self._loaded_key, None)
        self.saveRequested.emit(sync_set)
        self._refresh_coverage()
        self.status_label.setText(
            self.tr("Saved: {count} message(s) in the {scene} sync set of {controller}.").format(
                count=len(sync_set.messages), scene=sync_set.scene, controller=sync_set.controller
            )
        )
        return sync_set


__all__ = ["AtelierView"]
