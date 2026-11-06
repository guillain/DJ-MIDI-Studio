import logging

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox, QListWidget, QVBoxLayout

from djmidi.gui.click_trail import install_click_trail


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _listen(level):
    logger = logging.getLogger("djmidi.gui.click_trail")
    handler = _Records()
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(level)
    return logger, handler, previous


def _list_in_a_box():
    box = QGroupBox()
    layout = QVBoxLayout(box)
    lst = QListWidget()
    lst.setObjectName("portList")
    lst.addItems(["IAC Driver Bus 1", "IAC Driver Bus 2"])
    layout.addWidget(lst)
    box.resize(300, 200)
    box.show()
    QApplication.processEvents()
    return box, lst


def test_a_click_on_a_list_item_is_logged_with_its_widget_and_item():
    app = QApplication.instance()
    trail = install_click_trail(app)
    logger, handler, previous = _listen(logging.DEBUG)
    box, lst = _list_in_a_box()
    try:
        point = lst.visualItemRect(lst.item(1)).center()
        QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        clicks = [m for m in handler.messages if m.startswith("click:")]
        assert clicks == [
            "click: press on QListWidget#portList < QGroupBox at row 1 col 0 'IAC Driver Bus 2'",
            "click: release on QListWidget#portList < QGroupBox at row 1 col 0 'IAC Driver Bus 2'",
        ]
    finally:
        app.removeEventFilter(trail)
        logger.removeHandler(handler)
        logger.setLevel(previous)
        box.close()


def test_nothing_is_logged_below_debug():
    app = QApplication.instance()
    trail = install_click_trail(app)
    logger, handler, previous = _listen(logging.INFO)
    box, lst = _list_in_a_box()
    try:
        point = lst.visualItemRect(lst.item(0)).center()
        QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        assert handler.messages == []
    finally:
        app.removeEventFilter(trail)
        logger.removeHandler(handler)
        logger.setLevel(previous)
        box.close()
