"""Controller Emulator (issue #9, phase 1 of the agreed roadmap): a single,
interactive schematic for one controller. Click a pad/button to see which
Serato function the currently loaded mapping resolves it to.

Phase 3 (continuous controls) is delivered: dragging a knob/fader/jog glyph
vertically sets its value (_ClickableEmulatorView, _DRAG_KINDS), reusing
draw_control_glyph()'s existing knob-rotation/fader-thumb math via
EmulatorLayoutView.set_value() -- but deliberately display-only, not
reopening "continuous controls are out of catalog scope" as a side effect:
these visual kinds have no ControlInfo at all, so a drag only ever moves
the glyph, never dry-run-resolves or live-sends (a discrete pad/button
click is unaffected, still routed through controlPressed as before). No
persistent *state* beyond that one local value: SHIFT/pad-mode-page
tracking is phase 5's job; a clicked discrete cell with several
raw-trigger variants still always resolves to one fixed, documented
default -- see layout.pick_default_variant. Multiple simultaneous emulator
windows (phase 2) and real MIDI output (phase 4, partially: dry-run
resolution always happens, and a click also sends a real MIDI message when
the embedded LiveSendControl -- gui/live_send.py, shared with
ControllerLayoutView and ControllerImageView -- is switched on, default
off) are both delivered too.

This does NOT extend gui.layout_view.ControllerLayoutView: that widget's
entire contract is a two-controller diff/audit view (a tab bar, a deck
filter, and a split-half "what does the *other* controller think this
trigger means" row) for the By Channel/Deck/Controller tabs, none of which
fits a single-controller interactive emulator. Instead this reuses the
already-free-standing pieces of that module: layout.build_layout(),
layout_view.metrics_for(), layout_view.draw_control_glyph() (extracted from
ControllerLayoutView._draw_control_shape for exactly this reuse), and
layout_view.real_position_markers() -- for a controller with measured
geometry (gui/geometry.CONTROL_GEOMETRY), this schematic now draws the
exact same real-position markers ControllerLayoutView's real-position mode
does (same rects, same glyphs), so the two read identically rather than
diverging into two independent layouts for the same controller, which the
maintainer explicitly asked for after phase R1 gave ControllerLayoutView
real-position rendering but left this emulator on the old uniform grid.
A controller with no geometry still falls back to that uniform grid here
too, matching ControllerLayoutView's own fallback."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsEllipseItem,
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


_KIND_ROLE = layout_view._KIND_ROLE
# Continuous controls -- drag-to-set instead of click-to-resolve (phase 3).
# Deliberately *not* extending catalog scope: these visual kinds have no
# ControlInfo at all (see the module docstring), so a drag only ever moves
# the glyph, never dry-run-resolves or live-sends anything.
_DRAG_KINDS = frozenset({"knob", "fader", "jog"})
# Pixels of vertical drag per one-unit change in the 0-127 MIDI value --
# higher = coarser/less sensitive. Matches a typical software-knob feel
# (a few hundred px of drag to sweep the full range) rather than a literal
# 1:1 pixel mapping, which would make the small glyphs impossible to set
# precisely.
_DRAG_PX_PER_UNIT = 2.5


class _ClickableEmulatorView(QGraphicsView):
    controlPressed = Signal(tuple)  # CellKey
    valueDragged = Signal(tuple, int)  # CellKey, new 0-127 value
    viewportResized = Signal()

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        # Set by EmulatorLayoutView right after construction -- reads the
        # continuous control's *current* value so a drag starts from
        # wherever the glyph was last left, not always from the default.
        self.value_provider: Callable[[CellKey], int] | None = None
        self._drag_key: CellKey | None = None
        self._drag_start_y: float = 0.0
        self._drag_start_value: int = 0

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            key = item.data(_KEY_ROLE)
            if key is not None:
                if item.data(_KIND_ROLE) in _DRAG_KINDS:
                    self._drag_key = key
                    self._drag_start_y = event.position().y()
                    self._drag_start_value = (
                        self.value_provider(key) if self.value_provider is not None else layout_view._MIDI_DEFAULT
                    )
                else:
                    self.controlPressed.emit(key)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_key is not None:
            # Dragging up increases the value, matching a physical fader/
            # knob's usual "up = more" convention.
            delta = (self._drag_start_y - event.position().y()) / _DRAG_PX_PER_UNIT
            new_value = max(0, min(127, round(self._drag_start_value + delta)))
            self.valueDragged.emit(self._drag_key, new_value)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # A drag never counts as a "press" -- no dry-run resolution or live
        # send for a continuous control, which has no ControlInfo at all to
        # resolve (see the module docstring); it only ever moves the glyph.
        self._drag_key = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # See ControllerLayoutView's identical _ClickableView.resizeEvent
        # for why this view's own resize (not the outer widget's) is the
        # reliable trigger for re-fitting real-position mode.
        self.viewportResized.emit()


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
        # Last drag-to-set value (0-127) per continuous-control key (phase
        # 3) -- a level, not a pulse, like ControllerLayoutView's own
        # set_value(): it persists wherever the glyph was last left. No
        # dry-run/live-send meaning at all (these keys have no ControlInfo),
        # purely local visual state for the emulator's own interaction.
        self._values: dict[CellKey, int] = {}
        # Set by _rebuild(); resizeEvent/_fit_view() use it instead of
        # recomputing real_position_markers() on every resize.
        self._real_position_mode = False

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(layout_view._SCENE_BRUSH)
        self._view = _ClickableEmulatorView(self._scene)
        self._view.setStyleSheet(
            "background: #0d1119; border: 1px solid #2b3b53; border-radius: 8px;"
        )
        self._view.value_provider = self._current_value
        self._view.controlPressed.connect(self._on_control_pressed)
        self._view.valueDragged.connect(self.set_value)
        self._view.viewportResized.connect(self._fit_view)

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
        self._values.clear()
        self._rebuild()

    def _current_value(self, key: CellKey) -> int:
        return self._values.get(key, layout_view._MIDI_DEFAULT)

    def set_value(self, key: CellKey, value: int) -> None:
        """Drag-to-set a knob/fader/jog glyph (phase 3) -- reuses
        draw_control_glyph()'s existing knob-rotation/fader-thumb math via
        _rebuild(), the same way ControllerLayoutView's own set_value()
        (live MIDI values) already does."""
        if self._values.get(key) == value:
            return
        self._values[key] = value
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
            self._real_position_mode = False
            self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))
            return
        markers = layout_view.real_position_markers(self._controller)
        self._real_position_mode = bool(markers)
        if markers:
            self._rebuild_real_position(markers)
        else:
            self._rebuild_classic_grid()

    def _rebuild_real_position(self, markers: list[layout_view.RealPositionMarker]) -> None:
        """Identical rendering to ControllerLayoutView's own real-position
        mode (same markers, same rects, same glyphs) -- see
        layout_view.real_position_markers()'s docstring for why this is a
        shared function rather than two independently-drifting layouts.
        No deck-usage coloring here (this schematic has no loaded-mapping
        concept beyond the dry-run status label below it): a marker rests
        at its own semantic color, like Controller Images, and flashes
        white on press."""
        canvas_w, canvas_h = layout_view._reference_canvas_size(self._controller)
        for marker in markers:
            rect = marker.rect
            bg_item: QGraphicsRectItem | QGraphicsEllipseItem = (
                QGraphicsEllipseItem(rect) if marker.shape == "circle" else QGraphicsRectItem(rect)
            )
            if marker.key in self._flash_keys:
                bg_item.setBrush(layout_view._FLASH_BRUSH)
            else:
                resting = QColor(marker.color)
                resting.setAlpha(90)
                bg_item.setBrush(QBrush(resting))
            bg_item.setPen(layout_view._BORDER_PEN)
            bg_item.setData(_KEY_ROLE, marker.key)
            bg_item.setData(_KIND_ROLE, marker.visual_kind)
            bg_item.setToolTip(f"{self._controller} — {marker.label}")
            self._scene.addItem(bg_item)

            glyph_size = layout_view.glyph_size_for(self._metrics, marker.visual_kind)
            glyph_x = rect.center().x() - glyph_size / 2 - 8
            glyph_y = rect.center().y() - glyph_size / 2 - 8
            layout_view.draw_control_glyph(
                self._scene, self._metrics, glyph_x, glyph_y, marker.visual_kind, marker.key,
                self._values.get(marker.key), marker.key in self._flash_keys,
            )
        self._scene.setSceneRect(0, 0, canvas_w, canvas_h)
        self._fit_view()

    def _rebuild_classic_grid(self) -> None:
        """A controller with no gui/geometry.CONTROL_GEOMETRY entries --
        the same uniform-card fallback ControllerLayoutView's classic mode
        uses, unchanged from before real-position mode existed."""
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
            rect.setData(_KIND_ROLE, cell.visual_kind)
            rect.setToolTip(f"{cell.key[0]} — {cell.key[1]} {cell.label}")
            self._scene.addItem(rect)
            layout_view.draw_control_glyph(
                self._scene, m, x, y, cell.visual_kind, cell.key,
                self._values.get(cell.key), cell.key in self._flash_keys,
            )
            label = QGraphicsSimpleTextItem(layout_view._elide(cell.label, 24))
            label.setFont(small_font)
            label.setPos(x + m.label_x, y + 2)
            label.setBrush(QColor("#f3f6fb"))
            label.setData(_KEY_ROLE, cell.key)
            self._scene.addItem(label)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10))

    def _fit_view(self) -> None:
        """Auto-fits to the available window space in real-position mode
        (matching ControllerLayoutView's own auto-fit); a no-op for the
        classic grid, which keeps its existing natural-size behavior."""
        if not self._real_position_mode:
            return
        self._view.resetTransform()
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


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
