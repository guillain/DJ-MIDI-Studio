"""Long message boxes keep their buttons on screen (the Music library's Trash
confirmation used to push Yes/No below the screen)."""

from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox, QScrollArea

from djmidi.gui import message_box_fit


def _box(text: str) -> QMessageBox:
    box = QMessageBox(QMessageBox.Icon.Question, "Move to Trash", text)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    return box


def _long_trash_text() -> str:
    lines = [
        f"• /Users/someone/Music/Collection/Artist {n}/Album {n}/0{n} Some rather long track title.mp3\n"
        f"    keeps /Users/someone/Music/Collection/Artist {n}/Album {n}/0{n} Some rather long track title (1).mp3"
        for n in range(15)
    ]
    return "Move 15 file(s) to the Trash?\n\n" + "\n".join(lines) + "\n… and 12 more\n\nYou can put them back."


def test_a_long_message_box_scrolls_and_keeps_its_buttons_on_screen():
    app = QApplication.instance()
    fitter = message_box_fit.install(app)
    try:
        box = _box(_long_trash_text())
        box.show()
        app.processEvents()
        app.processEvents()  # the deferred resize
        screen = box.screen().availableGeometry()
        assert box.findChild(QScrollArea, "djmidiMessageScroll") is not None
        assert box.height() <= screen.height() and box.width() <= screen.width()
        buttons = box.findChild(QDialogButtonBox)
        bottom = buttons.mapTo(box, buttons.rect().bottomLeft()).y()
        assert bottom <= box.height()
        box.close()
    finally:
        app.removeEventFilter(fitter)
        message_box_fit._INSTALLED.remove(fitter)


def test_a_short_message_box_is_left_alone():
    box = _box("Move 1 file to the Trash?")
    assert not message_box_fit.fit_message_box(box)
    assert box.findChild(QScrollArea, "djmidiMessageScroll") is None
