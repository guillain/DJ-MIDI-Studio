from PySide6.QtWidgets import QApplication, QWidget

from djmidi.gui import theme
from djmidi.gui.midi_clock_view import MidiClockView


def test_midi_clock_view_restyles_live_on_a_theme_switch():
    """Was a literal hardcoded dark background, so this dock stayed dark
    regardless of theme -- same class of bug, and same fix, as
    MidiRoutingView._apply_dj_style, which this dock's actual content (the
    reparented Clock panel) is styled by."""
    view = MidiClockView(QWidget())
    try:
        theme.apply_theme(QApplication.instance(), "light")
        assert theme.colors("light")["window_bg"] in view.styleSheet()
        assert theme.colors("dark")["window_bg"] not in view.styleSheet()

        theme.apply_theme(QApplication.instance(), "dark")
        assert theme.colors("dark")["window_bg"] in view.styleSheet()
    finally:
        theme.apply_theme(QApplication.instance(), "dark")
