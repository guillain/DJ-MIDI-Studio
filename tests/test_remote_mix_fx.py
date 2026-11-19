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


def test_midi_mode_click_a_knob_then_move_the_controller(tmp_path):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from test_remote_mix_dialog import FakeBackend

    from djmidi.gui.remote_mix_audio import RemoteAudioPanel
    from djmidi.midi_io import MidiEvent
    from djmidi.remote_mix import controls

    panel = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=tmp_path / "c.json", ensure_listening=lambda: True)
    panel.show()
    try:
        before = panel.reverb_dial.value()
        QTest.mouseClick(panel.reverb_dial, Qt.MouseButton.LeftButton, pos=QPoint(40, 20))
        assert panel.learning is None  # not in MIDI mode: an ordinary click
        panel.reverb_dial.setValue(before)
        panel.midi_button.setChecked(True)
        QTest.mouseClick(panel.reverb_dial, Qt.MouseButton.LeftButton, pos=QPoint(40, 20))
        assert panel.learning == controls.FX_REVERB and panel.reverb_dial.value() == before
        assert "Reverb" in panel.controls_hint.text()
        assert panel.feed_midi_event(MidiEvent("in", "1", "Control Change", "21", "127", 0.0, "XP2"))
        assert controls.FX_REVERB in panel.controls.bindings and panel.reverb_dial.value() == 100
        assert panel.midi_button.isChecked()  # stays on for the next control
        panel.midi_button.setChecked(False)
        assert panel.learning is None
    finally:
        panel.close()
