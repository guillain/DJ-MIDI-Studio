"""Logs where the GUI thread is stuck when the window stops responding.

A freeze leaves nothing in the log by itself: the GUI thread is busy, so it
writes nothing until it is done -- or until the user kills the process. The
watchdog keeps a heartbeat on the GUI thread (a `QTimer`) and checks it from
a background thread. When the heartbeat is late by more than `threshold`
seconds it logs a warning with the GUI thread's current stack (the exact
call it is stuck in), once per freeze, then how long the freeze lasted once
the heartbeat comes back.

:meth:`FreezeWatchdog.check` holds the decision and takes the clock and the
stack reader as arguments, so it is tested without threads or a real freeze.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_MS = 500
THRESHOLD_SECONDS = 5.0


def gui_thread_stack(thread_id: int) -> str:
    """The current stack of the thread `thread_id`, formatted."""
    frame = sys._current_frames().get(thread_id)
    if frame is None:
        return "(stack unavailable)"
    return "".join(traceback.format_stack(frame))


class FreezeWatchdog(QObject):
    def __init__(
        self,
        parent: QObject | None = None,
        threshold: float = THRESHOLD_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(parent)
        self.threshold = threshold
        self._clock = clock
        self._last_beat = clock()
        self._frozen_since: float | None = None
        self._gui_thread_id = threading.get_ident()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(HEARTBEAT_MS)
        self._timer.timeout.connect(self.beat)

    # --- GUI thread ---------------------------------------------------------------

    def beat(self) -> None:
        """The heartbeat; also reports the end of a freeze."""
        now = self._clock()
        if self._frozen_since is not None:
            _LOGGER.warning("Window responsive again after %.1f s", now - self._frozen_since)
            self._frozen_since = None
        self._last_beat = now

    # --- watchdog thread -------------------------------------------------------------

    def check(self, stack_reader: Callable[[int], str] = gui_thread_stack) -> str | None:
        """The warning to log when the heartbeat is late (once per freeze)."""
        now = self._clock()
        late = now - self._last_beat
        if late < self.threshold or self._frozen_since is not None:
            return None
        self._frozen_since = self._last_beat
        return (
            f"Window not responding for {late:.1f} s -- the GUI thread is busy here:\n"
            f"{stack_reader(self._gui_thread_id)}"
        )

    def _run(self) -> None:
        while not self._stop.wait(1.0):
            message = self.check()
            if message:
                _LOGGER.warning(message)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._last_beat = self._clock()
        self._timer.start()
        self._thread = threading.Thread(target=self._run, name="djmidi-freeze-watchdog", daemon=True)
        self._thread.start()
        _LOGGER.info("Freeze watchdog on (warns after %.0f s without a response)", self.threshold)

    def stop(self) -> None:
        self._timer.stop()
        self._stop.set()
        self._thread = None


__all__ = ["FreezeWatchdog", "gui_thread_stack"]
