import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Never let the suite read (or write) the developer's real preferences file:
# MainWindow() loads it on construction and, via _apply_plugin_preferences,
# pins catalog's enabled-controller filter to whatever the developer has
# toggled — which then hides throwaway controllers registered by later tests.
os.environ.setdefault(
    "DJMIDI_PREFERENCES_FILE",
    os.path.join(tempfile.gettempdir(), "djmidi-test-preferences.json"),
)

import mido
import pytest
from PySide6.QtWidgets import QApplication

from djmidi import catalog, software

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


@pytest.fixture(autouse=True)
def _reset_plugin_enablement():
    """Keep the global controller/software enablement filter from leaking
    between tests. MainWindow() and _apply_plugin_preferences() set it as a
    side effect; without this a test that disables a controller (or just
    constructs a window) makes later throwaway-controller tests flaky
    depending on run order.

    Also drop a real ``catalog.CONTROLLER_NAMES`` attribute if one was left
    behind: ``monkeypatch.setattr(catalog, "CONTROLLER_NAMES", ...)`` restores
    a *static* list on teardown (the name is normally served by the module
    ``__getattr__``), permanently shadowing the live registry view.
    """
    yield
    catalog.set_enabled_plugin_ids(None)
    software.set_enabled_plugin_ids(None)
    for frozen in ("CONTROLLER_NAMES", "PAD_COUNTS"):
        if frozen in vars(catalog):
            delattr(catalog, frozen)
