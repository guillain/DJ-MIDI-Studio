"""Keep two Link sessions, in two homes, on one tempo and one beat (remote
mix, phase 1).

Link itself only reaches one local network. Here one DJ *leads*: the other
side's app reads the leader's tempo and beat from every pong of the
connection test (``probe``), moves that beat onto its own clock with the
measured offset, and nudges its local Link session — which Serato or Traktor
then follow like any Link peer. Only one side leads at a time; "take the lead"
hands it over, as in a back-to-back.

Qt-free and side-effect free: ``LinkFollower.update`` returns what to change,
the probe session applies it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from djmidi.remote_mix.probe import QUANTUM, LinkSnapshot, local_beat_at, phase_gap_ms

MIN_GAP_MS = 3.0  # below this, a correction would only chase the network's noise
MIN_INTERVAL_S = 2.0  # at most one phase jump every two seconds
TEMPO_EPSILON = 0.005
OFFSET_WINDOW = 30
BEATS_PER_BAR = 4
BARS_PER_PHRASE = 4


class LinkControl(Protocol):
    def set_tempo(self, tempo: float) -> None: ...

    def force_beat(self, beat: float) -> None: ...


@dataclass(frozen=True)
class RemoteBeat:
    """The leader's Link state, as one pong carried it."""

    tempo: float
    beat: float
    sent: float  # leader's clock when it read that beat
    rtt: float  # seconds
    offset: float  # leader's clock minus ours, seconds


@dataclass(frozen=True)
class Correction:
    tempo: float | None = None
    beat: float | None = None
    gap_ms: float = 0.0


class LinkFollower:
    """Turns the leader's beats into corrections of the local Link session.

    The clock offset comes from the fastest recent round trip (the one least
    bent by queueing), not from the latest, so jitter doesn't move the beat.
    """

    def __init__(
        self,
        *,
        min_gap_ms: float = MIN_GAP_MS,
        min_interval_s: float = MIN_INTERVAL_S,
        quantum: float = QUANTUM,
    ) -> None:
        self._min_gap_ms = min_gap_ms
        self._min_interval_s = min_interval_s
        self._quantum = quantum
        self._recent: deque[tuple[float, float]] = deque(maxlen=OFFSET_WINDOW)  # (rtt, offset)
        self._last_jump: float | None = None
        self.last_gap_ms: float | None = None
        self.corrections = 0

    def reset(self) -> None:
        self._recent.clear()
        self._last_jump = None
        self.last_gap_ms = None

    def offset(self) -> float | None:
        return min(self._recent)[1] if self._recent else None

    def update(self, remote: RemoteBeat, local: LinkSnapshot, now: float) -> Correction | None:
        self._recent.append((remote.rtt, remote.offset))
        offset = self.offset()
        assert offset is not None
        if remote.tempo <= 0:
            return None
        # The leader's beat now, on our clock.
        leader_beat = remote.beat + (now - (remote.sent - offset)) * remote.tempo / 60.0
        ours = local_beat_at(local, now)
        tempo = remote.tempo if abs(local.tempo - remote.tempo) > TEMPO_EPSILON else None
        gap = phase_gap_ms(ours, leader_beat, remote.tempo, self._quantum)
        self.last_gap_ms = gap
        beat = None
        recent_jump = self._last_jump is not None and now - self._last_jump < self._min_interval_s
        if abs(gap) >= self._min_gap_ms and not recent_jump:
            beat = ours - gap * remote.tempo / 60_000.0
            self._last_jump = now
        if tempo is None and beat is None:
            return None
        self.corrections += 1
        return Correction(tempo=tempo, beat=beat, gap_ms=gap)


def apply(correction: Correction, control: LinkControl) -> None:
    if correction.tempo is not None:
        control.set_tempo(correction.tempo)
    if correction.beat is not None:
        control.force_beat(correction.beat)


@dataclass(frozen=True)
class PhrasePosition:
    bar: int  # 1..BARS_PER_PHRASE
    beat: int  # 1..BEATS_PER_BAR
    beats_to_phrase: int  # whole beats until the next phrase starts (0 on its first beat)


def phrase_position(beat: float, beats_per_bar: int = BEATS_PER_BAR, bars: int = BARS_PER_PHRASE) -> PhrasePosition:
    """Where ``beat`` falls in a phrase of ``bars`` bars: both DJs see the same
    count once their Link sessions share one beat."""
    length = beats_per_bar * bars
    whole = int(beat // 1) % length
    return PhrasePosition(
        bar=whole // beats_per_bar + 1,
        beat=whole % beats_per_bar + 1,
        beats_to_phrase=(length - whole) % length,
    )
