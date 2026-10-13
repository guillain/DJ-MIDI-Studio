"""Tests for djmidi/startup_timing.py (issue #264): Qt-free, fake clock."""
from __future__ import annotations

from djmidi import startup_timing
from djmidi.startup_timing import StartupTimer


class _FakeClock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


def test_mark_records_offsets_from_the_start():
    clock = _FakeClock()
    timer = StartupTimer(clock=clock)
    clock.now = 10.25
    assert timer.mark("imports") == 0.25
    clock.now = 11.0
    assert timer.mark("main window built") == 1.0
    assert timer.elapsed("imports") == 0.25
    assert timer.elapsed("missing") is None


def test_summary_lists_each_phase_duration_then_the_total():
    clock = _FakeClock()
    timer = StartupTimer(clock=clock)
    clock.now = 10.2
    timer.mark("imports")
    clock.now = 11.0
    timer.mark("main window built")
    assert timer.summary() == "imports 200 ms, main window built 800 ms (total 1000 ms)"


def test_summary_without_milestones():
    assert StartupTimer().summary() == "no startup milestones recorded"


def test_take_hands_over_the_begun_timer_once():
    begun = startup_timing.begin()
    assert startup_timing.take() is begun
    fresh = startup_timing.take()
    assert fresh is not begun
    assert fresh.milestones == []
