from __future__ import annotations

from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

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
        # This dock used to place clock_panel directly, with no scroll
        # protection at all -- unlike MidiRoutingView, which the panel was
        # split out of (see take_clock_panel()) and which already wraps its
        # own content in a QScrollArea. Found while widening the issue #19
        # clipping audit: when this dock's real minimum width (~400px, from
        # clock_panel's combos/buttons) plus the central widget's own
        # minimum exceeds the window, QMainWindow doesn't shrink either one
        # below its floor -- it lets this dock's geometry extend past the
        # window's right edge instead, so its own title bar (Undock/Close,
        # built by MainWindow) gets silently clipped along with it. A
        # QScrollArea reports a small minimumSizeHint regardless of its
        # content's real size, which is what lets a dock actually shrink to
        # fit instead of overflowing -- confirmed: MidiRoutingView's dock,
        # the one dock that already had this, was the only one whose title
        # bar survived the same repro.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(clock_panel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll, 1)

    def _restyle(self, *_args: object) -> None:
        """Was a literal hardcoded dark background, so this dock stayed dark
        regardless of theme -- same class of bug, and same fix, as
        MidiRoutingView._apply_dj_style, which this dock's actual content
        (the reparented Clock panel) is styled by."""
        self.setStyleSheet(f"#midiClockSurface {{ background: {theme_colors()['window_bg']}; }}")


__all__ = ["MidiClockView"]
