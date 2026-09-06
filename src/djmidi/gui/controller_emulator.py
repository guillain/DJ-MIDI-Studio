"""Controller Emulator (issue #9, phase 1 of the agreed roadmap): a single,
interactive schematic for one controller. Click a pad/button to see which
Serato function the currently loaded mapping resolves it to.

Deliberately narrow for this first phase: discrete controls only (no
drag/spin for knobs/faders/jog wheels -- that's phase 3), no persistent
state (SHIFT/pad-mode-page tracking is phase 5's job; a clicked cell with
several raw-trigger variants always resolves to one fixed, documented
default -- see layout.pick_default_variant), and a single fixed dock
instance (multiple simultaneous emulator windows are phase 2). Phase 4
(real MIDI output) is partially delivered: dry-run resolution always
happens, and a click also sends a real MIDI message when the embedded
LiveSendControl (gui/live_send.py, shared with ControllerLayoutView and
ControllerImageView) is switched on -- default off.

This does NOT extend gui.layout_view.ControllerLayoutView: that widget's
entire contract is a two-controller diff/audit view (a tab bar, a deck
filter, and a split-half "what does the *other* controller think this
trigger means" row) for the By Channel/Deck/Controller tabs, none of which
fits a single-controller interactive emulator. Instead this reuses the
already-free-standing pieces of that module: layout.build_layout(),
layout_view.metrics_for(), and layout_view.draw_control_glyph() (extracted
from ControllerLayoutView._draw_control_shape for exactly this reuse)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui import layout as layout_mod
from djmidi.gui import layout_view
from djmidi.gui.layout import CellKey
from djmidi.gui.live_send import LiveSendControl
from djmidi.gui.mapping_group import build_mapping_groups
from djmidi.model import MidiConfig

_KEY_ROLE = layout_view._KEY_ROLE
_FLASH_DURATION_MS = 220

# NOTE/CC -> the model's own event_type string convention (see CLAUDE.md:
# "MidiEvent.channel/event_type/data1 are pre-formatted to match
# model.Control's string convention"), so a picked ControlInfo's trigger can
# be looked up directly against a MappingGroup's (channel, event_type,
# control_no) key.
_EVENT_TYPE_FOR_KIND: dict[catalog.NoteOrCC, str] = {"NOTE": "Note On", "CC": "Control Change"}

# Moved to layout.py (as pick_default_variant) so gui/live_send.py's
# real-MIDI-send path can share the exact same "which variant does an
# ambiguous cell mean" rule instead of a second, independently-drifting
# copy -- re-exported under the old private name so this module's own call
# site and tests/test_controller_emulator.py don't need to change.
_pick_default_variant = layout_mod.pick_default_variant


def _dry_run_lookup(config: MidiConfig) -> dict[tuple[str, str, str], list[str]]:
    """(channel, event_type, control_no) -> the Serato function(s) it's bound
    to, restricted to click (input) triggers -- mirrors
    LiveMonitorView.set_config()'s own _function_lookup construction."""
    lookup: dict[tuple[str, str, str], list[str]] = {}
    for group in build_mapping_groups(config):
        if group.event != "click":
            continue
        key = (group.channel, group.event_type, group.control_no)
        lookup.setdefault(key, []).append(f"Deck {group.deck_id} slot {group.slot_id}: {group.tag}")
    return lookup


class _ClickableEmulatorView(QGraphicsView):
    controlPressed = Signal(tuple)  # CellKey

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is not None:
            key = item.data(_KEY_ROLE)
            if key is not None:
                self.controlPressed.emit(key)
        super().mousePressEvent(event)


class EmulatorLayoutView(QWidget):
    """A single controller's interactive, clickable schematic -- one flat row
    per cell (no split-half "other controller" comparison, no tab bar, no
    deck filter). Clicking a pad/button flashes it and emits its CellKey."""

    controlPressed = Signal(tuple)  # CellKey

    def __init__(self, controller: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._metrics = layout_view.metrics_for(controller)
        self._flash_keys: set[CellKey] = set()

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(layout_view._SCENE_BRUSH)
        self._view = _ClickableEmulatorView(self._scene)
        self._view.setStyleSheet(
            "background: #0d1119; border: 1px solid #2b3b53; border-radius: 8px;"
        )
        self._view.controlPressed.connect(self._on_control_pressed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self._rebuild()

    def set_controller(self, controller: str) -> None:
        if controller == self._controller:
            return
        self._controller = controller
        self._metrics = layout_view.metrics_for(controller)
        self._flash_keys.clear()
        self._rebuild()

    def flash_key(self, key: CellKey) -> None:
        self._flash_keys.add(key)
        self._rebuild()
        QTimer.singleShot(_FLASH_DURATION_MS, lambda k=key: self._clear_flash(k))

    def _clear_flash(self, key: CellKey) -> None:
        self._flash_keys.discard(key)
        self._rebuild()

    def _on_control_pressed(self, key: CellKey) -> None:
        self.flash_key(key)
        self.controlPressed.emit(key)

    def _rebuild(self) -> None:
        self._scene.clear()
        self._scene.setBackgroundBrush(layout_view._SCENE_BRUSH)
        if not self._controller:
            self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))
            return
        m = self._metrics
        col_step = m.cell_w + m.margin
        row_step = m.half_h + m.margin
        small_font = QFont()
        small_font.setPointSize(7)
        for cell in layout_mod.build_layout(self._controller):
            x = cell.col * col_step
            y = cell.row * row_step
            rect = QGraphicsRectItem(QRectF(0, 0, m.cell_w, m.half_h))
            rect.setPos(x, y)
            rect.setBrush(layout_view._UNUSED_BRUSH)
            rect.setPen(layout_view._BORDER_PEN)
            rect.setData(_KEY_ROLE, cell.key)
            rect.setToolTip(f"{cell.key[0]} — {cell.key[1]} {cell.label}")
            self._scene.addItem(rect)
            layout_view.draw_control_glyph(
                self._scene, m, x, y, cell.visual_kind, cell.key,
                None, cell.key in self._flash_keys,
            )
            label = QGraphicsSimpleTextItem(layout_view._elide(cell.label, 24))
            label.setFont(small_font)
            label.setPos(x + m.label_x, y + 2)
            label.setBrush(QColor("#f3f6fb"))
            label.setData(_KEY_ROLE, cell.key)
            self._scene.addItem(label)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))


class ControllerEmulatorView(QWidget):
    """Dock content for the Controller Emulator: pick a controller, click its
    schematic, see what the currently loaded mapping resolves that trigger
    to. Dry-run resolution always happens; a click additionally sends a real
    MIDI message to a chosen output port when the embedded LiveSendControl
    (gui/live_send.py) is switched on (default off) -- see that module's
    docstring for why every layout surface uses the same widget/default."""

    def __init__(
        self,
        config_provider: Callable[[], MidiConfig | None],
        initial_controller: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_provider = config_provider

        self._combo = QComboBox()
        self._combo.addItems(catalog.CONTROLLER_NAMES)

        initial = initial_controller if initial_controller in catalog.CONTROLLER_NAMES else (
            catalog.CONTROLLER_NAMES[0] if catalog.CONTROLLER_NAMES else ""
        )
        if initial:
            self._combo.setCurrentText(initial)
        # Connected after the initial selection so constructing with a
        # specific initial_controller (see MainWindow._create_emulator_instance)
        # doesn't fire a redundant _on_controller_changed before self._emulator
        # exists.
        self._combo.currentTextChanged.connect(self._on_controller_changed)

        self._emulator = EmulatorLayoutView(initial)
        self._emulator.controlPressed.connect(self._on_control_pressed)

        self._status_label = QLabel("Click a control to see what it resolves to.")
        self._status_label.setWordWrap(True)

        self._live_send = LiveSendControl()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._combo)
        layout.addWidget(self._live_send)
        layout.addWidget(self._emulator, 1)
        layout.addWidget(self._status_label)

    def current_controller(self) -> str:
        """The controller currently selected in this instance -- used by
        MainWindow to persist which controllers had an open emulator
        instance (see MainWindow.closeEvent/_restore_user_layout)."""
        return self._combo.currentText()

    def refresh_controllers(self) -> None:
        """Repopulates the controller combo from the live registry -- call
        after a controller is registered/replaced mid-session (see
        MainWindow._on_controller_applied), since CONTROLLER_NAMES was only
        read once at __init__ time otherwise."""
        current = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(catalog.CONTROLLER_NAMES)
        restored = self._combo.findText(current)
        self._combo.setCurrentIndex(max(restored, 0))
        self._combo.blockSignals(False)
        new_current = self._combo.currentText()
        if new_current:
            self._emulator.set_controller(new_current)

    def _on_controller_changed(self, name: str) -> None:
        if not name:
            return
        self._emulator.set_controller(name)
        self._status_label.setText("Click a control to see what it resolves to.")

    def _on_control_pressed(self, key: CellKey) -> None:
        text = self._resolve(key)
        sent = self._live_send.resolve_and_send(key[0], key)
        if sent is not None:
            text += f"  [LIVE SENT: ch{sent.channels[0] if sent.channels else '?'} {sent.note_or_cc} {sent.data1}]"
        self._status_label.setText(text)

    def _resolve(self, key: CellKey) -> str:
        variants = layout_mod.reverse_lookup(key[0]).get(key)
        if not variants:
            return f"{key[1]} {key[2]}: no raw MIDI trigger known for this control."
        entry = _pick_default_variant(variants)
        channel = entry.channels[0] if entry.channels else "?"
        trigger = f"ch{channel} {entry.note_or_cc} {entry.data1}"
        config = self._config_provider()
        if config is None:
            return f"{key[1]} {key[2]} → {trigger} (no mapping loaded)"
        functions = _dry_run_lookup(config).get(
            (channel, _EVENT_TYPE_FOR_KIND[entry.note_or_cc], entry.data1), []
        )
        if not functions:
            return f"{key[1]} {key[2]} → {trigger}: not mapped in the loaded config"
        return f"{key[1]} {key[2]} → " + "; ".join(functions)


__all__ = ["ControllerEmulatorView", "EmulatorLayoutView"]
