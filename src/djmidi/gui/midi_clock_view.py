from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget


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
        self.setStyleSheet("#midiClockSurface { background: #0d121b; }")
        layout = QVBoxLayout(self)
        layout.addWidget(clock_panel, 1)


__all__ = ["MidiClockView"]
