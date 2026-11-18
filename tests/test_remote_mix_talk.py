"""Talkback between DJs (remote mix, phase 14)."""

import time

import numpy as np
from test_remote_mix_dialog import FakeBackend

from djmidi.midi_io import MidiEvent
from djmidi.remote_mix import audio, probe, talkback
from djmidi.remote_mix.signals import PadTrigger


def _voice(level=0.3, n=480):
    return np.full((n, 2), level, np.float32)


def test_a_voice_travels_flagged_and_never_reaches_the_music_players():
    player_b = audio.BarAlignedPlayer() if hasattr(audio, "BarAlignedPlayer") else None
    link_b = audio.AudioLink(port=0, peer=("127.0.0.1", 9), player=player_b, bind_host="127.0.0.1")
    link_a = audio.AudioLink(port=0, peer=("127.0.0.1", link_b.port), player=None, bind_host="127.0.0.1")
    heard = []
    link_b.talk_sink = lambda dj, packet: heard.append((dj, packet))
    try:
        packets = audio.SendBuffer().add(_voice(), 0, 0.0, 120.0, audio.CODEC_PCM24)
        link_a.send_talk(packets)
        deadline = time.monotonic() + 3
        while len(heard) < len(packets) and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        link_a.close()
        link_b.close()
    assert len(heard) == len(packets) and heard[0][0] == 0
    if player_b is not None:
        assert player_b.received == 0  # a voice is not music


def test_voices_play_at_once_and_say_who_talks():
    now = [10.0]
    receiver = talkback.TalkReceiver(clock=lambda: now[0])
    for i in range(20):
        receiver.push(2, audio.AudioPacket(i * 240, 0.0, 120.0, _voice(n=240)))
    assert receiver.talking() == [2]
    out = receiver.read(960)
    assert out.max() > 0.2
    now[0] += 1.0
    assert receiver.talking() == []


def test_the_talk_pad_is_held():
    pad = PadTrigger("7", "9")

    def ev(kind, velocity="127", note="9"):
        return MidiEvent("in", "7", kind, note, velocity, 0.0, "DDJ-XP2")

    assert talkback.pad_event(ev("Note On"), pad) == talkback.PRESS
    assert talkback.pad_event(ev("Note On", "0"), pad) == talkback.RELEASE
    assert talkback.pad_event(ev("Note Off", "64"), pad) == talkback.RELEASE
    assert talkback.pad_event(ev("Note On", note="10"), pad) is None
    assert talkback.pad_event(ev("Note On"), None) is None


class _TalkLink:
    def __init__(self, **kwargs):
        self.port, self.error, self.closed = kwargs["port"], None, False
        self.packets, self.talk, self.talk_sink = [], [], None

    def send(self, packets):
        self.packets += packets

    def send_talk(self, packets):
        self.talk += packets

    def close(self):
        self.closed = True


def test_hold_to_talk_from_the_panel_and_hear_them_in_the_headphones(tmp_path):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel

    links = []
    backend = FakeBackend()
    panel = RemoteAudioPanel(
        lambda: ("127.0.0.1", 9, lambda: probe.LinkSnapshot(tempo=120.0, beat=8.0, at=0.0, peers=1)),
        backend=backend,
        link_factory=lambda **kw: links.append(_TalkLink(**kw)) or links[-1],
        controls_path=tmp_path / "c.json",
    )
    try:
        panel.input_combo.setCurrentIndex(0)  # no music sent: the only input is the microphone
        panel.talk.mic_combo.setCurrentIndex(1)
        assert panel.start()
        link = links[0]
        assert link.talk_sink is not None and panel.talk.talk_button.isEnabled()
        mic = backend.devices["Master In"]
        mic.blocks.append(_voice(n=960))
        panel.pump()
        assert link.talk == []  # not holding: nothing sent
        panel.talk.talk_button.pressed.emit()
        mic.blocks.append(_voice(n=960))
        panel.pump()
        assert len(link.talk) == 4 and not link.packets
        panel.talk.talk_button.released.emit()
        assert not panel.talk.talking

        for i in range(40):  # Alex talks back
            link.talk_sink(1, audio.AudioPacket(i * 240, 0.0, 120.0, _voice(0.4, 240)))
        backend.devices["Speakers"].written.clear()
        panel.pump()
        assert max(block.max() for block in backend.devices["Speakers"].written) > 0.3
        panel.talk._show_status()
        assert "talking" in panel.talk.status_label.text()

        panel.talk.learn()
        assert panel.feed_midi_event(MidiEvent("in", "7", "Note On", "9", "127", 0.0, "XP2"))
        assert panel.talk.pad == PadTrigger("7", "9")
        assert talkback.load_pad(tmp_path / talkback.FILE_NAME) == PadTrigger("7", "9")
        assert panel.feed_midi_event(MidiEvent("in", "7", "Note On", "9", "127", 0.0, "XP2"))
        assert panel.talk.talking
        assert panel.feed_midi_event(MidiEvent("in", "7", "Note Off", "9", "0", 0.0, "XP2"))
        assert not panel.talk.talking
    finally:
        panel.stop()
        panel.close()
