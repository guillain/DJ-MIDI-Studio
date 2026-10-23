"""MIDI round-trip latency monitor (issue #255).

Sends a Note On to a chosen output port and times how long the matching
message takes to come back on a chosen input port, over N pings, then reports
min / median / max / mean and jitter.

**Only meaningful with something that echoes.** A plain controller does not
send back what it receives, so every ping simply times out. The result means
something with a loopback (macOS's IAC Driver bus opened as both output and
input, a virtual MIDI cable, a hardware MIDI-thru) or a device known to echo
the messages it receives. No controller's echo behaviour is assumed here.

Qt-free and fully driven by injected callables, so the timing logic is tested
with a fake port pair and a fake clock:

* ``send(channel, note, velocity, note_on)`` sends one Note On / Note Off,
* ``receive()`` returns the :class:`~djmidi.midi_io.MidiEvent` s that arrived
  since the last call (non-blocking, like ``MidiMonitor.poll``),
* ``clock()`` returns seconds from a monotonic clock (``time.perf_counter``).

:class:`LatencyProbe` is a step-wise state machine (one :meth:`~LatencyProbe.step`
per poll); :func:`run_probe` drives it in a tight loop with an injectable
``sleep`` -- the GUI runs that loop on a worker thread, since a Qt timer's
millisecond-plus granularity would be added to every measurement.

Matching: a reply is a ``Note On`` with a non-zero velocity on the ping's
channel and note. Each ping uses its own velocity (1..127, cycling) and, by
default, the reply must carry it too -- so a late echo of a ping that already
timed out is never mistaken for the next ping's reply. Turn
``match_velocity`` off for a device that echoes a different velocity. After
every ping a Note Off is sent, so an echoing LED is not left lit; its echo is
never counted (a Note Off, or a Note On with velocity 0).
"""

from __future__ import annotations

import itertools
import logging
import statistics
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.midi_io import MidiEvent, mido_message_to_event

_LOGGER = logging.getLogger(__name__)

SendFn = Callable[[int, int, int, bool], None]
ReceiveFn = Callable[[], Iterable[MidiEvent]]
ClockFn = Callable[[], float]

MAX_PINGS = 1000

ECHO_WARNING = QT_TRANSLATE_NOOP(
    "MidiLatencyDialog",
    "Only meaningful with a port or device that echoes what it receives "
    "(IAC Driver / virtual loopback, MIDI thru, or a controller known to echo "
    "its LED messages). A controller that does not echo makes every ping time out.",
)
# The statistics line (issue #319): English templates, translated by the caller.
_NO_REPLY = QT_TRANSLATE_NOOP(
    "MidiLatencyDialog", "No reply to {sent} ping(s) -- the port or device does not seem to echo."
)
_STATS = QT_TRANSLATE_NOOP(
    "MidiLatencyDialog",
    "{received}/{sent} replies ({lost}% lost): min {min}, median {median}, max {max}, jitter {jitter}",
)
_MILLISECONDS = QT_TRANSLATE_NOOP("MidiLatencyDialog", "{value} ms")
_NOT_AVAILABLE = QT_TRANSLATE_NOOP("MidiLatencyDialog", "n/a")


@dataclass(frozen=True)
class LatencyConfig:
    """What to send and how long to wait. Channel is 1-based like the rest
    of the app; ``interval_ms`` is the time between two ping *starts*."""

    count: int = 20
    channel: int = 1
    note: int = 60
    interval_ms: float = 100.0
    timeout_ms: float = 500.0
    match_velocity: bool = True

    def validated(self) -> LatencyConfig:
        if not 1 <= self.count <= MAX_PINGS:
            raise ValueError(f"count must be in [1, {MAX_PINGS}], got {self.count}")
        if not 1 <= self.channel <= 16:
            raise ValueError(f"channel must be in [1, 16], got {self.channel}")
        if not 0 <= self.note <= 127:
            raise ValueError(f"note must be in [0, 127], got {self.note}")
        if self.interval_ms < 0:
            raise ValueError(f"interval must be >= 0 ms, got {self.interval_ms}")
        if self.timeout_ms <= 0:
            raise ValueError(f"timeout must be > 0 ms, got {self.timeout_ms}")
        return self


@dataclass(frozen=True)
class PingResult:
    """One ping: its round-trip time in ms, or ``None`` when it timed out."""

    index: int
    velocity: int
    rtt_ms: float | None

    @property
    def lost(self) -> bool:
        return self.rtt_ms is None


@dataclass(frozen=True)
class LatencyStats:
    """Summary over every ping sent. The time fields are ``None`` when no
    reply came back at all. ``jitter_ms`` is the mean absolute difference
    between consecutive round-trip times (the usual network definition,
    RFC 3550-style without smoothing), ``None`` with fewer than two replies."""

    sent: int
    received: int
    min_ms: float | None = None
    median_ms: float | None = None
    max_ms: float | None = None
    mean_ms: float | None = None
    jitter_ms: float | None = None

    @property
    def lost(self) -> int:
        return self.sent - self.received

    @property
    def loss_percent(self) -> float:
        return 100.0 * self.lost / self.sent if self.sent else 0.0


def ping_velocity(index: int) -> int:
    """The velocity of ping ``index`` (0-based): 1..127, cycling, never 0
    (a Note On with velocity 0 is a Note Off)."""
    return index % 127 + 1


def compute_stats(results: Iterable[PingResult]) -> LatencyStats:
    results = list(results)
    rtts = [r.rtt_ms for r in results if r.rtt_ms is not None]
    if not rtts:
        return LatencyStats(sent=len(results), received=0)
    jitter = (
        statistics.fmean(abs(b - a) for a, b in itertools.pairwise(rtts)) if len(rtts) > 1 else None
    )
    return LatencyStats(
        sent=len(results),
        received=len(rtts),
        min_ms=min(rtts),
        median_ms=statistics.median(rtts),
        max_ms=max(rtts),
        mean_ms=statistics.fmean(rtts),
        jitter_ms=jitter,
    )


def format_stats(stats: LatencyStats, translate: Translate = untranslated) -> str:
    """A one-line human summary, e.g. for the status bar or a log.

    ``translate`` turns each English template into the interface language
    before it is filled in (issue #319); the default keeps English."""
    if stats.received == 0:
        return translate(_NO_REPLY).format(sent=stats.sent)

    def ms(value: float | None) -> str:
        return translate(_NOT_AVAILABLE) if value is None else translate(_MILLISECONDS).format(value=f"{value:.2f}")

    return translate(_STATS).format(
        received=stats.received,
        sent=stats.sent,
        lost=f"{stats.loss_percent:.0f}",
        min=ms(stats.min_ms),
        median=ms(stats.median_ms),
        max=ms(stats.max_ms),
        jitter=ms(stats.jitter_ms),
    )


class LatencyProbe:
    """Ping state machine. Call :meth:`step` repeatedly (as often as possible
    for accuracy) until it returns ``False``; :attr:`results` grows by one
    :class:`PingResult` per finished ping."""

    def __init__(
        self,
        send: SendFn,
        receive: ReceiveFn,
        config: LatencyConfig | None = None,
        *,
        clock: ClockFn = time.perf_counter,
    ) -> None:
        self._send = send
        self._receive = receive
        self.config = (config or LatencyConfig()).validated()
        self._clock = clock
        self.results: list[PingResult] = []
        self._sent_at: float | None = None
        self._next_send_at: float | None = None
        self._cancelled = False

    @property
    def finished(self) -> bool:
        return self._cancelled or (
            self._sent_at is None and len(self.results) >= self.config.count
        )

    def cancel(self) -> None:
        """Stop after the current state; an outstanding ping is released
        (Note Off) but not recorded."""
        if self._sent_at is not None:
            self._release(ping_velocity(len(self.results)))
            self._sent_at = None
        self._cancelled = True

    def stats(self) -> LatencyStats:
        return compute_stats(self.results)

    def _is_reply(self, event: MidiEvent, velocity: int) -> bool:
        if event.direction != "in" or event.event_type != "Note On":
            return False
        try:
            channel, note, value = int(event.channel), int(event.data1), int(event.data2)
        except ValueError:
            return False
        if channel != self.config.channel or note != self.config.note or value == 0:
            return False
        return value == velocity if self.config.match_velocity else True

    def _release(self, velocity: int) -> None:
        try:
            self._send(self.config.channel, self.config.note, 0, False)
        except Exception:
            _LOGGER.warning("Latency probe: Note Off for velocity %d failed", velocity, exc_info=True)

    def _finish_ping(self, rtt_ms: float | None, now: float) -> None:
        index = len(self.results)
        velocity = ping_velocity(index)
        self.results.append(PingResult(index, velocity, rtt_ms))
        self._release(velocity)
        assert self._sent_at is not None
        self._next_send_at = max(now, self._sent_at + self.config.interval_ms / 1000.0)
        self._sent_at = None

    def step(self) -> bool:
        if self.finished:
            return False
        events = list(self._receive())
        now = self._clock()
        if self._sent_at is not None:
            velocity = ping_velocity(len(self.results))
            if any(self._is_reply(event, velocity) for event in events):
                self._finish_ping((now - self._sent_at) * 1000.0, now)
            elif (now - self._sent_at) * 1000.0 >= self.config.timeout_ms:
                self._finish_ping(None, now)
            else:
                return True
        if len(self.results) >= self.config.count:
            return False
        if self._next_send_at is None or now >= self._next_send_at:
            velocity = ping_velocity(len(self.results))
            self._sent_at = self._clock()
            self._send(self.config.channel, self.config.note, velocity, True)
        return True


def run_probe(
    probe: LatencyProbe,
    *,
    sleep: Callable[[float], None] = time.sleep,
    poll_interval_s: float = 0.0002,
    should_stop: Callable[[], bool] | None = None,
    on_result: Callable[[PingResult], None] | None = None,
) -> LatencyStats:
    """Drives ``probe`` to completion (blocking) and returns its stats.

    ``should_stop`` is checked between steps (the GUI's Stop button);
    ``on_result`` is called once per finished ping, from this loop's thread."""
    reported = 0
    while True:
        if should_stop is not None and should_stop():
            probe.cancel()
        running = probe.step()
        if on_result is not None:
            while reported < len(probe.results):
                on_result(probe.results[reported])
                reported += 1
        if not running:
            break
        sleep(poll_interval_s)
    return probe.stats()


@contextmanager
def open_port_pair(output_name: str, input_name: str) -> Iterator[tuple[SendFn, ReceiveFn]]:
    """Opens the real mido ports and yields ``(send, receive)`` for
    :class:`LatencyProbe`. Anything already waiting on the input is drained
    first, so a stale message can't answer the first ping."""
    import mido

    inport = mido.open_input(input_name)
    try:
        outport = mido.open_output(output_name)
    except Exception:
        inport.close()
        raise
    try:
        for _ in inport.iter_pending():
            pass

        def send(channel: int, note: int, velocity: int, note_on: bool) -> None:
            kind = "note_on" if note_on else "note_off"
            outport.send(mido.Message(kind, channel=channel - 1, note=note, velocity=velocity))

        def receive() -> list[MidiEvent]:
            events = []
            for msg in inport.iter_pending():
                event = mido_message_to_event(msg, "in", port=input_name)
                if event is not None:
                    events.append(event)
            return events

        yield send, receive
    finally:
        outport.close()
        inport.close()


__all__ = [
    "ECHO_WARNING",
    "LatencyConfig",
    "LatencyProbe",
    "LatencyStats",
    "PingResult",
    "compute_stats",
    "format_stats",
    "open_port_pair",
    "ping_velocity",
    "run_probe",
]
