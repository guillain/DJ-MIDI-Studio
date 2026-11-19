"""The console's beat-synced effects on the official mix."""

import numpy as np

from djmidi.remote_mix import fx, table


def _blocks(x, size=960):
    return [x[i : i + size] for i in range(0, len(x), size)]


def test_the_delay_echoes_on_the_beat_at_the_session_tempo():
    delay = fx.BeatDelay()
    click = np.zeros((48_000, 2), np.float32)
    click[0] = 1.0
    out = np.concatenate([delay.process(b, 0.5, 1.0, 120.0) for b in _blocks(click)])
    echoes = np.nonzero(np.abs(out[:, 0]) > 0.1)[0]
    assert list(echoes) == [0, 24_000]  # one beat at 120 BPM = 0.5 s
    assert abs(out[24_000, 0] - 0.5) < 1e-6
    assert fx.BeatDelay.frames(0.5, 128.0) == round(0.5 * 60 / 128 * 48_000)


def test_knobs_down_leave_the_mix_untouched_and_the_reverb_rings():
    mix = np.random.default_rng(1).random((960, 2), dtype=np.float32) * 0.2
    master = fx.MasterFx()
    assert np.array_equal(master.process(mix, delay=0.0, beats=1.0, reverb=0.0, tempo=120.0), mix)
    reverb = fx.Reverb()
    reverb.process(mix, 0.5)
    tail = reverb.process(np.zeros((960 * 3, 2), np.float32), 0.5)
    assert np.abs(tail[-960:]).max() > 0.0  # the room keeps ringing


def test_the_effects_are_shared_console_controls():
    host, guest = table.SharedTable(0), table.SharedTable(1)
    for name in ("fx_delay", "fx_reverb", table.FX_BEATS, table.MASTER):
        assert guest.receive(host.local_change(name, 2)) == [(name, 2)]
