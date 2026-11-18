"""Remote mix phase 8: a listener hears the control room's official mix."""

import time

import numpy as np
import pytest

from djmidi.remote_mix import audio, listen, opus

pytestmark = pytest.mark.skipif(opus.unavailable() is not None, reason="PyAV not installed")


def _tone(n):
    t = np.arange(n) / audio.RATE
    mono = 0.4 * np.sin(2 * np.pi * 440 * t)
    return np.stack([mono, mono], axis=1).astype(np.float32)


def test_a_listener_says_hello_and_receives_the_mix_over_localhost():
    server = listen.ListenerServer(port=0, bind_host="127.0.0.1")
    player = listen.StreamPlayer(buffer_ms=20)
    client = listen.ListenerClient(server=("127.0.0.1", server.port), player=player, bind_host="127.0.0.1")
    try:
        deadline = time.monotonic() + 3
        while not server.listeners() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(server.listeners()) == 1
        for start in range(0, 4800, 1000):  # odd block sizes: whole packets only go out
            server.send_mix(_tone(4800)[start : start + 1000])
        while player.received < 18 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        client.close()
        server.close()
    assert player.received >= 18
    heard = player.read(960)
    assert heard.max() > 0.2


def test_the_player_waits_for_its_buffer_then_plays_evenly_and_fills_gaps_with_silence():
    player = listen.StreamPlayer(buffer_ms=10)  # 480 samples
    assert not player.read(240).any()  # nothing yet
    for position in range(0, 2400, 240):
        if position != 1200:  # one packet lost
            player.push(audio.AudioPacket(position, 0.0, 120.0, np.full((240, 2), 0.5, np.float32)))
    first = player.read(240)  # starts 10 ms behind the newest sample: 1920
    assert first.min() == pytest.approx(0.5, abs=1e-6)
    assert player.buffered_ms() == 5
    player.read(240)
    assert player.gap_ratio() == 0.0
    fresh = listen.StreamPlayer(buffer_ms=10)
    for position in range(0, 2400, 240):
        if position != 1200:
            fresh.push(audio.AudioPacket(position, 0.0, 120.0, np.full((240, 2), 0.5, np.float32)))
    fresh._cursor = 1200
    assert not fresh.read(240).any() and fresh.gap_ratio() == 1.0


def test_old_listeners_are_forgotten():
    now = [0.0]
    server = listen.ListenerServer(port=0, bind_host="127.0.0.1", clock=lambda: now[0])
    try:
        server._listeners[("127.0.0.1", 9)] = 0.0
        assert server.listeners() == [("127.0.0.1", 9)]
        now[0] = listen.LISTENER_TIMEOUT_S + 1
        assert server.listeners() == []
    finally:
        server.close()
