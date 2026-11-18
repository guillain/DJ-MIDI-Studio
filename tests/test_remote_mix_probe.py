"""Remote mix phase 0: the connection test between two DJ MIDI Studio."""

import time
from datetime import datetime

import pytest

from djmidi.remote_mix import probe as p


def test_round_trip_and_offset_follow_ntp():
    # Remote clock 5 s ahead, 20 ms each way, 1 ms spent answering.
    rtt, offset = p.round_trip(10.0, 15.020, 15.021, 10.041)
    assert rtt == pytest.approx(0.040)
    assert offset == pytest.approx(5.0)


def test_phase_gap_wraps_into_half_a_bar():
    assert p.phase_gap_ms(8.0, 8.0, 120.0) == 0
    assert p.phase_gap_ms(8.01, 8.0, 120.0) == pytest.approx(5.0)
    assert p.phase_gap_ms(0.0, 3.99, 120.0) == pytest.approx(5.0)  # across the bar line
    assert p.phase_gap_ms(3.99, 0.0, 120.0) == pytest.approx(-5.0)


def test_decode_refuses_anything_but_our_protocol():
    assert p.decode(p.encode({"k": "ping"}))["k"] == "ping"
    assert p.decode(b'{"p": "other", "k": "ping"}') is None
    assert p.decode(b"\xff\xfe") is None
    assert p.decode(b"[1, 2]") is None
    assert p.decode(b"{" + b" " * 2000 + b"}") is None


def _samples(rtts, phases=None, tempo=124.0):
    phases = phases or [None] * len(rtts)
    return [
        p.Sample(t=i * 1.0, rtt_ms=r, offset_ms=100.0, phase_ms=ph, local_tempo=tempo, remote_tempo=tempo)
        for i, (r, ph) in enumerate(zip(rtts, phases))
    ]


def test_summary_and_lights():
    samples = _samples([40.0, 42.0, 40.0, 44.0] * 10, [1.0 + i * 0.01 for i in range(40)])
    stats = p.summarise(samples, sent=40)
    assert stats.loss_pct == 0
    assert stats.rtt_min == 40.0
    assert stats.jitter_ms == pytest.approx(116 / 39)
    assert stats.phase_drift_ms_per_min == pytest.approx(0.6)
    assert p.verdicts(stats) == {"network": p.GREEN, "stability": p.GREEN, "link": p.GREEN}


def test_lights_turn_red_on_loss_jitter_and_tempo_mismatch():
    samples = _samples([40.0, 120.0] * 10)
    stats = p.summarise(samples, sent=40)
    lights = p.verdicts(stats)
    assert lights["network"] == p.RED  # half the pings lost
    assert lights["stability"] == p.RED
    assert lights["link"] == p.UNKNOWN  # no phase measured
    mismatch = [p.Sample(0.0, 40.0, 0.0, 0.0, 124.0, 126.0)]
    assert p.verdicts(p.summarise(mismatch, 1))["link"] == p.RED
    assert p.verdicts(None)["network"] == p.UNKNOWN


def test_report_lists_the_measures():
    stats = p.summarise(_samples([40.0, 42.0] * 10, [2.0] * 20), sent=20)
    text = p.report_markdown(stats, role="host", peer="10.147.17.5", started=datetime(2026, 11, 21, 21, 0))  # noqa: DTZ001
    assert "2026-11-21 21:00:00" in text
    assert "| Jitter | 2.0 ms |" in text
    assert "124.00 BPM / 124.00 BPM" in text
    assert "Tempo and phase: green" in text
    assert "No answer" in p.report_markdown(None, role="join", peer="x", started=datetime(2026, 1, 1))  # noqa: DTZ001


def _wait_for(session, count, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(session.snapshot()[0]) >= count:
            return
        time.sleep(0.02)
    raise AssertionError("no pongs")


def test_two_sessions_measure_each_other_on_localhost():
    clock = time.monotonic
    host_link = lambda: p.LinkSnapshot(tempo=124.0, beat=clock() * 124 / 60, at=clock(), peers=1)
    guest_link = lambda: p.LinkSnapshot(tempo=124.0, beat=clock() * 124 / 60 + 0.5, at=clock())
    host = p.ProbeSession(port=0, link_reader=host_link, bind_host="127.0.0.1", interval=0.02)
    host.start()
    guest = p.ProbeSession(peer=("127.0.0.1", host.port), link_reader=guest_link, interval=0.02)
    guest.start()
    try:
        _wait_for(guest, 5)
        _wait_for(host, 5)  # the host pings back once it knows the guest
    finally:
        guest.stop()
        host.stop()
    stats = guest.stats()
    assert stats.rtt_median < 50
    assert abs(stats.phase_median_ms - 0.5 * 60_000 / 124) < 5  # the guest is half a beat ahead
    assert host.stats().remote_tempo == 124.0
    assert host.peer[0] == "127.0.0.1"


def test_the_host_answers_only_its_first_peer():
    host = p.ProbeSession(port=0, bind_host="127.0.0.1", interval=0.02)
    host.start()
    first = p.ProbeSession(peer=("127.0.0.1", host.port), interval=0.02)
    first.start()
    try:
        _wait_for(first, 2)
        second = p.ProbeSession(peer=("127.0.0.1", host.port), interval=0.02)
        second.start()
        time.sleep(0.2)
        second.stop()
    finally:
        first.stop()
        host.stop()
    assert second.snapshot()[0] == []
