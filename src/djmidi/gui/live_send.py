"""Live-send control (issue #9's phase 4 / the Controller Emulator roadmap's
addendum, `~/.claude/plans/purrfect-fluttering-quail.md`): a small, reusable
widget pairing an output-port picker with a very visibly styled "Live send"
toggle, embeddable in any layout surface that wants an opt-in real-MIDI-send
capability alongside its existing dry-run/audit behavior --
gui/controller_emulator.py's ControllerEmulatorView, gui/layout_view.py's
ControllerLayoutView, and gui/controller_image_view.py's ControllerImageView.

Default OFF, always: ControllerLayoutView (By Channel/Deck/Controller) is
browsed constantly while auditing a mapping, and ControllerImageView is
looked at just to see a real photo -- neither must ever send live MIDI from
an ordinary click unless the user has deliberately turned this on, and the
ON state must be impossible to miss (a persistent, high-contrast badge, not
a small checkbox). The dedicated Controller Emulator dock is the one
exception in spirit (clicking there is already the whole point of the tab),
but it uses the exact same widget/default for consistency rather than a
separate always-on path.

Resolution (CellKey -> raw ControlInfo trigger) and the actual send both
reuse existing, tested code -- no new MIDI-sending logic anywhere in this
module: layout.reverse_lookup() + layout.pick_default_variant() for
resolution (the same pair the Controller Emulator's own dry-run already
uses), session_player.send_control_info_entry() for the send (the same
primitive Controller Setup's "Send once" button already uses)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QWidget

from djmidi import midi_io
from djmidi.catalog._registry import ControlInfo
from djmidi.gui import layout as layout_mod
from djmidi.session_player import send_control_info_entry

_DEFAULT_SEND_VALUE = 127


class LiveSendControl(QWidget):
    """Output-port combo + a checkable "Live send" toggle, default off.

    Callers should route every click through resolve_and_send() rather than
    checking is_active() themselves first -- it already no-ops (returns
    None) when live send is off, no port is selected, or the clicked cell
    has no raw MIDI trigger at all, so the call site stays a single line
    regardless of state."""

    activeChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(150)
        self._port_combo.setToolTip("MIDI output port for Live send")

        self._refresh_button = QPushButton("⟳")
        self._refresh_button.setToolTip("Refresh output ports")
        self._refresh_button.setFixedWidth(26)
        self._refresh_button.clicked.connect(self.refresh_ports)

        self._toggle_button = QPushButton()
        self._toggle_button.setCheckable(True)
        self._toggle_button.setToolTip(
            "When ON, clicking a control here sends a real MIDI message to the "
            "selected output port -- not just dry-run resolution."
        )
        self._toggle_button.toggled.connect(self._on_toggled)
        self._apply_toggle_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._port_combo)
        layout.addWidget(self._refresh_button)
        layout.addWidget(self._toggle_button)

        self.refresh_ports()

    def refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        self._port_combo.addItems(midi_io.list_output_ports())
        restored = self._port_combo.findText(current)
        self._port_combo.setCurrentIndex(max(restored, 0))
        self._port_combo.blockSignals(False)

    def _on_toggled(self, checked: bool) -> None:
        self._apply_toggle_style(checked)
        self.activeChanged.emit(checked)

    def _apply_toggle_style(self, checked: bool) -> None:
        if checked:
            self._toggle_button.setText("LIVE SEND: ON")
            self._toggle_button.setStyleSheet(
                "QPushButton {"
                " background: #c0304a; color: #ffffff; font-weight: bold;"
                " border: 2px solid #ff5577; border-radius: 5px; padding: 4px 10px;"
                " }"
            )
        else:
            self._toggle_button.setText("Live send: off")
            self._toggle_button.setStyleSheet(
                "QPushButton {"
                " background: #202d3d; color: #8fa7bd;"
                " border: 1px solid #3a506d; border-radius: 5px; padding: 4px 10px;"
                " }"
            )

    def is_active(self) -> bool:
        return self._toggle_button.isChecked()

    def selected_port(self) -> str | None:
        text = self._port_combo.currentText()
        return text or None

    def resolve_and_send(
        self, controller: str, key: layout_mod.CellKey, value: int = _DEFAULT_SEND_VALUE
    ) -> ControlInfo | None:
        """Resolves `key` (a schematic CellKey, e.g. from a layout click) to
        a raw trigger and sends it, only when live send is on, a port is
        selected, and the cell actually has a raw MIDI trigger. Returns the
        ControlInfo actually sent, or None otherwise -- callers can use the
        return value for status feedback without a separate is_active() check."""
        if not self.is_active():
            return None
        port = self.selected_port()
        if not port:
            return None
        variants = layout_mod.reverse_lookup(controller).get(key)
        if not variants:
            return None
        entry = layout_mod.pick_default_variant(variants)
        send_control_info_entry(port, entry, value)
        return entry


__all__ = ["LiveSendControl"]
