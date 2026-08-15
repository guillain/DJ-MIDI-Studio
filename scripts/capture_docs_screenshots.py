"""Capture documentation screenshots from the current Qt UI without MIDI hardware."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from djmidi.gui.main_window import MainWindow
from djmidi.parser import parse_file

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "images" / "layout"
FIXTURE = ROOT / "data" / "ddj-xp2-custom-4-decks.xml"


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
            "intro": "introduction.png",
            "setup": "controlleur-etup.png",
            "images": "controlleur-image.png",
            "deck": "by-deck.png",
            "controller": "by-controller.png",
            "monitor": "live-monitor.png",
            "routing": "midi-routing.png",
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
        for key in ("monitor", "routing"):
            window._show_tool_dock(key)
        app.processEvents()
        if not window.grab().save(str(OUTPUT / "midi-tools-docked.png")):
            raise RuntimeError("could not save midi-tools-docked.png")

        for key, filename in (
            ("monitor", "live-monitor-floating.png"),
            ("routing", "midi-routing-floating.png"),
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
        window.close()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
