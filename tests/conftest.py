import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def _qapp():
    """Widgets (as opposed to QStandardItemModel/QObject) need a QApplication
    to exist before construction; tests run headless via QT_QPA_PLATFORM."""
    app = QApplication.instance() or QApplication([])
    yield app
