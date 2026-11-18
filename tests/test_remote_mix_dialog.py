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
