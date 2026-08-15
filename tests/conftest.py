import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
import pytest
from PySide6.QtWidgets import QApplication

# The suite is hardware-free.  CoreMIDI enumeration can abort the interpreter
# on a headless or permission-restricted macOS runner before Python can catch
# the native RtMidi error, so expose an empty deterministic port inventory.
mido.get_input_names = list
mido.get_output_names = list


@pytest.fixture(scope="session", autouse=True)
def _qapp():
    """Widgets (as opposed to QStandardItemModel/QObject) need a QApplication
    to exist before construction; tests run headless via QT_QPA_PLATFORM."""
    app = QApplication.instance() or QApplication([])
    yield app
