"""Tools → Mix Together: Connection Test… (remote mix, phase 0)."""

from datetime import datetime

from djmidi.gui.main_window import MainWindow
from djmidi.gui.remote_mix_dialog import RemoteMixDialog
from djmidi.remote_mix import probe


class FakeSession:
    def __init__(self, *, port, peer, link_reader, link_control=None, follow=False):
        self.port, self.peer, self.link_reader = port, peer, link_reader
        self.link_control, self.follow = link_control, follow
        self.leading = peer is None
        self.remote_leading = None
        self.follow_error = None
        self.error = None
        self.samples = []
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def take_lead(self):
        self.leading, self.remote_leading = True, False

    def stats(self):
        return probe.summarise(self.samples, len(self.samples))


def _dialog(tmp_path, sessions, link_factory=lambda: None):
    def factory(**kwargs):
        sessions.append(FakeSession(**kwargs))
        return sessions[-1]

    return RemoteMixDialog(
        session_factory=factory,
        link_factory=link_factory,
        addresses=lambda: ["10.147.17.5"],
        report_dir=lambda: tmp_path,
        now=lambda: datetime(2026, 11, 21, 21, 0),  # noqa: DTZ001
    )


def test_hosting_waits_then_shows_the_lights_and_saves_a_report(tmp_path):
    sessions = []
    dialog = _dialog(tmp_path, sessions)
    try:
        assert "10.147.17.5" in dialog.addresses_label.text()
        dialog.start_button.click()
        session = sessions[0]
        assert session.started and session.peer is None and session.port == probe.DEFAULT_PORT
        assert "Waiting for the other DJ" in dialog.status_label.text()
        assert not dialog.save_button.isEnabled()

        session.peer = ("10.147.17.9", 50000)
        session.samples = [probe.Sample(t=float(i), rtt_ms=38.0, offset_ms=0.0) for i in range(5)]
        dialog.refresh()
        assert dialog.lights["network"][0].property("light") == probe.GREEN
        assert "round trip 38 ms" in dialog.lights["network"][1].text()
        assert "turn Link on" in dialog.lights["link"][1].text()
        assert dialog.save_button.isEnabled()

        dialog.start_button.click()  # stop
        assert session.stopped and not dialog.running
        path = dialog.save_report()
        assert path == tmp_path / "remote-mix-test-20261121-210000.md"
        assert "10.147.17.9" in path.read_text()
    finally:
        dialog.close()


def test_joining_needs_the_host_address(tmp_path):
    sessions = []
    dialog = _dialog(tmp_path, sessions)
    try:
        dialog.join_radio.setChecked(True)
        assert dialog.addresses_label.isHidden() or not dialog.isVisible()
        dialog.start_button.click()
        assert sessions == [] and "address first" in dialog.status_label.text()
        dialog.address_edit.setText(" 10.147.17.5 ")
        dialog.port_spin.setValue(47900)
        dialog.start_button.click()
        assert sessions[0].peer == ("10.147.17.5", 47900)
        assert "Calling 10.147.17.5" in dialog.status_label.text()
    finally:
        dialog.close()
    assert sessions[0].stopped  # closing the window ends the test


def test_joining_with_link_follows_the_host_then_takes_the_lead(tmp_path):
    controls = []

    def link():
        reader = lambda: probe.LinkSnapshot(tempo=124.0, beat=13.5, at=0.0)
        reader.control = object()
        controls.append(reader.control)
        return reader

    sessions = []
    dialog = _dialog(tmp_path, sessions, link)
    try:
        dialog.join_radio.setChecked(True)
        dialog.address_edit.setText("10.147.17.5")
        dialog.start_button.click()
        session = sessions[0]
        assert session.link_control is controls[0] and session.follow
        assert dialog.together_frame.isHidden()  # nothing to share before the first answer

        session.remote_leading = True
        session.samples = [probe.Sample(t=0.0, rtt_ms=40.0, offset_ms=0.0)]
        dialog.refresh()
        assert not dialog.together_frame.isHidden()
        assert "10.147.17.5 leads the tempo" in dialog.lead_label.text()
        assert "Bar 4 · beat 2 — next phrase in 3" == dialog.phrase_label.text()

        dialog.follow_checkbox.setChecked(False)
        assert session.follow is False and "not following" in dialog.lead_label.text()
        dialog.lead_button.click()
        assert session.leading and "You lead the tempo" in dialog.lead_label.text()
        assert not dialog.lead_button.isEnabled()
    finally:
        dialog.close()


def test_tools_menu_opens_the_connection_test(monkeypatch):
    window = MainWindow()
    try:
        tools_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Tools")
        assert window._remote_mix_action in tools_menu.actions()
        dialog = window._on_remote_mix_test()
        assert window._on_remote_mix_test() is dialog
        dialog.close()
    finally:
        window.close()


class FakeInput:
    def __init__(self):
        self.blocks = []
        self.closed = False

    def read(self):
        import numpy as np

        return self.blocks.pop(0) if self.blocks else np.zeros((0, 2), dtype=np.float32)

    def close(self):
        self.closed = True


class FakeOutput:
    def __init__(self):
        self.written = []
        self.closed = False

    def free_frames(self):
        return 960

    def queued_frames(self):
        return 0

    def write(self, samples):
        self.written.append(samples)

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self):
        self.devices = {}

    def inputs(self):
        return ["Master In"]

    def outputs(self):
        return ["Speakers", "Virtual Out"]

    def open_input(self, name):
        self.devices[name] = FakeInput()
        return self.devices[name]

    def open_output(self, name):
        self.devices[name] = FakeOutput()
        return self.devices[name]


class FakeAudioLink:
    def __init__(self, *, port, peer, player):
        self.port, self.peer, self.player = port, peer, player
        self.packets, self.error, self.closed = [], None, False

    def send(self, packets):
        self.packets += packets

    def close(self):
        self.closed = True


def test_the_sound_panel_sends_my_master_and_plays_theirs_one_bar_late(tmp_path):
    import numpy as np

    from djmidi.remote_mix import audio

    def link():
        reader = lambda: probe.LinkSnapshot(tempo=120.0, beat=8.0, at=0.0)
        reader.control = None
        return reader

    sessions, links = [], []
    backend = FakeBackend()

    def audio_link(**kwargs):
        links.append(FakeAudioLink(**kwargs))
        return links[-1]

    def factory(**kwargs):
        sessions.append(FakeSession(**kwargs))
        return sessions[-1]

    dialog = RemoteMixDialog(
        session_factory=factory, link_factory=link, addresses=list, report_dir=lambda: tmp_path,
        audio_backend=backend, audio_link_factory=audio_link,
    )
    try:
        panel = dialog.sound_panel
        assert not panel.start()  # not connected yet
        dialog.join_radio.setChecked(True)
        dialog.address_edit.setText("10.147.17.5")
        dialog.start_button.click()
        sessions[0].samples = [probe.Sample(t=0.0, rtt_ms=40.0, offset_ms=0.0)]
        dialog.refresh()
        assert not panel.isHidden()
        panel.input_combo.setCurrentIndex(1)
        panel.program_combo.setCurrentIndex(2)
        assert panel.start()
        assert links[0].peer == ("10.147.17.5", probe.DEFAULT_PORT + 1)

        tone = np.full((480, 2), 0.25, dtype=np.float32)
        backend.devices["Master In"].blocks.append(tone)
        # The other DJ's sound stamped one bar before our beat 8.0 arrives.
        panel.player.push(audio.AudioPacket(position=0, beat=4.0, tempo=120.0, samples=np.full((960, 2), 0.5, np.float32)))
        panel.pump()
        sent = links[0].packets
        assert len(sent) == 2 and sent[0].beat == 8.0 - 480 / audio.RATE * 2
        heard = backend.devices["Speakers"].written[0]
        assert heard.shape == (960, 2) and np.allclose(heard, 0.5)
        program = backend.devices["Virtual Out"].written[0]
        assert program.shape == (960, 2) and program[0, 0] > 0.25  # both DJs in the program mix
        assert panel.them_meter.value() == 50

        dialog.start_button.click()  # stopping the test stops the sound
        assert not panel.running and links[0].closed and backend.devices["Speakers"].closed
    finally:
        dialog.close()


def test_without_system_audio_the_panel_says_so(tmp_path):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel

    class Missing:
        unavailable = "libpulse.so.0: cannot open shared object file"

        def inputs(self):
            return []

        def outputs(self):
            return []

    panel = RemoteAudioPanel(lambda: None, backend=Missing())
    try:
        assert not panel.start_button.isEnabled()
        assert "No sound on this computer" in panel.status_label.text()
    finally:
        panel.close()


def test_learn_drives_the_mixer_from_a_controller_fader(tmp_path):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel
    from djmidi.midi_io import MidiEvent
    from djmidi.remote_mix import controls

    listening = []
    path = tmp_path / "controls.json"
    panel = RemoteAudioPanel(
        lambda: None, backend=FakeBackend(), ensure_listening=lambda: listening.append(1) or True, controls_path=path
    )
    try:
        assert panel.learn_buttons[controls.CROSSFADER].text() == "Learn"
        panel.learn_buttons[controls.CROSSFADER].click()
        assert listening and panel.learning == controls.CROSSFADER
        assert not panel.feed_midi_event(MidiEvent("in", "1", "Note On", "11", "127", 0.0))  # a pad isn't learned
        assert panel.feed_midi_event(MidiEvent("in", "7", "Control Change", "31", "0", 0.0))
        assert panel.learning is None and panel.crossfader.value() == 0
        assert panel.learn_buttons[controls.CROSSFADER].text() == "ch7 CC 31"
        assert panel.feed_midi_event(MidiEvent("in", "7", "Control Change", "31", "127", 0.0))
        assert panel.crossfader.value() == 100
        assert not panel.feed_midi_event(MidiEvent("in", "7", "Control Change", "32", "127", 0.0))
    finally:
        panel.close()

    again = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=path)
    try:
        assert again.controls.bindings[controls.CROSSFADER].control == "31"
        again.forget_buttons[controls.CROSSFADER].click()
        assert not again.forget_buttons[controls.CROSSFADER].isEnabled()
        assert controls.MixerControls.load(path).bindings == {}
    finally:
        again.close()


def test_learning_without_a_controller_says_so(tmp_path):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel
    from djmidi.remote_mix import controls

    panel = RemoteAudioPanel(
        lambda: None, backend=FakeBackend(), ensure_listening=lambda: False, controls_path=tmp_path / "c.json"
    )
    try:
        panel.learn_buttons[controls.ME].click()
        assert panel.learning is None
        assert "No controller is plugged in" in panel.controls_hint.text()
    finally:
        panel.close()


def test_live_midi_reaches_the_mix_together_mixer(monkeypatch):
    from djmidi.midi_io import MidiEvent
    from djmidi.remote_mix import controls

    window = MainWindow()
    try:
        dialog = window._on_remote_mix_test()
        panel = dialog.sound_panel
        panel.controls.bind(controls.THEM, controls.MixerTrigger("2", "Control Change", "19"))
        window._on_live_midi_event(MidiEvent("in", "2", "Control Change", "19", "0", 0.0))
        assert panel.them_volume.value() == 0
        dialog.close()
    finally:
        window.close()


def test_eq_knobs_shape_their_sound_and_follow_the_controller(tmp_path):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel
    from djmidi.midi_io import MidiEvent
    from djmidi.remote_mix import controls

    panel = RemoteAudioPanel(
        lambda: None, backend=FakeBackend(), ensure_listening=lambda: True, controls_path=tmp_path / "c.json"
    )
    try:
        panel.dials["them_low"].setValue(0)
        assert panel.them_strip.low == 0 and panel.me_strip.low == 50
        panel.learn_buttons["me_filter"].click()
        assert panel.feed_midi_event(MidiEvent("in", "1", "Control Change", "23", "127", 0.0))
        assert panel.dials["me_filter"].value() == 100 and panel.me_strip.filter == 100
        assert panel.controls.bindings["me_filter"] == controls.MixerTrigger("1", "Control Change", "23")
        panel.flat_buttons[controls.THEM].click()
        assert panel.them_strip.flat
    finally:
        panel.close()


def test_two_panels_share_one_mixer_and_a_controller_picks_up_softly(tmp_path):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel
    from djmidi.midi_io import MidiEvent
    from djmidi.remote_mix import controls, table

    host = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=tmp_path / "a.json")
    guest = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=tmp_path / "b.json")
    to_guest, to_host = [], []
    host.attach_table(table.HOST, to_guest.append)
    guest.attach_table(table.GUEST, to_host.append)
    guest.set_peer_name("Host DJ")
    try:
        host.dials["me_low"].setValue(5)
        host.crossfader.setValue(20)
        for message in to_guest:
            guest.apply_remote(message)
        assert guest.dials["them_low"].value() == 5
        assert guest.crossfader.value() == 80
        assert "Host DJ" in guest.remote_label.text()
        assert to_host == []  # applying their move doesn't echo it back

        # The guest's crossfader is on a controller, far from where the host left it.
        guest.controls.bind(controls.CROSSFADER, controls.MixerTrigger("1", "Control Change", "31"))
        assert guest.feed_midi_event(MidiEvent("in", "1", "Control Change", "31", "0", 0.0))
        assert guest.crossfader.value() == 80  # not picked up yet: no jump
        guest.feed_midi_event(MidiEvent("in", "1", "Control Change", "31", "127", 0.0))  # sweeps past 80
        assert guest.crossfader.value() == 100
        assert to_host and host.apply_remote(to_host[-1]) is None and host.crossfader.value() == 0
    finally:
        host.close()
        guest.close()


def test_mix_together_has_its_own_tab_after_music():
    window = MainWindow()
    try:
        index = window._tab_indexes["mix"]
        assert window._tab_indexes["library"] < index
        assert getattr(window, "_remote_mix_dialog", None) is None  # built on first visit only
        window.left_tabs.setCurrentIndex(index)
        dialog = window._remote_mix_dialog
        assert dialog is not None and window._on_remote_mix_test() is dialog
        assert window.left_tabs.currentIndex() == index
    finally:
        window.close()


def test_the_regie_makes_and_records_the_official_mix(tmp_path):
    from djmidi.gui.remote_mix_audio import RemoteAudioPanel
    from djmidi.remote_mix import table

    links = []
    panel = RemoteAudioPanel(
        lambda: ("127.0.0.1", 9, lambda: probe.LinkSnapshot(tempo=120.0, beat=8.0, at=0.0, peers=1)),
        backend=FakeBackend(),
        link_factory=lambda **kw: links.append(FakeAudioLink(**kw)) or links[-1],
        controls_path=tmp_path / "c.json",
        recordings_dir=tmp_path / "Exports",
    )
    to_host = []
    panel.attach_table(table.GUEST, to_host.append)
    try:
        assert not panel.makes_the_mix and "made at" in panel.regie_label.text()
        assert panel.start()
        assert not panel.record_button.isEnabled()  # the host is the régie
        panel.regie_button.click()
        assert panel.makes_the_mix and to_host and "here" in panel.regie_label.text()
        assert panel.record_button.isEnabled()
        panel.record_button.click()
        assert panel.recorder is not None
        for _ in range(5):
            panel.pump()
        panel.record_button.click()
        files = list((tmp_path / "Exports").glob("mix-together-*.wav"))
        assert len(files) == 1 and "Recorded" in panel.record_label.text()
    finally:
        panel.stop()
        panel.close()
