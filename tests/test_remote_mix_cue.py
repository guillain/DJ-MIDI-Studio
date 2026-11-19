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
