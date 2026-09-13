from PySide6.QtWidgets import QApplication

from djmidi.gui import theme
from djmidi.gui.helpful_notes_dialog import HelpfulNotesDialog


def test_title_color_reflects_the_current_theme():
    """Was a literal hardcoded copy of the dark palette's "title" color, so
    this dialog's heading stayed cyan-on-dark-styled even under Light. A
    fresh instance each time it's shown (not a persistent singleton like
    MidiRoutingView/ControllerSetupView), so reading theme.colors() once at
    construction -- no live themeChanged wiring -- is enough."""
    app = QApplication.instance()
    try:
        theme.apply_theme(app, "light")
        light_dialog = HelpfulNotesDialog()
        assert theme.colors("light")["title"] in light_dialog._title_label.styleSheet()

        theme.apply_theme(app, "dark")
        dark_dialog = HelpfulNotesDialog()
        assert theme.colors("dark")["title"] in dark_dialog._title_label.styleSheet()
    finally:
        theme.apply_theme(app, "dark")


def test_closing_with_yes_emits_closed_persistently(monkeypatch):
    import djmidi.gui.helpful_notes_dialog as module

    monkeypatch.setattr(
        module.QMessageBox, "question", lambda *a, **k: module.QMessageBox.StandardButton.Yes
    )
    dialog = HelpfulNotesDialog()
    received = []
    dialog.closedPersistently.connect(lambda: received.append("persistent"))
    dialog.closedForSession.connect(lambda: received.append("session"))
    dialog.close()
    assert received == ["persistent"]


def test_closing_with_no_emits_closed_for_session(monkeypatch):
    import djmidi.gui.helpful_notes_dialog as module

    monkeypatch.setattr(
        module.QMessageBox, "question", lambda *a, **k: module.QMessageBox.StandardButton.No
    )
    dialog = HelpfulNotesDialog()
    received = []
    dialog.closedPersistently.connect(lambda: received.append("persistent"))
    dialog.closedForSession.connect(lambda: received.append("session"))
    dialog.close()
    assert received == ["session"]


def test_closing_with_cancel_keeps_the_dialog_open(monkeypatch):
    import djmidi.gui.helpful_notes_dialog as module

    monkeypatch.setattr(
        module.QMessageBox, "question", lambda *a, **k: module.QMessageBox.StandardButton.Cancel
    )
    dialog = HelpfulNotesDialog()
    dialog.show()
    received = []
    dialog.closedPersistently.connect(lambda: received.append("persistent"))
    dialog.closedForSession.connect(lambda: received.append("session"))
    dialog.close()
    assert received == []
    assert dialog.isVisible()
