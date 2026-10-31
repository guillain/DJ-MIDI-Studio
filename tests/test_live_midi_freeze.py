"""Live MIDI bursts must not freeze the window (RCA in gui/deferred_rebuild.py).

Before the fix, every live event redrew every controller drawing (By Channel /
Deck / Controller and the emulators), each redraw ~10 ms: a 614-event burst
from a jog wheel kept the GUI thread busy for ~2.5 minutes. These tests count
redraws, not seconds, so they hold on any machine."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from djmidi.gui import live_monitor as live_monitor_mod
from djmidi.gui.controller_emulator import EmulatorLayoutView
from djmidi.gui.freeze_watchdog import FreezeWatchdog
from djmidi.gui.layout_view import ControllerLayoutView
from djmidi.midi_io import MidiEvent

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _count_rebuilds(monkeypatch, cls):
    calls = []
    original = cls._rebuild_scene

    def counted(self):
        calls.append(self)
        return original(self)

    monkeypatch.setattr(cls, "_rebuild_scene", counted)
    return calls


def _jog(i, port="XDJ-XZ (1)"):
    return MidiEvent("in", "1", "Control Change", "34", "65", float(i), port)


def _pad(i):
    return MidiEvent("in", "8", "Note On", str(i % 16), "127" if i % 2 == 0 else "0", float(i), "DDJ-XP2")


class _FakeMonitor:
    def __init__(self, events):
        self.events = events

    def poll(self):
        events, self.events = self.events, []
        return events


@pytest.mark.parametrize("make_event", [_jog, _pad])
def test_a_burst_redraws_each_drawing_once_not_once_per_event(monkeypatch, make_event):
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        window._load_mapping_from_path(FIXTURE, software_id="serato")
        window.left_tabs.setCurrentIndex(window._tab_indexes["channel"])
        window.show()
        window._create_emulator_instance("XDJ-XZ")
        rebuilds = _count_rebuilds(monkeypatch, ControllerLayoutView)
        emulator_rebuilds = _count_rebuilds(monkeypatch, EmulatorLayoutView)
        window.live_monitor_view._monitor = _FakeMonitor([make_event(i) for i in range(600)])
        window.live_monitor_view._poll()
        # The visible By Channel drawing redraws once; the two hidden tabs
        # wait until shown; the emulator redraws once.
        assert len(rebuilds) <= 1
        assert len(emulator_rebuilds) <= 1
        assert window.live_monitor_view._log.rowCount() > 0
    finally:
        window.close()


def test_hidden_view_redraws_when_shown_and_flashes_expire_together(monkeypatch):
    from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

    tabs = QTabWidget()
    first = ControllerLayoutView()
    tabs.addTab(first, "a")
    tabs.addTab(QWidget(), "b")
    tabs.show()
    tabs.setCurrentIndex(1)
    QApplication.processEvents()
    rebuilds = _count_rebuilds(monkeypatch, ControllerLayoutView)
    for key in (("x",), ("y",), ("z",)):
        first.flash_key(key)
    assert rebuilds == [] and first._rebuild_pending
    tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert len(rebuilds) == 1
    # Every flash of the burst shares one expiry timer: one redraw to clear them.
    first._flash_expiry = dict.fromkeys(first._flash_expiry, 0.0)
    first._expire_flashes()
    assert len(rebuilds) == 2 and not first._flash_keys
    tabs.close()


def test_batches_nest_and_redraw_once(monkeypatch):
    view = ControllerLayoutView()
    rebuilds = _count_rebuilds(monkeypatch, ControllerLayoutView)
    view.begin_batch()
    view.begin_batch()
    view.spin_jog(("jog",), 3)
    view.set_value(("knob",), 64)
    view.end_batch()
    assert rebuilds == []
    view.end_batch()
    assert len(rebuilds) == 1
    view.spin_jog(("jog",), 1)  # outside a batch: immediate, as before
    assert len(rebuilds) == 2


def test_slow_and_large_batches_are_logged(monkeypatch, caplog):
    view = live_monitor_mod.LiveMonitorView()
    view._monitor = _FakeMonitor([_jog(i) for i in range(250)])
    with caplog.at_level(logging.INFO, logger=live_monitor_mod.__name__):
        view._poll()
    assert "Live MIDI burst: 250 event(s)" in caplog.text
    assert "XDJ-XZ (1) Control Change ch1 #34 ×250" in caplog.text
    monkeypatch.setattr(live_monitor_mod, "SLOW_BATCH_MS", 0)
    view._monitor = _FakeMonitor([_jog(1)])
    with caplog.at_level(logging.WARNING, logger=live_monitor_mod.__name__):
        view._poll()
    assert "took" in caplog.text and "the window doesn't respond" in caplog.text


def test_watchdog_reports_a_freeze_once_with_the_stack_then_its_end(caplog):
    now = [100.0]
    dog = FreezeWatchdog(threshold=5.0, clock=lambda: now[0])
    dog.beat()
    now[0] += 3
    assert dog.check(lambda _id: "stack") is None
    now[0] += 4
    message = dog.check(lambda _id: 'File "main_window.py", line 42, in _rebuild')
    assert "not responding for 7.0 s" in message and "main_window.py" in message
    now[0] += 10
    assert dog.check(lambda _id: "stack") is None  # reported once per freeze
    with caplog.at_level(logging.WARNING):
        dog.beat()
    assert "responsive again after 17.0 s" in caplog.text
    now[0] += 1
    assert dog.check(lambda _id: "stack") is None
