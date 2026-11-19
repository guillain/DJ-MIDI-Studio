"""Cue a DJ in the headphones; the host mutes a DJ for everyone."""

import numpy as np
from test_remote_mix_dialog import FakeAudioLink, FakeBackend

from djmidi.remote_mix import audio, probe, table


def _panel(tmp_path, backend):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel

    return RemoteAudioPanel(
        lambda: ("127.0.0.1", 9, lambda: probe.LinkSnapshot(tempo=120.0, beat=8.0, at=0.0, peers=1)),
        backend=backend,
        link_factory=lambda **kw: FakeAudioLink(**kw),
        controls_path=tmp_path / "c.json",
    )


def test_cue_goes_to_the_headphones_before_the_fader_and_never_to_the_mix(tmp_path):
    backend = FakeBackend()
    panel = _panel(tmp_path, backend)
    try:
        panel.input_combo.setCurrentIndex(0)
        panel.phones_combo.setCurrentIndex(2)  # "Virtual Out" as headphones
        panel.program_combo.setCurrentIndex(0)
        assert panel.start()
        panel.faders["them"].setValue(0)  # closed fader...
        panel.cue_buttons["them"].setChecked(True)  # ...but cued
        tone = np.full((960, 2), 0.5, np.float32)
        player = panel.players.get(1)
        player.read = lambda n, beat: tone[:n]
        panel.pump()
        phones = backend.devices["Virtual Out"].written
        speakers = backend.devices["Speakers"].written
        assert phones and max(b.max() for b in phones) > 0.4  # heard in the headphones
        assert speakers and max(b.max() for b in speakers) == 0.0  # not in the room
    finally:
        panel.stop()
        panel.close()


def test_the_host_mutes_a_dj_and_guests_cannot(tmp_path):
    panel = _panel(tmp_path, FakeBackend())
    sent = []
    try:
        panel.attach_table(0, sent.append)
        panel.set_roster(0, {0: "Host", 1: "Alex"})
        assert panel.mute_buttons["them"].isEnabled()
        panel.mute_buttons["them"].setChecked(True)
        assert sent[-1]["c"]["dj1_mute"][0] == 1 and panel._gain("them") == 0.0
        guest = _panel(tmp_path, FakeBackend())
        try:
            guest.attach_table(1, lambda m: None)
            guest.set_roster(1, {0: "Host", 1: "Alex"})
            assert not guest.mute_buttons["them"].isEnabled()
            guest.apply_remote(sent[-1])  # the host muted me: my strip is muted here too
            assert guest.mute_buttons[guest._local("dj1_mute").rpartition("_")[0]].isChecked()
            assert table.HOST == 0 and audio.CHANNELS == 2
        finally:
            guest.close()
    finally:
        panel.close()


def test_the_console_gain_master_and_headphones_blend(tmp_path):
    from djmidi.gui.led_meter import LedMeter
    from djmidi.remote_mix import controls

    backend = FakeBackend()
    panel = _panel(tmp_path, backend)
    sent = []
    try:
        assert isinstance(panel.meters["them"], LedMeter)
        assert abs(panel._trim("them") - 1.0) < 1e-6
        panel.dials["them_gain"].setValue(100)
        assert abs(panel._trim("them") - 10 ** (12 / 20)) < 1e-6  # +12 dB at the right
        assert "them_gain" in controls.TARGETS and controls.MASTER in controls.TARGETS
        panel.attach_table(0, sent.append)
        panel.master_dial.setValue(40)
        assert sent[-1]["c"]["master"][0] == 40  # shared: the régie applies it
        panel.dials["them_gain"].setValue(50)
        panel.input_combo.setCurrentIndex(0)
        panel.phones_combo.setCurrentIndex(2)
        assert panel.start()
        tone = np.full((960, 2), 0.4, np.float32)
        panel.players.get(1).read = lambda n, beat: tone[:n]
        panel.faders["them"].setValue(100)
        panel.phones_mix.setValue(100)  # the room's sound, not the cue
        panel.pump()
        phones = backend.devices["Virtual Out"].written
        assert phones and max(b.max() for b in phones) > 0.3
        meter = LedMeter()
        meter.setValue(50)
        assert meter.lit() == round(50 * 15 / 100)
    finally:
        panel.stop()
        panel.close()
