"""Coalesced redraws for the controller drawings that follow live MIDI.

`ControllerLayoutView` (By Channel / Deck / Controller) and
`EmulatorLayoutView` redraw their whole graphics scene on every change, and
`QGraphicsScene.clear()` alone costs ~10 ms on a real controller photo. When
every live MIDI event triggered that -- 18 redraws per jog-wheel tick across
the three schematic tabs, plus one more per 220 ms flash expiry -- a burst of
a few hundred events (a jog turned, Serato's LED feedback) took minutes to
work through and the window froze until the process was killed.

`DeferredRebuild` keeps each view's own ``_rebuild_scene()`` but routes every
request through :meth:`_rebuild`:

- inside :meth:`begin_batch` / :meth:`end_batch` (one Live Monitor read, i.e.
  every event of one MIDI poll), requests only mark the view dirty and the
  batch ends with a single redraw;
- a view that isn't visible in its window (a tab that isn't current) only
  marks itself dirty and redraws when it is shown;
- flash pulses share one timer per view (:meth:`_flash`), so a burst's
  expiries clear together in one redraw instead of one redraw each.

Outside a batch, a visible view still redraws at once, as before.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer


class DeferredRebuild:
    """Mixin for a QWidget with a ``_rebuild_scene()`` method and a
    ``_flash_keys`` set."""

    def _init_deferred_rebuild(self, flash_duration_ms: int) -> None:
        self._batch_depth = 0
        self._rebuild_pending = False
        self._flash_duration = flash_duration_ms / 1000.0
        self._flash_expiry: dict[object, float] = {}
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._expire_flashes)

    # --- requests -------------------------------------------------------------

    def _rebuild(self) -> None:
        if self._batch_depth or not self._shown_in_window():
            self._rebuild_pending = True
            return
        self._rebuild_pending = False
        self._rebuild_scene()

    def _shown_in_window(self) -> bool:
        # A widget on a tab that isn't current is hidden by its stacked
        # widget. A view that is its own window (standalone, or not placed
        # yet) counts as shown: Qt reports a never-shown window as hidden.
        if self.isWindow():
            return True
        return self.isVisibleTo(self.window())

    def begin_batch(self) -> None:
        self._batch_depth += 1

    def end_batch(self) -> None:
        self._batch_depth = max(0, self._batch_depth - 1)
        if not self._batch_depth and self._rebuild_pending:
            self._rebuild()

    def flush_rebuild(self) -> None:
        """Redraw now if anything is pending (tests, before reading the scene)."""
        if self._rebuild_pending:
            self._rebuild_pending = False
            self._rebuild_scene()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._rebuild_pending and not self._batch_depth:
            self._rebuild_pending = False
            self._rebuild_scene()

    # --- flashes ---------------------------------------------------------------

    def _flash(self, key) -> None:
        """Lights `key` for the flash duration; every pending expiry shares
        one timer."""
        self._flash_keys.add(key)
        self._flash_expiry[key] = time.monotonic() + self._flash_duration
        self._rebuild()
        if not self._flash_timer.isActive():
            self._flash_timer.start(int(self._flash_duration * 1000))

    def _expire_flashes(self) -> None:
        now = time.monotonic()
        expired = [key for key, at in self._flash_expiry.items() if at <= now + 0.005]
        for key in expired:
            del self._flash_expiry[key]
            self._flash_keys.discard(key)
        if expired:
            self._rebuild()
        if self._flash_expiry:
            next_at = min(self._flash_expiry.values())
            self._flash_timer.start(max(1, int((next_at - now) * 1000)))

    def _clear_flash(self, key) -> None:
        self._flash_expiry.pop(key, None)
        self._flash_keys.discard(key)
        self._rebuild()


__all__ = ["DeferredRebuild"]
