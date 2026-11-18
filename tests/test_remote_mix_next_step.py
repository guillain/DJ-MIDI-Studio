"""Mix Together always shows the next step (golden rule)."""

from datetime import datetime

from PySide6.QtGui import QGuiApplication

from djmidi.gui.remote_mix_dialog import RemoteMixDialog
from djmidi.remote_mix import next_step, probe
from djmidi.remote_mix.next_step import State


def test_the_steps_follow_what_is_done():
    def key(**kwargs):
        step = next_step.next_step(State(**kwargs))
        return None if step is None else (step.key, step.number, step.action)

    assert key(role="listen") is None
    assert key(role="join") == ("type_address", 1, "focus_address")
    assert key(role="join", has_address=True) == ("start", 1, "start")
    assert key(role="host") == ("start", 1, "start")
    assert key(role="host", running=True) == ("give_address", 1, "copy_address")
    assert key(role="join", running=True) == ("wait_host", 1, None)
    assert key(role="host", running=True, connected=True) == ("link", 2, None)
    assert key(role="host", running=True, connected=True, link=True) == ("sound", 3, "start_sound")
    assert key(role="host", running=True, connected=True, link=True, sound=True) == ("mixing", 4, None)


class _Session:
    def __init__(self, **kwargs):
        self.port, self.peer, self.leading, self.remote_leading = kwargs["port"], None, True, None
        self.follow_error = self.error = None
        self.samples = []

    def start(self):
        pass

    def stop(self):
        pass

    def stats(self):
        return probe.summarise(self.samples, len(self.samples))


def test_the_banner_walks_the_host_through_and_its_button_does_the_step(tmp_path):
    sessions = []

    def factory(**kwargs):
        sessions.append(_Session(**kwargs))
        return sessions[-1]

    dialog = RemoteMixDialog(
        session_factory=factory, link_factory=lambda: None, addresses=lambda: ["10.147.17.5", "192.168.1.4"],
        report_dir=lambda: tmp_path, now=lambda: datetime(2026, 11, 21, 21, 0),  # noqa: DTZ001
        controls_path=tmp_path / "c.json", history_dirs=dict, exports_dir=tmp_path,
    )
    try:
        assert dialog.next_step.key == "start" and dialog.next_step_number.text() == "Step 1 of 4"
        dialog.next_step_button.click()
        assert dialog.running and dialog.next_step.key == "give_address"
        dialog.next_step_button.click()
        assert QGuiApplication.clipboard().text() == "10.147.17.5"
        sessions[0].peer = ("10.147.17.9", 50000)
        sessions[0].samples = [probe.Sample(t=float(i), rtt_ms=38.0, offset_ms=0.0) for i in range(3)]
        dialog.refresh()
        assert dialog.next_step.key == "link" and dialog.next_step_button.isHidden()
        dialog.join_radio.setChecked(True)
        dialog.stop()
        assert dialog.next_step.key == "type_address"
        dialog.address_edit.setText("10.147.17.5")
        assert dialog.next_step.key == "start"
        dialog.listen_radio.setChecked(True)
        assert dialog.next_step_frame.isHidden()
    finally:
        dialog.close()
