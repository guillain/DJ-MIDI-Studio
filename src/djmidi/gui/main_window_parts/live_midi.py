"""MainWindow, part: Live MIDI from the Live Monitor: batching redraws, routing each event to the layouts, emulators, captures, MIDI Learn and macro triggers, and output-direction LED feedback.

A mixin of `djmidi.gui.main_window.MainWindow` (issue #429); its strings keep the
"MainWindow" translation context."""

from __future__ import annotations

from djmidi import (
    catalog,
)
from djmidi.gui import jog as jog_mod
from djmidi.gui import layout as layout_mod
from djmidi.gui.geometry import (
    CONTROL_GEOMETRY,
    resolve_geometry_label,
)
from djmidi.midi_io import MidiEvent


class LiveMidiMixin:
    def _begin_live_batch(self) -> None:
        """One Live Monitor read starts: the drawings that follow live MIDI
        only record changes until it ends, then redraw once. Without this, a
        burst (a jog turned, LED feedback) redrew every view per event and
        froze the window."""
        self._end_live_batch()
        self._live_batch_views = [
            self.layout_view, self.deck_layout_view, self.controller_layout_view, *self._emulator_views()
        ]
        for view in self._live_batch_views:
            view.begin_batch()

    def _end_live_batch(self) -> None:
        views, self._live_batch_views = self._live_batch_views, []
        for view in views:
            try:
                view.end_batch()
            except RuntimeError:  # an emulator closed during the batch
                continue

    def _ensure_learn_listening(self) -> bool:
        """MIDI Learn listens through the Live Monitor: start it on every
        input if it isn't running yet, and report whether anything is open."""
        self.live_monitor_view.ensure_monitoring_started()
        return self.live_monitor_view.is_running

    def _on_live_midi_event(self, event: MidiEvent) -> None:
        if event.direction == "in" and event.port in self._record_shared_ports:
            self._record_events.append(event)
        # An active MIDI Learn consumes the press it learns; the layouts still
        # react to it below like any other live hit. Otherwise a press bound
        # to a macro (issue #252) plays it -- never while the macro editor is
        # open, whose own Learn may be waiting for exactly that press. While
        # ● Rec records (issue #296) neither happens: the presses are meant
        # for the sync set, not for a macro or a pending Learn.
        if self._record_button.isChecked():
            pass
        elif self._profile_check_dialog is not None and self._profile_check_dialog.feed_event(event):
            pass  # a press being verified (issue #364) is neither a macro nor a Learn
        elif self._hardware_session_dialog is not None and self._hardware_session_dialog.feed_event(event):
            pass  # captured for a hardware session check (issue #426)
        elif (
            self.midi_routing_view.active_transform_dialog is not None
            and self.midi_routing_view.active_transform_dialog.feed_learn_event(event)
        ):
            pass  # a remap Learn (issue #368)
        elif self._macro_dialog is not None:
            self._macro_dialog.feed_learn_event(event)
        elif not self.edit_panel.feed_learn_event(event):
            self._play_triggered_macros(event)
        try:
            value = int(event.data2)
        except (TypeError, ValueError):
            value = None

        # Stage Mode's compact monitor gets every event except jog-wheel
        # ticks: a platter turn sends dozens per second, which would push
        # every meaningful press off its few large lines.
        if self._stage_window is not None and not jog_mod.jog_cell_keys_for_event(
            event.channel, event.event_type, event.data1
        ):
            lookup_type = "Note On" if event.event_type == "Note Off" else event.event_type
            stage_hits = (
                catalog.lookup(event.channel, lookup_type, event.data1)
                if event.channel and event.data1
                else []
            )
            self._stage_window.add_event(event, stage_hits)

        # Output-direction traffic (Serato -> controller LED feedback, seen on
        # the virtual monitor port) drives a *latched* LED highlight, kept
        # separate from the input-direction momentary "held" state so an
        # input release can't clear an LED the software is still driving. We
        # assume the LED note number equals the input trigger note (Serato's
        # own convention for almost every mapping; there's no per-control
        # led_note field in the catalog). No flash, no selection change --
        # this is passive state, not a user gesture.
        if event.direction == "out":
            self._on_output_led_event(event, value)
            return

        # A jog-wheel turn is a stream of relative Control Change ticks that
        # deliberately have no catalog entry (continuous controls are out of
        # catalog scope), so it can't flow through the lookup path below.
        # Resolve it against gui/jog.py's small per-controller table instead
        # and integrate the ticks into each jog glyph's notch angle. Handled
        # before _update_layout_selection so a jog turn never clears the
        # cross-tab selection -- it isn't a "the user picked this control"
        # gesture, just motion feedback.
        jog_keys = jog_mod.jog_cell_keys_for_event(
            event.channel, event.event_type, event.data1
        )
        if jog_keys:
            # Each controller decodes its own relative encoding (the
            # Inpulse 500 is two's complement, the rest 0x40-centred).
            image_controller = self.controller_image_view.current_controller_name()
            for key in jog_keys:
                delta = jog_mod.decode_jog_delta_for_key(key, value)
                if not delta:
                    continue
                for lv in (
                    self.layout_view,
                    self.deck_layout_view,
                    self.controller_layout_view,
                ):
                    lv.spin_jog(key, delta)
                for view in self._emulator_views():
                    view.spin_jog_from_key(key, delta)
                # Spin the Controller Images overlay's own marker when this
                # tab shows that controller: the right-hand "Jog wheel (R)"
                # when the controller's geometry has one (DDJ-REV5, XDJ-XZ),
                # else its single "Jog wheel".
                if key[0] == image_controller:
                    label = key[2]
                    if label not in CONTROL_GEOMETRY.get(image_controller, {}):
                        label = label.removesuffix(layout_mod._RIGHT_GRID_SUFFIX)
                    self.controller_image_view.spin_jog(label, delta)
            return

        # A note release arrives as "Note Off" or as "Note On" with velocity
        # 0 (running status). Catalog entries are all stored as "Note On", so
        # resolve a release against "Note On" too -- the selection/highlight
        # should track the control that was just let go, not vanish.
        is_release = event.event_type == "Note Off" or (
            event.event_type == "Note On" and value == 0
        )
        is_press = event.event_type == "Note On" and (value or 0) > 0
        lookup_type = "Note On" if event.event_type == "Note Off" else event.event_type

        self._update_layout_selection(event.channel, lookup_type, event.data1)
        if not (event.channel and event.event_type and event.data1):
            return
        hits = catalog.lookup(event.channel, lookup_type, event.data1)
        # Same reasoning as _update_layout_selection(): flash/value/hold only
        # the physical marker the live hit's own deck actually belongs to,
        # not both sides of a split cell.
        keys = {layout_mod.presentation_key_for_hit(hit) for hit in hits}
        layouts = (self.layout_view, self.deck_layout_view, self.controller_layout_view)
        for key in keys:
            # Persistent "held down" amber highlight first -- lit on press,
            # cleared on release; a plain CC (neither) leaves it be -- so the
            # 220ms white flash_key() pulse below always paints on top of it
            # for a press (Controller Images mutates its marker in place;
            # order matters there).
            if is_press or is_release:
                for lv in layouts:
                    lv.set_active(key, is_press)
            if not is_release:
                for lv in layouts:
                    lv.flash_key(key)
            if value is not None:
                for lv in layouts:
                    lv.set_value(key, value)

        # The Controller Images tab's real-photo overlay, for whichever
        # controller it currently shows (gui/geometry.py).
        image_controller = self.controller_image_view.current_controller_name()
        for hit in hits:
            if hit.controller != image_controller:
                continue
            label = resolve_geometry_label(hit.controller, hit.name)
            if label is None:
                continue
            if is_press or is_release:
                self.controller_image_view.set_active(label, is_press)
            if not is_release:
                self.controller_image_view.flash_key(label)

        # Every open Controller Emulator dock -- the flash_live_hit /
        # set_live_active_from_hit calls self-filter to the controller each
        # instance shows, so this can run unconditionally over all of them.
        for view in self._emulator_views():
            for hit in hits:
                if is_press or is_release:
                    view.set_live_active_from_hit(hit, is_press)
                if not is_release:
                    view.flash_live_hit(hit)

    def _on_output_led_event(self, event: MidiEvent, value: int | None) -> None:
        """Latch/clear the amber LED highlight from an output-direction MIDI
        note. Only note events count -- a CC on the output port (rare, e.g. a
        motorised fader) has no LED meaning here and is ignored."""
        led_on = event.event_type == "Note On" and (value or 0) > 0
        led_off = event.event_type == "Note Off" or (
            event.event_type == "Note On" and value == 0
        )
        if not (led_on or led_off):
            return
        if not (event.channel and event.data1):
            return
        hits = catalog.lookup(event.channel, "Note On", event.data1)
        keys = {layout_mod.presentation_key_for_hit(hit) for hit in hits}
        layouts = (self.layout_view, self.deck_layout_view, self.controller_layout_view)
        for key in keys:
            for lv in layouts:
                lv.set_led(key, led_on)

        image_controller = self.controller_image_view.current_controller_name()
        for hit in hits:
            if hit.controller == image_controller:
                label = resolve_geometry_label(hit.controller, hit.name)
                if label is not None:
                    self.controller_image_view.set_led(label, led_on)

        for view in self._emulator_views():
            for hit in hits:
                view.set_led_from_hit(hit, led_on)
