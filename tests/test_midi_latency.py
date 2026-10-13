import pytest

from djmidi.midi_io import MidiEvent
from djmidi.midi_latency import (
    LatencyConfig,
    LatencyProbe,
    PingResult,
    compute_stats,
    format_stats,
    ping_velocity,
    run_probe,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeLoopback:
    """A fake output/input port pair: every message sent comes back on the
    input after the next delay from `delays_ms` (None = swallowed)."""

    def __init__(self, clock: FakeClock, delays_ms, *, echo_velocity=None) -> None:
        self.clock = clock
        self.delays = list(delays_ms)
        self.echo_velocity = echo_velocity
        self.sent: list[tuple[int, int, int, bool]] = []
        self._queue: list[tuple[float, MidiEvent]] = []

    def send(self, channel, note, velocity, note_on) -> None:
        self.sent.append((channel, note, velocity, note_on))
        if not note_on:
            # The Note Off echoes immediately too; it must never be counted.
            self._queue.append((self.clock.now, _event("Note Off", channel, note, 0)))
            return
        delay = self.delays.pop(0) if self.delays else None
        if delay is None:
            return
        value = self.echo_velocity if self.echo_velocity is not None else velocity
        self._queue.append((self.clock.now + delay / 1000.0, _event("Note On", channel, note, value)))

    def push(self, at_ms: float, event: MidiEvent) -> None:
        self._queue.append((at_ms / 1000.0, event))

    def receive(self):
        ready = [e for t, e in self._queue if t <= self.clock.now + 1e-12]
        self._queue = [(t, e) for t, e in self._queue if t > self.clock.now + 1e-12]
        return ready


def _event(kind, channel, note, value, direction="in"):
    return MidiEvent(direction, str(channel), kind, str(note), str(value), 0.0)


def _run(delays_ms, config=None, **kwargs):
    clock = FakeClock()
    port = FakeLoopback(clock, delays_ms, **{k: v for k, v in kwargs.items() if k == "echo_velocity"})
    probe = LatencyProbe(port.send, port.receive, config or LatencyConfig(count=len(delays_ms)), clock=clock)
    stats = run_probe(probe, sleep=clock.sleep, poll_interval_s=0.0001)
    return probe, port, stats


def test_measures_round_trip_of_each_ping():
    probe, port, stats = _run([2.0, 4.0, 3.0, 5.0])
    assert [round(r.rtt_ms, 1) for r in probe.results] == [2.0, 4.0, 3.0, 5.0]
    assert stats.sent == stats.received == 4
    assert stats.min_ms == pytest.approx(2.0, abs=0.15)
    assert stats.max_ms == pytest.approx(5.0, abs=0.15)
    assert stats.median_ms == pytest.approx(3.5, abs=0.15)
    assert stats.mean_ms == pytest.approx(3.5, abs=0.15)
    # |4-2| + |3-4| + |5-3| = 5 over 3 differences
    assert stats.jitter_ms == pytest.approx(5 / 3, abs=0.1)
    note_ons = [s for s in port.sent if s[3]]
    note_offs = [s for s in port.sent if not s[3]]
    assert [s[2] for s in note_ons] == [1, 2, 3, 4]
    assert len(note_offs) == 4 and all(s[2] == 0 for s in note_offs)


def test_lost_ping_times_out_and_the_run_continues():
    config = LatencyConfig(count=3, timeout_ms=50, interval_ms=10)
    probe, _port, stats = _run([1.0, None, 1.0], config)
    assert [r.lost for r in probe.results] == [False, True, False]
    assert stats.received == 2 and stats.lost == 1
    assert stats.loss_percent == pytest.approx(100 / 3)


def test_no_echo_reports_every_ping_lost():
    config = LatencyConfig(count=3, timeout_ms=20)
    _probe, _port, stats = _run([None, None, None], config)
    assert stats.received == 0 and stats.min_ms is None and stats.jitter_ms is None
    assert "does not seem to echo" in format_stats(stats)


def test_late_echo_of_timed_out_ping_is_not_counted_for_the_next():
    # Ping 0's echo arrives after its 20 ms timeout, while ping 1 is waiting.
    config = LatencyConfig(count=2, timeout_ms=20, interval_ms=0)
    _probe, _port, stats = _run([30.0, 40.0], config)
    # Ping 1 (sent at ~20 ms) must wait for its own echo: 40 ms > timeout -> lost too.
    assert stats.received == 0


def test_match_velocity_off_accepts_any_non_zero_velocity():
    config = LatencyConfig(count=2, match_velocity=False)
    _probe, _port, stats = _run([1.0, 1.0], config, echo_velocity=127)
    assert stats.received == 2
    config = LatencyConfig(count=2, timeout_ms=10)
    _probe, _port, stats = _run([1.0, 1.0], config, echo_velocity=127)
    assert stats.received == 0


def test_ignores_other_notes_channels_and_output_direction():
    clock = FakeClock()
    port = FakeLoopback(clock, [None])
    port.push(0.5, _event("Note On", 2, 60, 1))
    port.push(0.6, _event("Note On", 1, 61, 1))
    port.push(0.7, _event("Note On", 1, 60, 1, direction="out"))
    port.push(0.8, _event("Control Change", 1, 60, 1))
    port.push(3.0, _event("Note On", 1, 60, 1))
    probe = LatencyProbe(port.send, port.receive, LatencyConfig(count=1), clock=clock)
    stats = run_probe(probe, sleep=clock.sleep, poll_interval_s=0.0001)
    assert stats.received == 1
    assert probe.results[0].rtt_ms == pytest.approx(3.0, abs=0.15)


def test_respects_interval_between_ping_starts():
    clock = FakeClock()
    port = FakeLoopback(clock, [1.0, 1.0, 1.0])
    starts = []
    original = port.send

    def send(channel, note, velocity, note_on):
        if note_on:
            starts.append(clock.now)
        original(channel, note, velocity, note_on)

    probe = LatencyProbe(send, port.receive, LatencyConfig(count=3, interval_ms=100), clock=clock)
    run_probe(probe, sleep=clock.sleep, poll_interval_s=0.001)
    assert starts[1] - starts[0] == pytest.approx(0.1, abs=0.002)
    assert starts[2] - starts[1] == pytest.approx(0.1, abs=0.002)


def test_should_stop_cancels_and_releases_the_outstanding_ping():
    clock = FakeClock()
    port = FakeLoopback(clock, [None] * 5)
    probe = LatencyProbe(port.send, port.receive, LatencyConfig(count=5, timeout_ms=1000), clock=clock)
    stats = run_probe(probe, sleep=clock.sleep, should_stop=lambda: clock.now > 0.01)
    assert probe.finished and stats.sent == 0
    assert port.sent[-1][3] is False  # Note Off sent for the cancelled ping


def test_on_result_called_once_per_ping():
    clock = FakeClock()
    port = FakeLoopback(clock, [1.0, 2.0])
    seen: list[PingResult] = []
    probe = LatencyProbe(port.send, port.receive, LatencyConfig(count=2), clock=clock)
    run_probe(probe, sleep=clock.sleep, on_result=seen.append)
    assert [r.index for r in seen] == [0, 1]


def test_ping_velocity_cycles_and_is_never_zero():
    assert ping_velocity(0) == 1
    assert ping_velocity(126) == 127
    assert ping_velocity(127) == 1


@pytest.mark.parametrize(
    "kwargs",
    [{"count": 0}, {"channel": 17}, {"note": 128}, {"timeout_ms": 0}, {"interval_ms": -1}],
)
def test_config_validation(kwargs):
    with pytest.raises(ValueError):
        LatencyConfig(**kwargs).validated()


def test_compute_stats_single_reply_has_no_jitter():
    stats = compute_stats([PingResult(0, 1, 2.5), PingResult(1, 2, None)])
    assert stats.received == 1 and stats.jitter_ms is None and stats.median_ms == 2.5
    assert "1/2 replies" in format_stats(stats)
