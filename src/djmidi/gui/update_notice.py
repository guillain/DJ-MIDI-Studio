"""Runs the GitHub release check off the main thread (issue #193).

The network call (``update_check.latest_release``) happens in a
``QThreadPool`` worker so a slow or offline network never blocks startup;
the result comes back to the main thread through the ``finished`` signal.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from djmidi.update_check import Fetcher, latest_release


class UpdateChecker(QObject):
    # (ReleaseInfo | None, manual): manual is True for Help → Check for Updates…
    finished = Signal(object, bool)
    _result = Signal(object, bool)

    def __init__(self, parent: QObject | None = None, fetch: Fetcher | None = None) -> None:
        super().__init__(parent)
        # Tests inject a fake fetcher; None means the real urllib request.
        self.fetch = fetch
        self.running = False
        self._result.connect(self._deliver)

    def start(self, manual: bool = False, pool: QThreadPool | None = None) -> bool:
        """Starts one background check; False when one is already running."""
        if self.running:
            return False
        self.running = True
        (pool or QThreadPool.globalInstance()).start(_CheckTask(self, manual))
        return True

    def _deliver(self, release: object, manual: bool) -> None:
        self.running = False
        self.finished.emit(release, manual)


class _CheckTask(QRunnable):
    def __init__(self, checker: UpdateChecker, manual: bool) -> None:
        super().__init__()
        self._checker = checker
        self._manual = manual

    def run(self) -> None:
        release = latest_release(self._checker.fetch)
        # Emitted from the worker thread: the auto connection to _deliver is
        # queued, so _deliver (and every finished slot) runs on the main thread.
        self._checker._result.emit(release, self._manual)
