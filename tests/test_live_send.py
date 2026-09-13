from PySide6.QtWidgets import QApplication

from djmidi.gui import live_send as live_send_mod
from djmidi.gui import theme
from djmidi.gui.live_send import LiveSendControl


def test_live_send_defaults_to_off(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    control = LiveSendControl()
    assert control.is_active() is False


def test_live_send_refreshes_ports_and_selects_first(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A", "Port B"])
    control = LiveSendControl()
    assert control.selected_port() == "Port A"


def test_resolve_and_send_is_a_noop_when_inactive(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    control = LiveSendControl()
    result = control.resolve_and_send("DDJ-XP2", ("DDJ-XP2", "OTHER", "SHIFT"))
    assert result is None
    assert sent == []


def test_resolve_and_send_is_a_noop_when_no_port_selected(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", list)
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    control = LiveSendControl()
    control._toggle_button.setChecked(True)
    result = control.resolve_and_send("DDJ-XP2", ("DDJ-XP2", "OTHER", "SHIFT"))
    assert result is None
    assert sent == []


def test_resolve_and_send_is_a_noop_for_a_cell_with_no_trigger(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(live_send_mod, "send_control_info_entry", lambda *a, **k: sent.append((a, k)))
    control = LiveSendControl()
    control._toggle_button.setChecked(True)
    result = control.resolve_and_send("DDJ-XP2", ("DDJ-XP2", "MIXER", "Effect 1 Depth"))
    assert result is None
    assert sent == []


def test_resolve_and_send_sends_when_active_with_a_port_and_a_real_trigger(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    sent = []
    monkeypatch.setattr(
        live_send_mod, "send_control_info_entry", lambda port, entry, value: sent.append((port, entry, value))
    )
    control = LiveSendControl()
    control._toggle_button.setChecked(True)
    result = control.resolve_and_send("DDJ-XP2", ("DDJ-XP2", "OTHER", "SHIFT"))
    assert result is not None
    assert result.name == "SHIFT"
    assert sent == [("Port A", result, 127)]


def test_active_changed_signal_fires_on_toggle(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    control = LiveSendControl()
    received = []
    control.activeChanged.connect(received.append)
    control._toggle_button.setChecked(True)
    assert received == [True]
    control._toggle_button.setChecked(False)
    assert received == [True, False]


# ─── Port warning: a real regression report -- "Live send did nothing in
# ─── Serato" traced to picking the controller's own port, not a virtual one ──


def test_port_warning_hidden_for_a_virtual_port(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["IAC Driver Bus 1"])
    control = LiveSendControl()
    assert control._port_warning.isHidden()


def test_port_warning_shown_for_a_controllers_own_port(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["DDJ-XP2"])
    control = LiveSendControl()
    assert not control._port_warning.isHidden()
    assert "DDJ-XP2" in control._port_warning.text()
    assert "Serato" in control._port_warning.text()


def test_port_warning_updates_when_switching_ports(monkeypatch):
    monkeypatch.setattr(
        live_send_mod.midi_io, "list_output_ports", lambda: ["IAC Driver Bus 1", "DDJ-XP2"]
    )
    control = LiveSendControl()
    assert control._port_warning.isHidden()  # first port ("IAC Driver Bus 1") auto-selected
    control._port_combo.setCurrentText("DDJ-XP2")
    assert not control._port_warning.isHidden()
    control._port_combo.setCurrentText("IAC Driver Bus 1")
    assert control._port_warning.isHidden()


def test_port_warning_hidden_when_no_ports_available(monkeypatch):
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", list)
    control = LiveSendControl()
    assert control._port_warning.isHidden()


# ─── theme ──────────────────────────────────────────────────────────────────


def test_off_state_pill_restyles_live_on_a_theme_switch(monkeypatch):
    """The "off" toggle style used to set a literal hardcoded copy of the
    dark palette's colors, so this pill stayed dark even after picking
    Light in Preferences."""
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    control = LiveSendControl()
    assert control.is_active() is False
    try:
        theme.apply_theme(QApplication.instance(), "light")
        c = theme.colors("light")
        assert c["header_bg"] in control._toggle_button.styleSheet()
        assert c["hint_text"] in control._toggle_button.styleSheet()

        theme.apply_theme(QApplication.instance(), "dark")
        d = theme.colors("dark")
        assert d["header_bg"] in control._toggle_button.styleSheet()
    finally:
        theme.apply_theme(QApplication.instance(), "dark")


def test_on_state_pill_stays_the_same_theme_invariant_red_on_a_theme_switch(monkeypatch):
    """The "on" style is deliberately theme-invariant (a hardware-LED-style
    warning), so a theme switch must not touch it -- but the toggle must
    still be re-evaluated for the *current* checked state, not just reset to
    the "off" style."""
    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    control = LiveSendControl()
    control._toggle_button.setChecked(True)
    before = control._toggle_button.styleSheet()
    assert "#c0304a" in before

    theme.apply_theme(QApplication.instance(), "light")
    try:
        assert control._toggle_button.styleSheet() == before
        assert control._toggle_button.text() == "LIVE SEND: ON"
    finally:
        theme.apply_theme(QApplication.instance(), "dark")


def test_restyle_on_a_destroyed_instance_does_not_crash(monkeypatch):
    """An instance embedded in a dynamic Controller Emulator dock is
    destroyed on dock close (_close_emulator_instance), but the persistent
    theme.signals.themeChanged connection outlives it -- a later theme
    switch must not crash trying to restyle a deleted QPushButton."""
    from PySide6.QtWidgets import QWidget

    monkeypatch.setattr(live_send_mod.midi_io, "list_output_ports", lambda: ["Port A"])
    host = QWidget()
    LiveSendControl(parent=host)  # its themeChanged connection outlives this scope
    host.deleteLater()
    QApplication.processEvents()
    QApplication.processEvents()

    try:
        theme.apply_theme(QApplication.instance(), "light")
        theme.apply_theme(QApplication.instance(), "dark")
    finally:
        theme.apply_theme(QApplication.instance(), "dark")
