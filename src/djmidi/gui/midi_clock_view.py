from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from djmidi.gui.theme import colors as theme_colors
from djmidi.gui.theme import signals as theme_signals


class MidiClockView(QWidget):
    """Independent surface for MIDI Clock configuration and diagnostics.

    The routing view still owns the clock session for now; this thin surface
    keeps the clock controls independently dockable without duplicating the
    safety-critical routing state.
    """

    def __init__(self, clock_panel: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("midiClockSurface")
        self.setAutoFillBackground(True)
        self._restyle()
        theme_signals.themeChanged.connect(self._restyle)
        layout = QVBoxLayout(self)
        layout.addWidget(clock_panel, 1)

    def _restyle(self, *_args: object) -> None:
        """Was a literal hardcoded dark background, so this dock stayed dark
        regardless of theme -- same class of bug, and same fix, as
        MidiRoutingView._apply_dj_style, which this dock's actual content
        (the reparented Clock panel) is styled by."""
        self.setStyleSheet(f"#midiClockSurface {{ background: {theme_colors()['window_bg']}; }}")


__all__ = ["MidiClockView"]
