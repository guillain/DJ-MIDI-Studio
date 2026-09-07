"""Capture documentation screenshots from the current Qt UI without MIDI hardware."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from djmidi import catalog
from djmidi.gui.main_window import MainWindow
from djmidi.parser import parse_file

# Purely cosmetic noise from running under QT_QPA_PLATFORM=offscreen: the
# offscreen platform plugin has no real window manager, so every
# dock.setFloating(True) + .show()/.raise_() pair here (this script's own
# floating-dock screenshots, and _create_emulator_instance()'s internal
# .raise_() call) logs a "this plugin does not support ..." qWarning().
# Harmless and expected -- these two calls have no QLoggingCategory to
# target with QT_LOGGING_RULES, so filter by message text instead of
# suppressing every Qt warning (which could hide a real one).
_NOISY_OFFSCREEN_MESSAGES = (
    "This plugin does not support propagateSizeHints()",
    "This plugin does not support raise()",
)


def _filter_offscreen_platform_noise(msg_type: QtMsgType, context, message: str) -> None:
    if any(noisy in message for noisy in _NOISY_OFFSCREEN_MESSAGES):
        return
    # Anything else (a real warning, our own app's log output, ...) still
    # reaches stderr exactly as Qt's own default handler would print it.
    stream = sys.stderr if msg_type != QtMsgType.QtDebugMsg else sys.stdout
    print(message, file=stream)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "images" / "layout"
CONTROLLERS_OUTPUT = ROOT / "docs" / "images" / "controllers"
FIXTURE = ROOT / "data" / "xdj_xz-ddj_xp2-4decks.xml"
# Controller Setup session files recorded from real hardware (see that
# tab's own docstring for the JSON shape: version/controller_name/
# recorded_events/rows) -- distinct from FIXTURE above, which is a Serato
# mapping XML, not a Controller Setup draft.
SETUP_SESSIONS = {
    "ddj_xp2.json": "controlleur-setup-ddj-xp2.png",
    "xdj_xz.json": "controlleur-setup-xdj-xz.png",
    "xdj_xz-ddj_xp2.json": "controlleur-setup-xdj-xz-ddj-xp2.png",
}


class _OfflineMidiMonitor:
    VIRTUAL_MONITOR_NAME = "DJMidiStudio Monitor"

    def open_input(self, _name: str) -> None:
        pass

    def open_virtual_monitor(self) -> None:
        pass

    def close_all(self) -> None:
        pass

    def poll(self) -> list:
        return []


def main() -> int:
    # Must be set before QApplication exists -- Qt reads QT_LOGGING_RULES
    # at logging-subsystem init time. Silences "Populating font family
    # aliases took ...ms. Replace uses of missing font family 'Sans
    # Serif' ..." -- a real Qt category (qt.qpa.fonts), so the standard
    # rules mechanism handles it cleanly, unlike the two uncategorized
    # qWarning() calls _filter_offscreen_platform_noise() filters below.
    # Purely cosmetic: QT_QPA_PLATFORM=offscreen has no real font database
    # to resolve "Sans Serif" against, but nothing in this script's
    # captures depends on that resolution succeeding.
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")
    qInstallMessageHandler(_filter_offscreen_platform_noise)
    app = QApplication.instance() or QApplication(sys.argv)
    with (
        patch("djmidi.gui.live_monitor.list_input_ports", return_value=[]),
        patch("djmidi.gui.live_monitor.MidiMonitor", _OfflineMidiMonitor),
        patch("djmidi.gui.controller_setup.list_input_ports", return_value=[]),
        patch("djmidi.gui.controller_setup.list_output_ports", return_value=[]),
        patch("djmidi.gui.controller_setup.MidiMonitor", _OfflineMidiMonitor),
        patch("djmidi.gui.midi_routing_view.list_input_ports", return_value=[]),
        patch("djmidi.gui.midi_routing_view.list_output_ports", return_value=[]),
    ):
        window = MainWindow()
        window.resize(1600, 1000)
        window.config = parse_file(FIXTURE)
        window.current_path = FIXTURE
        window._load_tree()
        window.show()
        app.processEvents()
        captures = {
            "intro": "dashboard.png",
            "setup": "controlleur-setup.png",
            "images": "controlleur-image.png",
            "deck": "by-deck.png",
            "controller": "by-controller.png",
            "monitor": "live-monitor.png",
            "routing": "midi-routing.png",
            "clock": "midi-clock.png",
            "metronome": "metronome.png",
        }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for key, filename in captures.items():
            if key in window._tab_indexes:
                window.left_tabs.setCurrentIndex(window._tab_indexes[key])
            else:
                window._show_tool_dock(key)
            app.processEvents()
            if not window.grab().save(str(OUTPUT / filename)):
                raise RuntimeError(f"could not save {filename}")
            if key in window._tool_docks:
                window._tool_docks[key].hide()

        # Capture the supported workspace compositions.  Arbitrary dock
        # positions and sizes are user-defined, so these are stable reference
        # arrangements rather than an attempt to enumerate every possibility.
        for key in ("monitor", "routing", "clock", "metronome"):
            window._show_tool_dock(key)
        app.processEvents()
        if not window.grab().save(str(OUTPUT / "midi-tools-docked.png")):
            raise RuntimeError("could not save midi-tools-docked.png")

        for key, filename in (
            ("monitor", "live-monitor-floating.png"),
            ("routing", "midi-routing-floating.png"),
            ("clock", "midi-clock-floating.png"),
            ("metronome", "metronome-floating.png"),
        ):
            dock = window._tool_docks[key]
            dock.setFloating(True)
            dock.resize(900, 700)
            dock.show()
            app.processEvents()
            if not dock.grab().save(str(OUTPUT / filename)):
                raise RuntimeError(f"could not save {filename}")
            dock.setFloating(False)
            dock.hide()

        # One Controller Emulator screenshot per registered controller, in
        # its own subdirectory -- unlike the tabs above (which show the
        # loaded config's two controllers together), the emulator is a
        # single-controller view, so this is the natural way to capture
        # every controller's own layout (real-position schematic for the 6
        # with geometry, classic card grid for the other 2) without
        # depending on which controllers happen to be in FIXTURE. Bypasses
        # whatever controller plugins happen to be enabled in *this
        # machine's* real, persisted PluginPreferences (MainWindow.__init__
        # already narrowed catalog.CONTROLLER_NAMES to just those, exactly
        # like the real "Show all controllers" View-menu toggle's off
        # state) -- docs screenshots must show every registered controller
        # regardless of which ones the person running this script actually
        # owns.
        catalog.set_enabled_plugin_ids(None)
        CONTROLLERS_OUTPUT.mkdir(parents=True, exist_ok=True)
        for name in catalog.CONTROLLER_NAMES:
            definition = catalog.get_definition(name)
            slug = Path(definition.reference_image).stem if definition.reference_image else name.lower().replace(
                " ", "-"
            )
            before_ids = set(window._emulator_docks.keys())
            emulator_dock = window._create_emulator_instance(name)
            instance_id = next(iter(set(window._emulator_docks.keys()) - before_ids))
            emulator_dock.setFloating(True)
            emulator_dock.resize(900, 700)
            emulator_dock.show()
            app.processEvents()
            if not emulator_dock.grab().save(str(CONTROLLERS_OUTPUT / f"{slug}.png")):
                raise RuntimeError(f"could not save {slug}.png")
            window._close_emulator_instance(instance_id)
            app.processEvents()

        # Controller Setup with a real hardware-recorded session loaded
        # (data/*.json -- distinct from FIXTURE, a Serato mapping XML, not
        # a Controller Setup draft; see that tab's own JSON shape).
        window.left_tabs.setCurrentIndex(window._tab_indexes["setup"])
        for session_file, out_name in SETUP_SESSIONS.items():
            window.controller_setup_view._load_session(ROOT / "data" / session_file)
            # _load_session() leaves the table's selection (and thus its
            # scroll position) wherever the session file's own row order
            # last put it -- scroll back to the top so every screenshot
            # consistently shows the start of the table, not an arbitrary
            # mid-scroll position.
            window.controller_setup_view._table.scrollToTop()
            app.processEvents()
            if not window.grab().save(str(OUTPUT / out_name)):
                raise RuntimeError(f"could not save {out_name}")

        window.close()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
