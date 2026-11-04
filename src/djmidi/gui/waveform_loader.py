"""Computes a track's waveform envelope off the main thread (issue #407).

Mirrors `gui/update_notice.py`'s `QThreadPool` worker pattern: the decode
(`library.waveform.compute_waveform_peaks`) happens on a worker thread so
auditioning a track never stalls on it, and the result comes back to the
main thread through the `finished` signal. The Music Library tab owns an
instance, checks the DB cache first, and only calls `load()` on a cache
miss; this class knows nothing about `LibraryDB`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from djmidi.library.waveform import compute_waveform_peaks

_LOGGER = logging.getLogger(__name__)

Compute = Callable[[str], list[float]]


class WaveformLoader(QObject):
    # (path, track_id, mtime, peaks | None) -- None on a decode failure.
    finished = Signal(str, int, float, object)
    _result = Signal(str, int, float, object)

    def __init__(self, parent: QObject | None = None, compute: Compute | None = None) -> None:
        super().__init__(parent)
        self._compute = compute or compute_waveform_peaks
        self._result.connect(self.finished.emit)

    def load(self, path: str, track_id: int, mtime: float, pool: QThreadPool | None = None) -> None:
        (pool or QThreadPool.globalInstance()).start(_WaveformTask(self, path, track_id, mtime, self._compute))


class _WaveformTask(QRunnable):
    def __init__(self, loader: WaveformLoader, path: str, track_id: int, mtime: float, compute: Compute) -> None:
        super().__init__()
        self._loader = loader
        self._path = path
        self._track_id = track_id
        self._mtime = mtime
        self._compute = compute

    def run(self) -> None:
        try:
            peaks: list[float] | None = self._compute(self._path)
        except Exception:
            _LOGGER.warning("Could not compute the waveform for %s", self._path, exc_info=True)
            peaks = None
        # Emitted from the worker thread: the auto connection to _result's
        # listener is queued, so it runs on the main thread.
        self._loader._result.emit(self._path, self._track_id, self._mtime, peaks)


__all__ = ["WaveformLoader"]
