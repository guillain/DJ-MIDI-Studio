"""Capture documentation screenshots from the current Qt UI without MIDI hardware."""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

# Never open (or create) the real music library index of whoever runs this:
# the Music Library captures below scan a throwaway synthetic library.
os.environ.setdefault("DJMIDI_LIBRARY_DB", ":memory:")

from mutagen.id3 import ID3, TBPM, TCON, TIT2, TKEY, TPE1

from djmidi import catalog
from djmidi.gui.main_window import MainWindow
from djmidi.library import workspace
from djmidi.parser import parse_file
from djmidi.software.traktor import parse_string as parse_traktor

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
# A real Traktor .tsi export (issue #122), committed zipped.
TRAKTOR_FIXTURE = ROOT / "data" / "traktor" / "xdj-xz-settings.tsi.zip"
# Synthetic tracks for the Music Library captures: (folder, title, artist,
# BPM, key, genre tag). Invented demo data -- tiny silent MP3 stubs written
# to a temp dir, never a real collection. The folders mimic a hand-curated
# Genre/Subgenre tree, and two genre tags are deliberately off so the
# category column shows both folder-resolved and fuzzy-suggested cases.
DEMO_TRACKS = (
    ("Tek/Tribe", "Kalimba Stomp", "Crowd Mover", "174", "Am", "Techno"),
    ("Tek/Tribe", "Dust Road", "Sonic Nomad", "172", "Em", "Other"),
    ("Tek/PsyTrance", "Neon Temple", "Astral Ops", "145", "F#m", "House"),
    ("Tek/HardTek", "Iron Floor", "Bassline Riot", "180", "Gm", "Hardtek"),
    ("Electro/Dub", "Roots Signal", "Dub Kitchen", "140", "D", "Dub"),
    ("Electro/Drum & Bass", "Night Runner", "Low Orbit", "174", "Bm", "DnB"),
    ("misc", "Midnight Jungle", "Selecta K", "172", "Bb", "Jungle"),
    ("misc", "Lost Frequencies", "Unknown", "145", "C#m", "Psytrancee"),
)
_MP3_FRAME = bytes([0xFF, 0xFB, 0x90, 0xC4]) + b"\x00" * 413

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
        # Live-send pickers (By Channel/Deck/Controller, Controller Images,
        # emulator) list ports via midi_io directly -- without this, the
        # capturing machine's own MIDI ports leak into the images.
        patch("djmidi.midi_io.list_output_ports", return_value=[]),
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
            "channel": "by-channel.png",
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
            # reference_image is "<slug>/reference.png" since the controller
            # assets moved to controllers/<slug>/ (v0.47.95) -- the slug is the
            # directory, not the file stem (which is "reference" for every one).
            reference = Path(definition.reference_image) if definition.reference_image else None
            if reference is not None and reference.parent.name:
                slug = reference.parent.name
            elif reference is not None:
                slug = reference.stem
            else:
                slug = name.lower().replace(" ", "-")
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
        # (data/controllers/*.json -- distinct from FIXTURE, a Serato mapping
        # XML, not a Controller Setup draft; see that tab's own JSON shape).
        window.left_tabs.setCurrentIndex(window._tab_indexes["setup"])
        for session_file, out_name in SETUP_SESSIONS.items():
            window.controller_setup_view._load_session(ROOT / "data" / "controllers" / session_file)
            # _load_session() leaves the table's selection (and thus its
            # scroll position) wherever the session file's own row order
            # last put it -- scroll back to the top so every screenshot
            # consistently shows the start of the table, not an arbitrary
            # mid-scroll position.
            window.controller_setup_view._table.scrollToTop()
            app.processEvents()
            if not window.grab().save(str(OUTPUT / out_name)):
                raise RuntimeError(f"could not save {out_name}")

        _capture_music_library(app, window)
        _capture_traktor_mapping(app, window)

        window.close()
        app.processEvents()
    return 0


def _write_demo_library(root: Path) -> None:
    for index, (folder, title, artist, bpm, key, genre) in enumerate(DEMO_TRACKS):
        path = root / folder / f"{index:02d} {artist} - {title}.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_MP3_FRAME * 20)
        tags = ID3()
        for frame, value in ((TIT2, title), (TPE1, artist), (TBPM, bpm), (TKEY, key), (TCON, genre)):
            tags.add(frame(encoding=3, text=[value]))
        tags.save(path)


def _save(widget, filename: str) -> None:
    if not widget.grab().save(str(OUTPUT / filename)):
        raise RuntimeError(f"could not save {filename}")


def _capture_music_library(app: QApplication, window: MainWindow) -> None:
    """Music Library tab (issue #132): track panel on a fuzzy-suggested
    track, the category manager, and generated playlists."""
    with tempfile.TemporaryDirectory() as temp:
        music = Path(temp) / "Music"
        _write_demo_library(music)
        view = window.music_library_view
        window.left_tabs.setCurrentIndex(window._tab_indexes["library"])
        app.processEvents()
        view.add_root(music)
        view.start_scan()
        view.run_pending_job()
        view.table.resizeColumnsToContents()
        suggested = next(row for row in view.table_model.rows() if row.category_suggestion)
        view.select_path(suggested.path)
        view.side_tabs.setCurrentIndex(0)
        app.processEvents()
        _save(window, "music-library.png")

        view.side_tabs.setCurrentIndex(1)
        app.processEvents()
        _save(window, "music-library-categories.png")

        seed = next(row for row in view.table_model.rows() if row.title == "Kalimba Stomp")
        view.create_playlist("Friday set", workspace.generate_playlist(view.visible_rows()), workspace.SOURCE_GENERATED)
        view.create_playlist(
            "Mix from Kalimba Stomp",
            workspace.generate_playlist(view.visible_rows(), seed_path=seed.path),
            workspace.SOURCE_GENERATED,
        )
        view.select_path(seed.path)
        app.processEvents()
        _save(window, "music-library-playlists.png")
        view.close_db()


def _capture_traktor_mapping(app: QApplication, window: MainWindow) -> None:
    """A real Traktor .tsi (issue #122) open in the By Channel view."""
    with zipfile.ZipFile(TRAKTOR_FIXTURE) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".tsi"))
        text = archive.read(member).decode("utf-8")
    window.config = parse_traktor(text)
    window.software_id = "traktor"
    window.current_path = Path(member)
    window._load_tree()
    # Its triggers are the XDJ-XZ's own, so show them on that layout.
    window._on_intro_drilldown_requested("channel", "XDJ-XZ")
    app.processEvents()
    _save(window, "traktor-tsi.png")


if __name__ == "__main__":
    raise SystemExit(main())
