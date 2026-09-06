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
primitive Controller Setup's "Send once" button already uses).

Picking the right *destination* port is the one thing this widget can't do
for the user, and got a real maintainer confused: sending to a
controller's own port only writes TO the hardware (e.g. its LEDs), never
reaches Serato -- Serato has to be listening on a *virtual* port (e.g. an
IAC Driver bus) added as an extra control surface input in its own MIDI
preferences, mirroring Live Monitor's documented output-direction
constraint (CLAUDE.md) for the reverse direction. `_update_port_warning()`
surfaces an inline warning via `catalog.detect_controller()` when the
selected port's name matches a real, known controller, since that's
exactly the intuitive-but-wrong choice a first-time user reaches for."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog, midi_io
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
        self._port_combo.setToolTip(
            "MIDI output port for Live send -- pick a virtual port (e.g. an "
            "IAC Driver bus) that you've also added as a control surface "
            "input in Serato's own MIDI preferences. Sending to your "
            "controller's own port won't reach Serato: that port writes TO "
            "the hardware (e.g. its LEDs), not to Serato's mapping engine."
        )
        self._port_combo.currentTextChanged.connect(self._update_port_warning)

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

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self._port_combo)
        row.addWidget(self._refresh_button)
        row.addWidget(self._toggle_button)

        # Hidden unless the selected port's name matches a real, known
        # controller (catalog.detect_controller) -- confirmed root cause of
        # a real "Live send does nothing in Serato" report: the maintainer
        # had picked their controller's own port (the intuitive choice),
        # which only writes TO the hardware, never reaches Serato at all.
        # Mirrors Live Monitor's own documented output-direction workaround
        # (CLAUDE.md: a virtual destination must be added as an *extra*
        # Serato MIDI output) for the reverse direction.
        self._port_warning = QLabel()
        self._port_warning.setWordWrap(True)
        self._port_warning.setStyleSheet(
            "QLabel { color: #e0954a; padding: 2px 0; font-size: 11px; }"
        )
        self._port_warning.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
        layout.addWidget(self._port_warning)

        self.refresh_ports()

    def refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        self._port_combo.addItems(midi_io.list_output_ports())
        restored = self._port_combo.findText(current)
        self._port_combo.setCurrentIndex(max(restored, 0))
        self._port_combo.blockSignals(False)
        self._update_port_warning(self._port_combo.currentText())

    def _update_port_warning(self, port_name: str) -> None:
        matches = catalog.detect_controller(port_name) if port_name else []
        if not matches:
            self._port_warning.hide()
            self._port_warning.setText("")
            return
        controller_name = matches[0].controller.name
        self._port_warning.setText(
            f"⚠ \"{port_name}\" looks like {controller_name}'s own port -- it won't reach "
            "Serato. Pick a virtual port (e.g. IAC Driver) added as a control "
            "surface input in Serato's MIDI preferences instead."
        )
        self._port_warning.show()

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
        # resolve_side_aware_variant (not a plain reverse_lookup() +
        # pick_default_variant()) so a right-pad-grid marker's key (e.g.
        # (controller, "PAD", "Pad 3 (R)")) resolves to *that* grid's real
        # deck (2/4), not the left grid's (1/3) -- see that function's
        # docstring for the real report this fixes.
        entry = layout_mod.resolve_side_aware_variant(controller, key)
        if entry is None:
            return None
        send_control_info_entry(port, entry, value)
        return entry


__all__ = ["LiveSendControl"]
