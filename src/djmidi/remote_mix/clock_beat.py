"""Tempo and beat from a DJ program's MIDI Clock (Traktor sends one).

Traktor can send MIDI Clock (Preferences → MIDI Clock → Send MIDI Clock):
24 ticks per beat, Start / Continue / Stop. That gives a precise tempo and
beat without Ableton Link and without listening to the sound. The ticks are
read by polling, so each one carries a few milliseconds of jitter: the tempo
and the phase come from a straight line fitted through the last ticks, which
averages it out.

Which beat is "one" of the bar isn't sent by MIDI Clock, so the snapshot's
quantum is one beat, like the listening clock (`beat_clock`).

Qt-free; `MidiClockBeat.reader` is a `probe.LinkReader`.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from djmidi.remote_mix.probe import LinkSnapshot

PPQN = 24
CLOCK, START, CONTINUE, STOP = 0xF8, 0xFA, 0xFB, 0xFC
WINDOW = 96  # ticks fitted: four beats
STALE_S = 0.5  # no tick for this long: the clock stopped


class MidiClockBeat:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._ticks: deque[tuple[int, float]] = deque(maxlen=WINDOW)  # (tick number, time)
        self._count = 0
        self.running = False

    def feed(self, status: int, at: float | None = None) -> None:
        """One realtime byte (clock, start, continue, stop) heard at ``at``."""
        at = self._clock() if at is None else at
        if status == START:
            self._ticks.clear()
            self._count = 0
            self.running = True
        elif status == CONTINUE:
            self.running = True
        elif status == STOP:
            self.running = False
        elif status == CLOCK:
            self._ticks.append((self._count, at))
            self._count += 1

    def _fit(self) -> tuple[float, float] | None:
        """(seconds per tick, time of tick 0) by least squares."""
        if len(self._ticks) < PPQN:
            return None
        n = len(self._ticks)
        mean_i = sum(i for i, _t in self._ticks) / n
        mean_t = sum(t for _i, t in self._ticks) / n
        var = sum((i - mean_i) ** 2 for i, _t in self._ticks)
        if var == 0:
            return None
        slope = sum((i - mean_i) * (t - mean_t) for i, t in self._ticks) / var
        if slope <= 0:
            return None
        return slope, mean_t - slope * mean_i

    def snapshot(self, now: float | None = None) -> LinkSnapshot | None:
        now = self._clock() if now is None else now
        if not self._ticks or now - self._ticks[-1][1] > STALE_S:
            return None
        fit = self._fit()
        if fit is None:
            return None
        per_tick, origin = fit
        tempo = 60.0 / (per_tick * PPQN)
        beat = (now - origin) / per_tick / PPQN
        return LinkSnapshot(tempo=tempo, beat=beat, at=now, peers=0, quantum=1.0)

    def reader(self) -> LinkSnapshot | None:
        """A `probe.LinkReader`."""
        return self.snapshot()


__all__ = ["CLOCK", "CONTINUE", "PPQN", "START", "STOP", "MidiClockBeat"]
