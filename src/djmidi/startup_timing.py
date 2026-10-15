"""Startup timing log (issue #264): how long the app takes to show a window.

Qt-free on purpose. ``djmidi.main()`` calls :func:`begin` before importing
the GUI package (so module import time is counted too), ``gui.app.run()``
marks each startup phase on the same timer, and the summary is logged once
the event loop has turned once -- the point where the window is actually on
screen. A launch that skipped ``main()`` (tests, ``python -m``) starts its own
timer inside ``run()`` instead, which simply leaves import time out.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

FIRST_WINDOW_MILESTONE = "first window"


@dataclass
class StartupTimer:
    """Named milestones measured from one start instant, in seconds."""

    clock: Callable[[], float] = time.perf_counter
    start: float | None = None
    milestones: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.start is None:
            self.start = self.clock()

    def mark(self, name: str) -> float:
        """Record ``name`` now; return its offset from the start."""
        elapsed = self.clock() - self.start
        self.milestones.append((name, elapsed))
        return elapsed

    def elapsed(self, name: str) -> float | None:
        """The offset recorded for ``name`` (its first mark), or None."""
        return next((offset for label, offset in self.milestones if label == name), None)

    def summary(self) -> str:
        """One log line: each phase's own duration, then the cumulative total.

        ``"imports 210 ms, main window built 780 ms (total 990 ms)"`` --
        per-phase deltas are what point at a slow step; the total is the
        number a user feels.
        """
        if not self.milestones:
            return "no startup milestones recorded"
        parts = []
        previous = 0.0
        for name, offset in self.milestones:
            parts.append(f"{name} {_ms(offset - previous)}")
            previous = offset
        return f"{', '.join(parts)} (total {_ms(self.milestones[-1][1])})"


def _ms(seconds: float) -> str:
    return f"{max(seconds, 0.0) * 1000:.0f} ms"


_current: StartupTimer | None = None


def begin() -> StartupTimer:
    """Start the process-wide timer (call as early as possible)."""
    global _current
    _current = StartupTimer()
    return _current


def take() -> StartupTimer:
    """Hand over the timer :func:`begin` started (a fresh one if it never
    ran) and forget it, so a second ``run()`` in the same process (tests)
    starts clean instead of appending to the first one's milestones."""
    global _current
    timer = _current if _current is not None else StartupTimer()
    _current = None
    return timer


__all__ = ["FIRST_WINDOW_MILESTONE", "StartupTimer", "begin", "take"]
