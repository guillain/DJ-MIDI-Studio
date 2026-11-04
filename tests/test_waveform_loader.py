"""GUI side of the waveform overview (issue #407). Fake compute functions
only: no real audio decoding here, that's `test_library_waveform.py`'s job.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from djmidi.gui.waveform_loader import WaveformLoader


def _wait_for(pool, results, expected=1):
    pool.waitForDone(5000)
    for _ in range(50):
        QApplication.processEvents()
        if len(results) >= expected:
            return


def test_waveform_loader_runs_off_the_main_thread_and_reports_back():
    loader = WaveformLoader(compute=lambda path: [0.1, 0.9, 0.2])
    results = []
    loader.finished.connect(lambda *args: results.append(args))
    pool = QThreadPool()
    loader.load("/music/a.mp3", 7, 123.0, pool=pool)
    _wait_for(pool, results)
    assert results == [("/music/a.mp3", 7, 123.0, [0.1, 0.9, 0.2])]


def test_waveform_loader_reports_none_on_a_decode_failure():
    def failing(path):
        raise RuntimeError("librosa is required for the waveform overview")

    loader = WaveformLoader(compute=failing)
    results = []
    loader.finished.connect(lambda *args: results.append(args))
    pool = QThreadPool()
    loader.load("/music/a.mp3", 7, 123.0, pool=pool)
    _wait_for(pool, results)
    assert results == [("/music/a.mp3", 7, 123.0, None)]


def test_waveform_loader_can_run_several_loads():
    loader = WaveformLoader(compute=lambda path: [len(path) / 10.0])
    results = []
    loader.finished.connect(lambda *args: results.append(args))
    pool = QThreadPool()
    loader.load("/a.mp3", 1, 1.0, pool=pool)
    loader.load("/bb.mp3", 2, 2.0, pool=pool)
    _wait_for(pool, results, expected=2)
    assert {result[1] for result in results} == {1, 2}
