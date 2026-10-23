"""Capture documentation screenshots from the current Qt UI without MIDI hardware."""

from __future__ import annotations

import contextlib
import copy
import os
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import (
    QLocale,
    QObject,
    QPoint,
    Qt,
    QtMsgType,
    QTranslator,
    QUrl,
    Signal,
    qInstallMessageHandler,
)
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QAbstractItemView, QApplication, QTabWidget

# Never open (or create) the real music library index of whoever runs this:
# the Music Library captures below scan a throwaway synthetic library.
os.environ.setdefault("DJMIDI_LIBRARY_DB", ":memory:")
os.environ.setdefault("DJMIDI_WORKSPACE", tempfile.mkdtemp(prefix="djmidi-docs-workspace-"))
# Same for preferences: the docs show the default install (every built-in
# controller enabled), not whichever plugins the person running this disabled.
os.environ.setdefault("DJMIDI_PREFERENCES_FILE", str(Path(tempfile.mkdtemp()) / "preferences.json"))

from mutagen.id3 import ID3, TBPM, TCON, TIT2, TKEY, TPE1

from djmidi import catalog
from djmidi.controller_sync import ControllerSyncSet, SyncMessage
from djmidi.exporter import write_file
from djmidi.gui import cheat_sheet
from djmidi.gui.cheat_sheet_dialog import CheatSheetExportDialog
from djmidi.gui.cheat_sheet_pdf import render_sheet_image
from djmidi.gui.first_run_wizard import FirstRunWizard
from djmidi.gui.main_window import MainWindow
from djmidi.gui.midi_latency_dialog import MidiLatencyDialog
from djmidi.gui.music_library_view import (
    BulkTagDialog,
    RelinkDialog,
    SmartPlaylistDialog,
)
from djmidi.gui.preferences_dialog import PreferencesDialog
from djmidi.gui.rename_files_dialog import RenameFilesDialog
from djmidi.gui.stage_window import StageWindow
from djmidi.gui.translation import install_translators
from djmidi.library import relink, rename, smart_playlist, workspace
from djmidi.midi_io import MidiEvent
from djmidi.parser import parse_file
from djmidi.plugins.preferences import PluginPreferences
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
        patch("djmidi.gui.preferences_dialog.list_output_ports", return_value=[]),
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
            # reference_image is "hardware/<vendor>/<Model>/reference.png" --
            # the slug comes from the directories, not the file stem (which is
            # "reference" for every one). Pioneer models keep their bare name
            # ("ddj-xp2"), other vendors are prefixed ("numark-mixtrack-pro-fx"),
            # matching the screenshot names the docs already link to.
            reference = Path(definition.reference_image) if definition.reference_image else None
            if reference is not None and len(reference.parts) >= 4 and reference.parts[0] == "hardware":
                vendor, model = reference.parts[1], reference.parts[2]
                slug = (model if vendor == "pioneer" else f"{vendor}-{model}").lower()
            elif reference is not None and reference.parent.name:
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

        _capture_function_search(app, window)
        _capture_mapping_diff(app, window)
        _capture_cheat_sheet(app, window)
        _capture_layer_map(app, window)
        _capture_live_ready(app, window)
        _capture_command_palette(app, window)
        _capture_first_run_wizard(app, window)
        _capture_midi_latency(app, window)
        window.statusBar().clearMessage()
        _capture_music_library(app, window)
        _capture_traktor_mapping(app, window)
        _capture_preferences_sync(app)
        _capture_stage_mode(app, window)
        _capture_interface_language(app)
        # Last: it records sync sets and switches the active scene, which
        # the menu bar of every later window capture would show.
        _capture_sync_scene_combo(app, window)

        window.close()
        app.processEvents()
    return 0


def _capture_stage_mode(app: QApplication, window: MainWindow) -> None:
    """Stage Mode (issue #230): a few synthetic XDJ-XZ hits in the compact
    monitor. Captured as a normal window at a fixed size, not full screen --
    the offscreen platform's "screen" is a small square."""
    stage = StageWindow(config_provider=lambda: window.config, initial_controller="XDJ-XZ")
    stage.resize(1600, 900)
    stage.show()
    port = "XDJ-XZ"
    for data1, data2 in (("11", "127"), ("11", "0"), ("12", "127"), ("12", "0")):
        event = MidiEvent("in", "1", "Note On", data1, data2, 0.0, port)
        stage.add_event(event, catalog.lookup("1", "Note On", data1))
    app.processEvents()
    _save(stage, "stage-mode.png")
    stage.close()
    stage.deleteLater()
    app.processEvents()


def _capture_function_search(app: QApplication, window: MainWindow) -> None:
    """Find function (issue #185): a query with its results, first one picked."""
    window.left_tabs.setCurrentIndex(window._tab_indexes["channel"])
    window.function_search_view.set_query("loop roll")
    # Give the results list room: by default it shares the column with the
    # edit panel and shows about one result.
    sizes = window._right_splitter.sizes()
    window._right_splitter.setSizes([360, max(sum(sizes) - 360 - sizes[-1], 100), sizes[-1]])
    app.processEvents()
    if window.function_search_view.result_count():
        window.function_search_view.select_row(0)
    window.left_tabs.setCurrentIndex(window._tab_indexes["channel"])
    app.processEvents()
    _save(window, "function-search.png")
    window.function_search_view.set_query("")
    window._right_splitter.setSizes(sizes)


def _capture_mapping_diff(app: QApplication, window: MainWindow) -> None:
    """Compare with… (issue #189): the open fixture against a copy edited in
    three places -- one trigger missing, one slot moved, one alias value
    changed -- written to a temp file, never next to the fixture."""
    assert window.config is not None
    reference = copy.deepcopy(window.config)
    triggers = sorted({(c.channel, c.event_type, c.control) for c in reference.controls})
    removed, moved, retuned = triggers[3], triggers[12], triggers[25]
    reference.controls = [c for c in reference.controls if (c.channel, c.event_type, c.control) != removed]
    for control in reference.controls:
        trigger = (control.channel, control.event_type, control.control)
        for userio in control.userios:
            for mapping in userio.mappings:
                if trigger == moved and mapping.slot_id is not None:
                    mapping.slot_id = str(int(mapping.slot_id) + 1) if mapping.slot_id.isdigit() else mapping.slot_id
                if trigger == retuned:
                    for translation in mapping.translations:
                        for alias in translation.aliases:
                            if alias.value.isdigit():
                                alias.value = str((int(alias.value) + 1) % 128)
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "friday-set.xml"
        write_file(reference, path)
        dialog = window._compare_with_path(path, "friday-set.xml")
        if dialog is None:
            raise RuntimeError("the mapping comparison failed")
        dialog.resize(1000, 600)
        app.processEvents()
        _save(dialog, "mapping-diff.png")
        dialog.close()
        window._diff_dialog = None


def _capture_cheat_sheet(app: QApplication, window: MainWindow) -> None:
    """File → Export → Cheat Sheet (issue #182): the controller picker and
    the first page it prints for the DDJ-XP2, drawn by the PDF code."""
    assert window.config is not None
    candidates = cheat_sheet.candidate_controllers(window.config)
    names = [name for name, _count in candidates]
    dialog = CheatSheetExportDialog(candidates, window._cheat_sheet_preselection(names), window)
    dialog.show()
    app.processEvents()
    _save(dialog, "cheat-sheet-dialog.png")
    dialog.close()
    sheet = cheat_sheet.build_sheets(window.config, ["DDJ-XP2"])[0]
    if not render_sheet_image(sheet, dpi=110).save(str(OUTPUT / "cheat-sheet-page.png")):
        raise RuntimeError("could not save cheat-sheet-page.png")


def _capture_sync_scene_combo(app: QApplication, window: MainWindow) -> None:
    """The menu bar's sync scene combo (issue #188), opened, with three
    scenes in use -- composed from the window and the popup, which is its
    own top-level window."""
    preferences = window.preferences
    for controller, scene in (("DDJ-XP2", "Default"), ("DDJ-XP2", "Tek"), ("XDJ-XZ", "DnB")):
        message = SyncMessage.create("Note On", 1, 0, 127)
        preferences.set_sync_set(ControllerSyncSet(controller=controller, messages=(message,), scene=scene))
    preferences.active_sync_scene = "Tek"
    window._refresh_sync_scene_combo()
    combo = window._sync_scene_combo
    combo.showPopup()
    app.processEvents()
    image = window.grab().toImage()
    popup = combo.view().window()
    # Drawn just under the combo: the offscreen screen is smaller than the
    # window, so Qt clamps the real popup somewhere else on it.
    offset = combo.mapTo(window, QPoint(0, combo.height()))
    painter = QPainter(image)
    painter.drawPixmap(offset, popup.grab())
    painter.end()
    combo.hidePopup()
    ratio = image.devicePixelRatio()
    corner = window._menu_corner.mapTo(window, QPoint(0, 0))
    left = max(corner.x() - 260, 0)
    height = max(offset.y() + popup.height() + 20, window._menu_corner.height() + 20)
    cropped = image.copy(
        round(left * ratio), 0, round((window.width() - left) * ratio), round(height * ratio)
    )
    if not cropped.save(str(OUTPUT / "sync-scene-combo.png")):
        raise RuntimeError("could not save sync-scene-combo.png")


class _DemoPlayer(QObject):
    """Stands in for QMediaPlayer in the preview capture: reports a duration
    and a position without decoding (or playing) anything."""

    durationChanged = Signal(int)
    positionChanged = Signal(int)
    playbackStateChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._playing = False

    def setSource(self, _url: QUrl) -> None:
        pass

    def play(self) -> None:
        self._playing = True
        self.playbackStateChanged.emit(1)

    def pause(self) -> None:
        self._playing = False
        self.playbackStateChanged.emit(2)

    def stop(self) -> None:
        self._playing = False
        self.playbackStateChanged.emit(0)

    def setPosition(self, position: int) -> None:
        self.positionChanged.emit(position)

    def isPlaying(self) -> bool:
        return self._playing


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


@contextlib.contextmanager
def _demo_music_dir() -> Iterator[Path]:
    """A throwaway folder for the synthetic library. A short fixed path
    under /tmp where there is one, so the duplicates/relink captures show
    readable paths instead of a random /var/folders/... temp name; removed
    before and after either way."""
    base = Path("/tmp/djmidi-docs-demo")
    if not Path("/tmp").is_dir():
        with tempfile.TemporaryDirectory() as temp:
            yield Path(temp) / "Music"
        return
    shutil.rmtree(base, ignore_errors=True)
    try:
        yield base / "Music"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _capture_music_library(app: QApplication, window: MainWindow) -> None:
    """Music Library tab (issue #132): track panel on a fuzzy-suggested
    track, the category manager, and generated playlists."""
    with _demo_music_dir() as music:
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

        # Filters: 170-180 BPM, harmonically compatible with 8A.
        view.side_tabs.setCurrentIndex(0)
        view.bpm_min_filter.setValue(170)
        view.bpm_max_filter.setValue(180)
        view.camelot_filter.setCurrentIndex(view.camelot_filter.findData("8A"))
        view.camelot_compatible_check.setChecked(True)
        app.processEvents()
        _save(window, "music-library-filters.png")
        view.reset_filters()

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

        # "Write tags to selection…": a whole folder selected, the genre
        # typed in the Track panel, so the dialog opens with Genre ticked.
        view.side_tabs.setCurrentIndex(0)
        folder = str(Path(seed.path).parent)
        paths = [row.path for row in view.visible_rows() if str(Path(row.path).parent) == folder]
        view.table.clearSelection()
        view.select_path(paths[0])
        view.select_paths(paths)
        view.field_edits["genre"].setText("Afro House")
        values = {name: edit.text() for name, edit in view.field_edits.items()}
        dialog = BulkTagDialog(values, len(paths), set(view.pending_track_edits()), window)
        dialog.show()
        app.processEvents()
        _save(dialog, "music-library-bulk-tags.png")
        dialog.close()
        view.field_edits["genre"].setText((seed.metadata.genre if seed.metadata else None) or "")

        _capture_library_tools(app, window, seed.path)

        # Audio preview bar (issue #192), playing 2:12 into a 6:00 track.
        preview = view.audio_preview
        preview._player_factory = _DemoPlayer
        view.select_path(seed.path)
        preview.play()
        preview._player.durationChanged.emit(360_000)
        preview._player.positionChanged.emit(132_000)
        app.processEvents()
        _save(preview, "music-library-preview.png")
        preview.stop()

        # Find duplicates… (issue #184): a byte-identical copy and a re-encode
        # (same artist/title, other bytes) of two demo tracks.
        night = next(row for row in view.table_model.rows() if row.title == "Night Runner")
        shutil.copy2(seed.path, music / "misc" / Path(seed.path).name)
        reencode = music / "misc" / "Low Orbit - Night Runner (320).mp3"
        shutil.copy2(night.path, reencode)
        with reencode.open("ab") as handle:
            handle.write(_MP3_FRAME * 5)
        view.start_scan()
        view.run_pending_job()
        view.find_duplicates()
        view.run_pending_job()
        app.processEvents()
        if view.duplicates_dialog is None:
            raise RuntimeError("the duplicate search opened no dialog")
        view.duplicates_dialog.resize(1000, 460)
        view.duplicates_dialog.tree.expandAll()
        app.processEvents()
        _save(view.duplicates_dialog, "music-library-duplicates.png")
        view.duplicates_dialog.close()

        # Relink missing… (issue #190): a folder renamed since the last scan.
        # The proposals are built directly: the view's own job opens the
        # dialog modally, which would block this script.
        (music / "Electro" / "Dub").rename(music / "Electro" / "Dub & Roots")
        lost = next(music.glob("misc/*Lost Frequencies.mp3"))
        (music / "misc" / "Unsorted").mkdir()
        lost.rename(music / "misc" / "Unsorted" / lost.name)
        view.start_scan()
        view.run_pending_job()
        dialog = RelinkDialog(relink.find_relink_proposals(view.db), view)
        dialog.resize(1200, 360)
        dialog.show()
        for column in range(dialog.tree.columnCount()):
            dialog.tree.resizeColumnToContents(column)
        app.processEvents()
        _save(dialog, "music-library-relink.png")
        dialog.close()
        view.close_db()


def _capture_layer_map(app: QApplication, window: MainWindow) -> None:
    """View → Layer Map (issue #253) on the fixture's DDJ-XP2."""
    dialog = window._on_show_layer_map()
    if dialog is None:
        raise RuntimeError("the Layer Map did not open")
    index = dialog.controller_combo.findData("DDJ-XP2")
    if index >= 0:
        dialog.controller_combo.setCurrentIndex(index)
    dialog.resize(1300, 720)
    app.processEvents()
    # The fixture maps the pads in PAD MODE 5 only: center that column so
    # mapped cells show beside free ones.
    mapped = dialog.table.item(0, 10)
    if mapped is not None:
        dialog.table.scrollToItem(mapped, QAbstractItemView.ScrollHint.PositionAtCenter)
    app.processEvents()
    _save(dialog, "layer-map.png")
    dialog.close()


def _capture_live_ready(app: QApplication, window: MainWindow) -> None:
    """Edit → Ready for Live (issue #254): the report on the fixture."""
    dialog = window._on_live_ready_check()
    if dialog is None:
        raise RuntimeError("the Ready for live report did not open")
    dialog.resize(1100, 560)
    app.processEvents()
    _save(dialog, "live-ready.png")
    dialog.close()


def _capture_command_palette(app: QApplication, window: MainWindow) -> None:
    """Cmd+K (issue #222): a query matching menu actions, with their menu
    path and shortcut."""
    window.left_tabs.setCurrentIndex(window._tab_indexes["channel"])
    dialog = window.open_command_palette("save")
    dialog.resize(700, 340)
    app.processEvents()
    _save(dialog, "command-palette.png")
    dialog.close()
    app.processEvents()


def _capture_first_run_wizard(app: QApplication, window: MainWindow) -> None:
    """Help → First-Run Setup (issue #251): two demo controller ports plus an
    unrecognized IAC bus, and a throwaway home holding copies of the fixture
    as Serato mappings -- never the real ~/Music/_Serato_."""
    # A short fixed path where /tmp exists, so the page's folder line reads
    # cleanly (as in _demo_music_dir); removed before and after.
    home = Path("/tmp/djmidi-docs-home") if Path("/tmp").is_dir() else Path(tempfile.mkdtemp())
    shutil.rmtree(home, ignore_errors=True)
    try:
        serato = home / "Music" / "_Serato_" / "MIDI" / "Xml"
        serato.mkdir(parents=True)
        for age, name in enumerate(("xdj_xz-ddj_xp2-4decks.xml", "ddj-xp2-tek-night.xml", "xdj-xz-backup.xml")):
            target = serato / name
            shutil.copyfile(FIXTURE, target)
            stamp = 1_760_000_000 - age * 86_400
            os.utime(target, (stamp, stamp))
        ports = ["PIONEER DDJ-XP2", "XDJ-XZ", "IAC Driver Bus 1"]
        wizard = FirstRunWizard(lambda: ports, home=home, parent=window)
        wizard.resize(640, 480)
        wizard.show()
        for filename in ("first-run-controllers.png", "first-run-mapping.png"):
            wizard.next()
            app.processEvents()
            _save(wizard, filename)
        wizard.close()
        wizard.deleteLater()
        app.processEvents()
    finally:
        shutil.rmtree(home, ignore_errors=True)


@contextlib.contextmanager
def _demo_loopback(_output: str, _input: str) -> Iterator[tuple]:
    """An in-process stand-in for an IAC Driver loopback: every Note On comes
    back after a short, slightly varying delay. Demo timing only -- it opens
    no port and is not a measurement of any real device."""
    import time

    pending: list[tuple[float, MidiEvent]] = []
    sent = [0]

    def send(channel: int, note: int, velocity: int, on: bool) -> None:
        if not on:
            return
        delay = (0.7 + 0.15 * (sent[0] % 5) + (0.4 if sent[0] % 7 == 3 else 0.0)) / 1000.0
        sent[0] += 1
        event = MidiEvent("in", str(channel), "Note On", str(note), str(velocity), 0.0, "IAC Driver Bus 1")
        pending.append((time.perf_counter() + delay, event))

    def receive() -> list[MidiEvent]:
        now = time.perf_counter()
        ready = [event for due, event in pending if due <= now]
        pending[:] = [(due, event) for due, event in pending if due > now]
        return ready

    yield send, receive


def _capture_midi_latency(app: QApplication, window: MainWindow) -> None:
    """View → MIDI Latency Test (issue #255): a finished 20-ping run through
    a simulated IAC loopback (see _demo_loopback), run synchronously."""
    bus = ["IAC Driver Bus 1"]
    dialog = MidiLatencyDialog(
        window,
        port_pair_factory=_demo_loopback,
        start_thread=lambda target: target(),
        list_outputs=lambda: bus,
        list_inputs=lambda: bus,
    )
    dialog.resize(640, 680)
    dialog.show()
    dialog.start()
    dialog.drain_results()
    app.processEvents()
    _save(dialog, "midi-latency.png")
    dialog.close()
    dialog.deleteLater()


def _capture_interface_language(app: QApplication) -> None:
    """Interface language (issue #263): the Dashboard and the Preferences
    General tab built with the French catalogue installed, then removed so
    the remaining captures stay in English."""
    before = set(app.findChildren(QTranslator))
    if install_translators(app, "fr") != "fr":
        raise RuntimeError("the French translation is not available")
    added = [translator for translator in app.findChildren(QTranslator) if translator not in before]
    try:
        french = MainWindow()
        french.resize(1600, 1000)
        # Opened the way File -> Open does, so the "Your files" card shows the
        # loaded mapping too (setting current_path + _load_tree() skipped it
        # and printed "Mapping: none open", issue #331), from a copy under a
        # short demo folder so the card's Folder line shows no personal path.
        with _demo_music_dir() as demo:
            demo.mkdir(parents=True)
            mapping = demo / FIXTURE.name
            shutil.copyfile(FIXTURE, mapping)
            french._load_mapping_from_path(mapping, software_id="serato")
            french.left_tabs.setCurrentIndex(french._tab_indexes["intro"])
            french.show()
            app.processEvents()
            _save(french, "interface-language-fr.png")
        french.close()
        french.deleteLater()
        preferences = PluginPreferences()
        preferences.language = "fr"
        dialog = PreferencesDialog(preferences)
        dialog.resize(640, 520)
        dialog.show()
        app.processEvents()
        # Only the tabs down to the Language row: further down, the log file
        # and workspace rows print paths of whoever runs this script.
        language = dialog._language
        bottom = language.mapTo(dialog, QPoint(0, language.height())).y() + 4
        pixmap = dialog.grab()
        ratio = pixmap.devicePixelRatio()
        cropped = pixmap.copy(0, 0, round(dialog.width() * ratio), round(bottom * ratio))
        if not cropped.save(str(OUTPUT / "interface-language-preferences.png")):
            raise RuntimeError("could not save interface-language-preferences.png")
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
    finally:
        for translator in added:
            app.removeTranslator(translator)


def _demo_cover(path: Path) -> None:
    """A plain generated picture for the cover-art capture (no real artwork)."""
    image = QImage(600, 600, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 600, 600)
    gradient.setColorAt(0.0, QColor("#1b2a6b"))
    gradient.setColorAt(1.0, QColor("#d9468f"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(QColor("white"))
    font = QFont()
    font.setPixelSize(64)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "KALIMBA\nSTOMP")
    painter.end()
    if not image.save(str(path)):
        raise RuntimeError("could not write the demo cover")


def _capture_library_tools(app: QApplication, window: MainWindow, seed_path: str) -> None:
    """Music Library tools added in issues #256-#261 and #279: cover art, statistics,
    smart playlist rules, file renaming and the change history -- all on
    the synthetic demo library."""
    view = window.music_library_view
    view.side_tabs.setCurrentIndex(0)

    # A tag write, logged in the change history below.
    dust = next(row for row in view.table_model.rows() if row.title == "Dust Road")
    view.table.clearSelection()
    view.select_path(dust.path)
    view.field_edits["genre"].setText("Tribe")
    view.apply_track_edits()

    # Cover art (issue #256): a generated picture set on the seed track.
    view.table.clearSelection()
    view.select_path(seed_path)
    with tempfile.TemporaryDirectory() as temp:
        cover = Path(temp) / "demo-cover.png"
        _demo_cover(cover)
        if not view.set_cover_from_file(str(cover)):
            raise RuntimeError("the demo cover was not written")
    app.processEvents()
    _save(window, "music-library-cover.png")

    # Statistics (issue #258).
    view.show_statistics()
    if view.stats_dialog is None:
        raise RuntimeError("the statistics window did not open")
    view.stats_dialog.resize(900, 600)
    app.processEvents()
    _save(view.stats_dialog, "music-library-statistics.png")
    view.stats_dialog.close()

    # Smart playlist rules (issue #259).
    rules = smart_playlist.SmartRules(
        category="Tek", bpm_min=170, bpm_max=180, camelot_key="8A", key_compatible=True, limit=40
    )
    dialog = SmartPlaylistDialog("Tek peak time", rules, view.db.has_play_stats(), view)
    # English number format whatever the capturing machine's locale, to
    # match the English interface ("170.0", not "170,0").
    dialog.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    dialog.show()
    app.processEvents()
    _save(dialog, "music-library-smart-playlist.png")
    dialog.close()
    view.create_smart_playlist(dialog.name(), dialog.rules())

    # Rename files (issue #260): the preview for the Tek folder; only the
    # tracks later captures don't use are actually renamed.
    tek = [row.path for row in view.table_model.rows() if "/Tek/" in row.path]
    dialog = RenameFilesDialog(
        lambda text: rename.plan_from_db(view.db, tek, text), "{camelot} - {bpm} - {artist} - {title}", view
    )
    dialog.resize(1000, 460)
    dialog.show()
    app.processEvents()
    _save(dialog, "music-library-rename.png")
    pairs = [(old, new) for old, new in dialog.renames() if old != seed_path]
    dialog.close()
    view.rename_files(pairs)

    # Change history (issues #261/#279): the tag write, cover and renames above.
    history = view.show_change_history()
    history.resize(1100, 560)
    app.processEvents()
    _save(history, "music-library-change-history.png")
    history.close()
    view.side_tabs.setCurrentIndex(0)


def _capture_preferences_sync(app: QApplication) -> None:
    """Preferences → Controller sync with two recorded sets."""
    preferences = PluginPreferences()
    for controller, port, notes, scene in (
        ("DDJ-XP2", "PIONEER DDJ-XP2", (27, 30), "Default"),
        ("DDJ-XP2", "PIONEER DDJ-XP2", (27,), "Tek"),
        ("XDJ-XZ", "XDJ-XZ (1)", (0, 1, 31), "Default"),
    ):
        messages = tuple(SyncMessage.create("Note On", 1, note, 127) for note in notes)
        preferences.set_sync_set(
            ControllerSyncSet(controller=controller, output_port=port, messages=messages, scene=scene)
        )
    dialog = PreferencesDialog(preferences)
    dialog.findChild(QTabWidget).setCurrentIndex(2)
    dialog.resize(640, 420)
    dialog.show()
    app.processEvents()
    _save(dialog, "preferences-controller-sync.png")
    dialog.close()


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
