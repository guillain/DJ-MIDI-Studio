"""Try Mix Together alone: a pretend second DJ on this computer."""

from datetime import datetime

import numpy as np
from test_remote_mix_dialog import FakeBackend

from djmidi.gui.remote_mix_dialog import RemoteMixDialog
from djmidi.remote_mix import audio, demo, signals


def test_the_demo_dj_answers_signals_and_echoes_sound_and_voice():
    now = [100.0]
    session = demo.DemoSession(port=47800, name="Me", clock=lambda: now[0])
    session.start()
    assert session.stats() is not None  # connected at once
    assert session.roster == {0: "Me", demo.DEMO_DJ: demo.DEMO_NAME}
    for _ in range(signals.REPEATS):
        session.send(signals.SignalBoard(0).send("next"))
    session.stats()
    assert session.inbox.empty()
    now[0] += demo.REPLY_AFTER_S
    session.stats()
    reply = session.inbox.get_nowait()
    assert reply["s"] == "love" and reply["from"] == demo.DEMO_DJ and session.inbox.empty()

    players = audio.PlayerBank()
    link = session.audio_link(players=players)
    packet = audio.AudioPacket(0, 4.0, 120.0, np.full((240, 2), 0.5, np.float32))
    link.send([packet])
    assert players.get(demo.DEMO_DJ).received == 1
    heard = []
    link.talk_sink = lambda dj, p: heard.append(dj)
    link.send_talk([packet])
    assert heard == [demo.DEMO_DJ]
    clock = demo.DemoClock(clock=lambda: now[0])
    first = clock().beat
    now[0] += 0.5
    assert clock().beat - first == 1.0 and clock().tempo == demo.DEMO_TEMPO


def test_try_alone_walks_the_whole_tab_without_a_partner(tmp_path):
    dialog = RemoteMixDialog(
        link_factory=lambda: None, addresses=list, report_dir=lambda: tmp_path,
        now=lambda: datetime(2026, 11, 21, 21, 0),  # noqa: DTZ001
        audio_backend=FakeBackend(), controls_path=tmp_path / "c.json", history_dirs=dict,
        exports_dir=tmp_path, settings_path=tmp_path / "s.json",
    )
    try:
        dialog.join_radio.setChecked(True)
        dialog.demo_button.click()
        assert dialog.running and dialog.demo and dialog.host_radio.isChecked()
        assert not dialog.demo_button.isEnabled()
        assert dialog.status_label.text().startswith("Demo:")
        assert dialog.next_step.key == "sound"  # connected, a steady tempo: next, the sound
        assert dialog.sound_panel.names["them"].text() == demo.DEMO_NAME
        assert dialog.signals_panel.board is not None and dialog.tracklist_panel.list is not None
        sound = dialog.sound_panel
        sound.talk.mic_combo.setCurrentIndex(1)
        assert sound.start()
        assert isinstance(sound.link, demo.DemoAudioLink) and sound.link.talk_sink is not None
        dialog.refresh()
        assert dialog.next_step.key == "mixing"
        dialog.start_button.click()  # stop
        assert not dialog.running and dialog.demo_button.isEnabled()
    finally:
        dialog.close()
