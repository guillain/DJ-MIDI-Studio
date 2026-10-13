from contextlib import contextmanager

from PySide6.QtWidgets import QPushButton

from djmidi.gui.midi_latency_dialog import MidiLatencyDialog, default_input_for
from djmidi.midi_io import MidiEvent


def _echo_factory(echo: bool, opened: list):
    @contextmanager
    def factory(output, input_name):
        opened.append((output, input_name))
        pending: list[MidiEvent] = []

        def send(channel, note, velocity, note_on):
            if echo and note_on:
                pending.append(MidiEvent("in", str(channel), "Note On", str(note), str(velocity), 0.0))

        def receive():
            ready = list(pending)
            pending.clear()
            return ready

        yield send, receive

    return factory


def _dialog(echo=True, opened=None, outputs=("IAC Driver Bus 1", "DDJ-XP2"), inputs=("DDJ-XP2", "IAC Driver Bus 1")):
    opened = [] if opened is None else opened
    return MidiLatencyDialog(
        port_pair_factory=_echo_factory(echo, opened),
        start_thread=lambda target: target(),
        list_outputs=lambda: list(outputs),
        list_inputs=lambda: list(inputs),
    )


def test_default_input_prefers_same_name():
    assert default_input_for("IAC Driver Bus 1", ["X", "IAC Driver Bus 1"]) == "IAC Driver Bus 1"
    assert default_input_for("DDJ-XP2 OUT", ["X"]) is None


def test_preselects_matching_input_and_shows_echo_warning():
    dialog = _dialog()
    assert dialog.output_combo.currentText() == "IAC Driver Bus 1"
    assert dialog.input_combo.currentText() == "IAC Driver Bus 1"
    warning = dialog.findChild(type(dialog.summary_label), "latencyEchoWarning")
    assert warning is not None and "echo" in warning.text()


def test_run_with_echo_reports_stats():
    opened = []
    dialog = _dialog(opened=opened)
    dialog.count_spin.setValue(3)
    dialog.interval_spin.setValue(0)
    dialog.start()
    dialog.drain_results()
    assert opened == [("IAC Driver Bus 1", "IAC Driver Bus 1")]
    assert len(dialog.results) == 3 and not dialog.running
    assert dialog.last_stats is not None and dialog.last_stats.received == 3
    assert "3/3 replies" in dialog.summary_label.text()
    assert dialog.log_view.toPlainText().count("Ping") == 3
    assert dialog.start_button.text() == "Start"


def test_run_without_echo_says_so():
    dialog = _dialog(echo=False)
    dialog.count_spin.setValue(2)
    dialog.timeout_spin.setValue(5)
    dialog.interval_spin.setValue(0)
    dialog.start()
    dialog.drain_results()
    assert dialog.last_stats.received == 0
    assert "does not seem to echo" in dialog.summary_label.text()


def test_port_open_failure_is_reported():
    @contextmanager
    def failing(output, input_name):
        raise OSError("port busy")
        yield

    dialog = MidiLatencyDialog(
        port_pair_factory=failing,
        start_thread=lambda target: target(),
        list_outputs=lambda: ["A"],
        list_inputs=lambda: ["A"],
    )
    dialog.start()
    dialog.drain_results()
    assert "port busy" in dialog.summary_label.text() and not dialog.running


def test_start_disabled_without_ports():
    dialog = _dialog(outputs=(), inputs=())
    assert not dialog.start_button.isEnabled()


def test_has_help_button():
    dialog = _dialog()
    assert any(b.property("help") for b in dialog.findChildren(QPushButton))


def test_main_window_view_menu_opens_dialog(monkeypatch):
    from djmidi.gui import main_window as mw

    monkeypatch.setattr(mw, "MidiLatencyDialog", lambda parent: _dialog())
    window = mw.MainWindow()
    try:
        window._latency_action.trigger()
        first = window._latency_dialog
        window._latency_action.trigger()
        assert window._latency_dialog is first and first.isVisible()
        first.close()
    finally:
        window.close()
