from __future__ import annotations

import logging
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QSettings,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QStandardItemModel,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from djmidi import backup, catalog, file_locations, software, sync_store, user_paths
from djmidi.catalog.profile import load_user_profiles
from djmidi.controller_sync import (
    ControllerSyncSet,
    PlugInSyncTracker,
    SyncResult,
    normalize_scene,
    run_sync,
    scene_names,
    summarize_results,
    sync_sets_from_recording,
)
from djmidi.function_search import FunctionResult
from djmidi.gui import cheat_sheet
from djmidi.gui import jog as jog_mod
from djmidi.gui import layout as layout_mod
from djmidi.gui.cheat_sheet_dialog import CheatSheetExportDialog
from djmidi.gui.cheat_sheet_pdf import write_cheat_sheet_pdf
from djmidi.gui.controller_emulator import ControllerEmulatorView
from djmidi.gui.controller_image_view import ControllerImageView
from djmidi.gui.controller_setup import ControllerSetupView
from djmidi.gui.controller_tree import CELL_KEY_ROLE, build_controller_columns
from djmidi.gui.deck_tree import build_deck_columns
from djmidi.gui.edit_panel import EditPanel
from djmidi.gui.file_reveal import reveal_in_file_manager
from djmidi.gui.function_search_view import FunctionSearchView
from djmidi.gui.geometry import resolve_geometry_label
from djmidi.gui.helpful_notes_dialog import HelpfulNotesDialog
from djmidi.gui.introduction_view import IntroductionView
from djmidi.gui.layout_view import ControllerLayoutView
from djmidi.gui.live_monitor import LiveMonitorView
from djmidi.gui.mapping_diff_dialog import MappingDiffDialog
from djmidi.gui.mapping_group import MappingGroup
from djmidi.gui.metronome_view import MetronomeView
from djmidi.gui.midi_clock_view import MidiClockView
from djmidi.gui.midi_routing_view import MidiRoutingView
from djmidi.gui.music_library_view import MusicLibraryView
from djmidi.gui.preferences_dialog import PreferencesDialog
from djmidi.gui.safe_update_dialog import SafeUpdateDialog
from djmidi.gui.scroll_utils import AutoSizeScrollArea
from djmidi.gui.splitter_utils import replace_splitter, scrollable_columns
from djmidi.gui.theme import apply_theme, mapping_tree_stylesheet
from djmidi.gui.theme import signals as theme_signals
from djmidi.gui.tree_model import NODE_ROLE, build_channel_columns, relabel_item
from djmidi.gui.update_notice import UpdateChecker
from djmidi.integration_detection import (
    detect_controller_ports,
    detect_software_mapping,
)
from djmidi.logging_config import configure_logging, current_log_path
from djmidi.mapping_diff import diff_configs
from djmidi.midi_io import MidiEvent, MidiMonitor, list_input_ports, list_output_ports
from djmidi.model import Control, MappingElement, MidiConfig
from djmidi.plugins import PluginPreferences, default_preferences_path
from djmidi.safe_update import prepare_update
from djmidi.update_check import ReleaseInfo, current_version, is_check_due, is_newer
from djmidi.validator import ValidationIssue, validate

_SEVERITY_COLORS = {
    "error": QColor(255, 200, 200),
    "warning": QColor(255, 235, 180),
    "info": QColor(225, 225, 225),
}

# The official docs catalog.py was transcribed from (see controllers/README.md).
_REFERENCE_LINKS = [
    ("Serato MIDI Mapping Guide", "https://support.serato.com/hc/en-us/articles/209377487-MIDI-mapping-with-Serato-DJ-Pro"),
    (
        "XDJ-XZ MIDI Message List (PDF)",
        "https://downloads.support.alphatheta.com/software_info/all-in-one-dj-systems/XDJ-XZ/XDJ-XZ_MIDI_Message_List_E3.pdf",
    ),
    (
        "DDJ-XP2 MIDI Message List (PDF)",
        "https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-XP2/DDJ-XP2_MIDI_Message_List_E1.pdf",
    ),
    (
        "Ableton Link documentation",
        "https://www.ableton.com/en/link/",
    ),
    (
        "DJ TechTools: Serato external sync overview",
        "https://djtechtools.com/2018/06/27/serato-dj-pro-four-ways-for-syncing-with-external-gear/",
    ),
]

_REVEAL_LABEL = "Show Mapping in Finder" if sys.platform == "darwin" else "Show Mapping in File Manager"
_RECENT_SETTINGS_KEY = "files/recent_mappings"
_LAST_DIR_SETTINGS_KEY = "files/last_mapping_dir"
_LAST_MAPPING_SETTINGS_KEY = "files/last_mapping"
_LAST_SOFTWARE_SETTINGS_KEY = "files/last_mapping_software"
_LAST_DRAFT_SETTINGS_KEY = "files/last_draft"
# Lets controllers' MIDI ports settle before the launch-time Sync.
_STARTUP_SYNC_DELAY_MS = 1500
# Startup update check (issue #193): after the window is up, at most once a day.
_STARTUP_UPDATE_CHECK_DELAY_MS = 3000
_LAST_UPDATE_CHECK_SETTINGS_KEY = "updates/last_check"
# How often output ports are listed to spot a controller being plugged in.
_PLUG_IN_POLL_MS = 2000

_LOCAL_HELP_DOCUMENTS = [
    ("Documentation Home", "docs/README.md"),
    ("Features Overview", "docs/enduser/README.md"),
    ("User Guide", "docs/enduser/user-guide.md"),
    ("Feature Pages", "docs/enduser/features/README.md"),
    ("End-to-End Examples", "docs/enduser/examples.md"),
    ("Supported Controllers", "docs/enduser/controller-profiles.md"),
    ("MIDI Clock Compatibility", "docs/enduser/midi-clock-compatibility.md"),
    ("Developer Documentation", "docs/developer/README.md"),
    ("Architecture", "docs/developer/design/architecture.md"),
    ("Build and Release", "docs/developer/cicd/build-and-release.md"),
]

_LOCAL_CONTROLLER_DOCUMENTS = [
    ("Controller documentation index", "controllers/README.md"),
    ("DDJ-XP2 MIDI Message List", "controllers/hardware/pioneer/DDJ-XP2/ddj-xp2-midi-message-list-e1.pdf"),
    ("XDJ-XZ MIDI Message List", "controllers/hardware/pioneer/XDJ-XZ/xdj-xz-midi-message-list-e3.pdf"),
    ("DDJ-1000 MIDI Message List", "controllers/hardware/pioneer/DDJ-1000/ddj-1000-midi-message-list-e1.pdf"),
    ("DDJ-FLX10 MIDI Message List", "controllers/hardware/pioneer/DDJ-FLX10/ddj-flx10-midi-message-list-e1.pdf"),
    ("DDJ-FLX4 MIDI Message List", "controllers/hardware/pioneer/DDJ-FLX4/ddj-flx4-midi-message-list-e1.pdf"),
    ("DDJ-REV1 MIDI Message List", "controllers/hardware/pioneer/DDJ-REV1/ddj-rev1-midi-message-list-e1.pdf"),
    ("Numark Mixtrack Pro FX User Guide", "controllers/hardware/numark/Mixtrack-Pro-FX/numark-mixtrack-pro-fx-user-guide-v1.2.pdf"),
    (
        "Hercules DJControl Inpulse 500 Product Sheet",
        "controllers/hardware/hercules/DJControl-Inpulse-500/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf",
    ),
]


_LOGGER = logging.getLogger(__name__)
_BACKUP_FILTER = "DJ MIDI Studio backup (*.zip);;All files (*)"


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} bytes"

# Performance Mode: how much to shrink the tree pane (never fully to 0 -- the
# pair splitters are non-collapsible by design) and how much to enlarge the
# schematic layout glyphs.
_PERFORMANCE_TREE_RATIO = 0.03
_PERFORMANCE_ZOOM_FACTOR = 1.6


def _refresh_tree_row_layout(view: QTreeView) -> None:
    """Force Qt to repaint every currently *visible* branch row under
    `view`'s current stylesheet.

    `QTreeView.setStyleSheet()` alone leaves a row's already-laid-out area
    showing whatever background was cached the *last* time that row's
    expand state changed -- found on By Controller after a live theme
    switch: rows that stay collapsed (`_apply_controller_expand_state`
    only expands a section with a used leaf) rendered with the *previous*
    theme's dark background indefinitely, while rows that had just been
    freshly expanded/collapsed painted correctly. By Channel/Deck never
    showed this because `expandToDepth(0)` touches every top-level row's
    expand state once at construction, well before any later theme switch
    -- by then Qt has nothing stale left to redraw for those specific
    rows. Toggling a row's expanded state off and immediately back to
    whatever it already was is a UI no-op but forces the repaint.

    Deliberately bounded to the viewport rather than a recursive full-model
    walk (which this started as): a row that isn't currently painted has
    nothing stale to fix -- scrolling to it afterwards already repaints
    correctly on its own (confirmed: a live theme switch followed by a
    scroll renders every newly-revealed row in the *current* theme, no
    staleness). Bounding the cost to "however many rows are on screen"
    also matters for a reason unrelated to correctness: theme.signals
    .themeChanged is a persistent module-level signal, and a tree whose
    widget hasn't actually been destroyed yet (Qt's own deferred-deletion
    timing, not a bug in this codebase) keeps costing this function on
    every future theme switch for as long as it lingers -- a recursive
    whole-model walk turned that from negligible into something that
    visibly compounded across a long test run (or, in principle, a long
    real session with several mapping reloads)."""
    model = view.model()
    if model is None:
        return
    viewport_bottom = view.viewport().rect().bottom()
    index = view.indexAt(view.viewport().rect().topLeft())
    while index.isValid() and view.visualRect(index).top() <= viewport_bottom:
        if model.hasChildren(index):
            was_expanded = view.isExpanded(index)
            view.setExpanded(index, not was_expanded)
            view.setExpanded(index, was_expanded)
        index = view.indexBelow(index)


# A mapping column narrower than this truncates every row ("ch1 N..."); the
# column row scrolls sideways instead (see splitter_utils.scrollable_columns).
MAPPING_COLUMN_MIN_WIDTH = 220

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.preferences_path = default_preferences_path()
        self.preferences = PluginPreferences.load(self.preferences_path)
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, self.preferences.theme)
            # Follow the OS light/dark switch live while in "system" mode.
            application.styleHints().colorSchemeChanged.connect(self._on_os_color_scheme_changed)
        self.setWindowTitle("DJ MIDI Studio")
        self.resize(self._default_window_size())
        # The absolute minimum stays intentionally tiny (v0.47.7: the window
        # must be draggable smaller than the controller-selector content
        # width); the *default* is what issue #19 was about — 1100x700 clipped
        # panels in both dimensions on macOS.
        self.setMinimumSize(320, 240)
        self.setStatusBar(QStatusBar())
        self.setAutoFillBackground(True)

        self.config: MidiConfig | None = None
        self.current_path: Path | None = None
        self.software_id = "serato"
        catalog.discover_plugins(trust_external=self.preferences.trust_external_plugins)
        software.discover_plugins(trust_external=self.preferences.trust_external_plugins)
        # Controller profiles the user installed from Controller Setup
        # (issue #175): JSON files in their DJ MIDI Studio folder.
        loaded, failed = load_user_profiles(user_paths.controllers_dir())
        if loaded:
            _LOGGER.info("Loaded %d installed controller profile(s): %s", len(loaded), ", ".join(loaded))
        for path, reason in failed.items():
            _LOGGER.warning("Skipped controller profile %s: %s", path, reason)
        # The user's visible folder (issue #175 phase 3); sync sets live there
        # as one file per controller, moved out of preferences.json once.
        user_paths.ensure_workspace()
        self.preferences.controller_sync_sets = sync_store.adopt_sync_sets(
            user_paths.sync_dir(), list(self.preferences.controller_sync_sets)
        )
        # "Show all controllers" (View menu) bypasses the per-controller
        # Preferences enablement so the mapping tabs list every registered
        # controller again; the real state is restored from QSettings in
        # _restore_user_layout once the menu action exists.
        self._show_all_controllers = False
        self._apply_plugin_preferences()
        self._last_save_plan = None
        self._diff_dialog: MappingDiffDialog | None = None
        self.node_to_item: dict[int, object] = {}
        self.channel_proxies: list[QSortFilterProxyModel] = []
        self._channel_model_owner: dict[int, tuple[QTreeView, QSortFilterProxyModel]] = {}
        self._deck_tree_views: list[QTreeView] = []
        self._controller_tree_views: list[QTreeView] = []
        # One connection, bound to self (MainWindow's own app-session
        # lifetime), rather than one theme_signals.themeChanged connection
        # per tree -- see _restyle_mapping_trees's docstring for why a
        # per-tree closure leaked.
        theme_signals.themeChanged.connect(self._restyle_mapping_trees)
        self._pair_splitters: list[QSplitter] = []
        self._pair_ratio_by_id: dict[int, float] = {}
        self._last_controller_detection: tuple[str, ...] = ()
        self._performance_mode = False
        self._performance_saved_ratios: dict[int, float] | None = None

        self.undo_stack = QUndoStack(self)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter by channel, control, event type, function, deck, slot...")
        self.search_box.textChanged.connect(self._on_search_text_changed)

        # Each representation is a row of columns (one per channel / one per
        # deck) instead of a single tree nesting that level, so the channel or
        # deck a row belongs to is implicit in which column it's in.
        self.channel_columns_container = QWidget()
        channel_layout = QVBoxLayout(self.channel_columns_container)
        channel_layout.setContentsMargins(0, 0, 0, 0)
        channel_layout.addWidget(self.search_box)
        self.channel_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._channel_columns_scroll = scrollable_columns(self.channel_splitter)
        channel_layout.addWidget(self._channel_columns_scroll)

        self.layout_view = ControllerLayoutView()
        self.layout_view.cellActivated.connect(lambda key: self._on_layout_cell_activated(key, "channel"))

        self.deck_columns_container = QWidget()
        deck_columns_layout = QVBoxLayout(self.deck_columns_container)
        deck_columns_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._deck_columns_scroll = scrollable_columns(self.deck_splitter)
        deck_columns_layout.addWidget(self._deck_columns_scroll)

        self.deck_layout_view = ControllerLayoutView(show_deck_filter=True)
        self.deck_layout_view.cellActivated.connect(lambda key: self._on_layout_cell_activated(key, "deck"))

        self.controller_columns_container = QWidget()
        controller_columns_layout = QVBoxLayout(self.controller_columns_container)
        controller_columns_layout.setContentsMargins(0, 0, 0, 0)
        self.controller_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._controller_columns_scroll = scrollable_columns(self.controller_splitter)
        controller_columns_layout.addWidget(self._controller_columns_scroll)

        self.controller_layout_view = ControllerLayoutView()
        self.controller_layout_view.cellActivated.connect(lambda key: self._on_layout_cell_activated(key, "controller"))

        # Each representation pairs the columns (text, precise) with a schematic
        # layout (visual, at-a-glance) of the same underlying data.
        channel_pair = QSplitter(Qt.Orientation.Vertical)
        channel_pair.addWidget(self.channel_columns_container)
        channel_pair.addWidget(self.layout_view)
        channel_pair.setChildrenCollapsible(False)
        channel_pair.setStretchFactor(0, 1)
        channel_pair.setStretchFactor(1, 1)

        deck_pair = QSplitter(Qt.Orientation.Vertical)
        deck_pair.addWidget(self.deck_columns_container)
        deck_pair.addWidget(self.deck_layout_view)
        deck_pair.setChildrenCollapsible(False)
        deck_pair.setStretchFactor(0, 1)
        deck_pair.setStretchFactor(1, 1)

        controller_pair = QSplitter(Qt.Orientation.Vertical)
        controller_pair.addWidget(self.controller_columns_container)
        controller_pair.addWidget(self.controller_layout_view)
        controller_pair.setChildrenCollapsible(False)
        controller_pair.setStretchFactor(0, 1)
        controller_pair.setStretchFactor(1, 1)

        self._pair_splitters = [channel_pair, deck_pair, controller_pair]
        for splitter in self._pair_splitters:
            self._pair_ratio_by_id[id(splitter)] = 0.5
            splitter.splitterMoved.connect(lambda *_args, s=splitter: self._remember_pair_ratio(s))

        self.controller_image_view = ControllerImageView()

        self.live_monitor_view = LiveMonitorView(on_event=self._on_live_midi_event)
        self.live_monitor_view.syncRequested.connect(self._on_sync_controllers)

        self.controller_setup_view = ControllerSetupView()
        self.controller_setup_view.set_default_file(self.preferences.controller_setup_default_file)
        self.controller_setup_view.controllerApplied.connect(self._on_controller_applied)
        self.controller_setup_view.openMappingRequested.connect(self._on_open_mapping_requested)
        self.controller_setup_view.syncSetSaveRequested.connect(self._on_sync_set_save_requested)

        self.midi_routing_view = MidiRoutingView()
        self.midi_routing_view.set_routing_enabled(self.preferences.routing_enabled)
        self.midi_clock_view = MidiClockView(self.midi_routing_view.take_clock_panel())
        self.metronome_view = MetronomeView(
            all_rows_provider=self.controller_setup_view.session_rows,
            selected_rows_provider=self.controller_setup_view.selected_session_rows,
            session_name_provider=self.controller_setup_view.session_controller_name,
        )
        # Controller Emulator instances are dynamic (phase 2 of issue #9's
        # roadmap: several may be open at once, each bound to its own
        # controller) -- see _create_emulator_instance, not a fixed
        # single-instance tool dock like monitor/routing/clock/metronome.
        self._emulator_docks: dict[str, QDockWidget] = {}

        self.introduction_view = IntroductionView()
        self.live_monitor_view.portNamesChanged.connect(
            self.introduction_view.refresh_midi_availability
        )
        self.live_monitor_view.portNamesChanged.connect(self._on_midi_ports_changed)
        self.introduction_view.refresh_midi_availability(
            self.live_monitor_view.input_port_names()
        )
        self.introduction_view.drillDownRequested.connect(self._on_intro_drilldown_requested)
        self.introduction_view.toolRequested.connect(self._show_tool_dock)

        # Music Library (issue #133/#132): a separate domain from mappings --
        # the DJ's own collection. Opens its index lazily on first show.
        self.music_library_view = MusicLibraryView()

        self.left_tabs = QTabWidget()
        self._tab_indexes = {
            "intro": self.left_tabs.addTab(self.introduction_view, "Dashboard"),
            "setup": self.left_tabs.addTab(self.controller_setup_view, "Controller Setup"),
            "images": self.left_tabs.addTab(self.controller_image_view, "Controller Images"),
            "channel": self.left_tabs.addTab(channel_pair, "By Channel"),
            "deck": self.left_tabs.addTab(deck_pair, "By Deck"),
            "controller": self.left_tabs.addTab(controller_pair, "By Controller"),
            "library": self.left_tabs.addTab(self.music_library_view, "Music Library"),
        }
        self.edit_panel = EditPanel(self.undo_stack, self._on_command_applied, self._on_group_edit_applied)

        self.issues_table = QTableWidget(0, 3)
        self.issues_table.setHorizontalHeaderLabels(["Severity", "Message", "Location"])
        self.issues_table.horizontalHeader().setStretchLastSection(True)
        self.issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Reverse search (issue #185): "which control triggers function X?".
        # Lives in the editing column so it's there on all three mapping tabs
        # without adding a field to each one.
        self.function_search_view = FunctionSearchView()
        self.function_search_view.resultSelected.connect(self._on_function_result_selected)

        # The edit panel's real minimum height (~850 px) exceeds what this
        # column gets at the default 1100x700, so it scrolls instead of
        # overlapping its own group boxes (issue #19's rule) -- more so now
        # that Find function shares the column.
        self._edit_panel_scroll = AutoSizeScrollArea()
        self._edit_panel_scroll.setWidgetResizable(True)
        self._edit_panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._edit_panel_scroll.setWidget(self.edit_panel)

        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.addWidget(self.function_search_view)
        self._right_splitter.addWidget(self._edit_panel_scroll)
        self._right_splitter.addWidget(self.issues_table)
        self._right_splitter.setStretchFactor(0, 0)
        self._right_splitter.setStretchFactor(1, 2)
        self._right_splitter.setStretchFactor(2, 1)
        # Search a short strip, the edit panel most of the column, the issue
        # table a strip (Qt rescales these to the real height).
        self._right_splitter.setSizes([150, 600, 150])

        # The edit / validation column only makes sense on the tree tabs; on
        # Dashboard / Controller Setup / Controller Images there is no node to
        # edit, so hide it there and give those tabs the full width.
        self._editing_tab_indexes = {
            self._tab_indexes[key] for key in ("channel", "deck", "controller")
        }
        self.left_tabs.currentChanged.connect(self._on_left_tab_changed)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.left_tabs)
        main_splitter.addWidget(self._right_splitter)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        self.setCentralWidget(main_splitter)
        self._on_left_tab_changed(self.left_tabs.currentIndex())
        main_splitter.setAutoFillBackground(True)
        self._tool_docks = self._create_tool_docks()

        settings = self._layout_settings()
        self._recent_mappings: list[str] = (
            [str(entry) for entry in (settings.value(_RECENT_SETTINGS_KEY, [], type=list) or [])]
            if settings is not None
            else []
        )
        self._build_menu()
        self.introduction_view.fileActionRequested.connect(self._on_dashboard_file_action)
        self._refresh_file_actions()
        self.helpful_notes_dialog = HelpfulNotesDialog(self)
        self.helpful_notes_dialog.closedPersistently.connect(self._persist_helpful_notes_closed)
        self.helpful_notes_dialog.closedForSession.connect(self._allow_helpful_notes_next_start)
        self._restore_user_layout()
        self.controller_setup_view.draftFileChanged.connect(self._remember_draft)
        self._prepare_reopen_last_files()
        if self._layout_settings() is not None:
            # Real app only, like reopening files: tests never touch MIDI here.
            QTimer.singleShot(_STARTUP_SYNC_DELAY_MS, self._start_controller_sync)
        self._update_checker = UpdateChecker(self)
        self._update_checker.finished.connect(self._on_update_check_finished)
        self._update_label = QLabel()
        self._update_label.setTextFormat(Qt.TextFormat.RichText)
        self._update_label.setOpenExternalLinks(True)
        self._update_label.hide()
        self.statusBar().addPermanentWidget(self._update_label)
        if self._layout_settings() is not None and self.preferences.check_for_updates:
            # Real app only, like Sync at launch: tests never touch the network.
            QTimer.singleShot(_STARTUP_UPDATE_CHECK_DELAY_MS, self._check_for_updates_at_startup)
        QTimer.singleShot(0, self._initialize_pair_splitters)
        QTimer.singleShot(0, self._show_helpful_notes_if_enabled)
        self.introduction_view.set_loaded_config_info(None)

    @staticmethod
    def _layout_settings() -> QSettings | None:
        """Return persistent window settings only for the real application.

        Tests and documentation capture helpers construct windows directly;
        avoiding persistence there keeps those isolated from a user's saved
        desktop arrangement.
        """
        if QCoreApplication.applicationName() != "DJ MIDI Studio":
            return None
        return QSettings("DJ MIDI Studio", "DJ MIDI Studio")

    # Preferred first-run size; scaled down to fit smaller screens.
    _PREFERRED_WINDOW_SIZE = QSize(1280, 820)
    _MIN_DEFAULT_WINDOW_SIZE = QSize(1100, 720)

    def _default_window_size(self) -> QSize:
        """First-run window size, derived from the available screen area.

        The old hardcoded ``1100x700`` clipped panels in both dimensions on
        macOS (issue #19). Use a larger preferred size, but never exceed the
        usable screen so the title bar and edges stay reachable; on a genuinely
        small display fall back to the minimum sensible default.
        """
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return QSize(self._PREFERRED_WINDOW_SIZE)
        available = screen.availableGeometry()
        width = min(self._PREFERRED_WINDOW_SIZE.width(), int(available.width() * 0.92))
        height = min(self._PREFERRED_WINDOW_SIZE.height(), int(available.height() * 0.90))
        return QSize(
            max(self._MIN_DEFAULT_WINDOW_SIZE.width(), width),
            max(self._MIN_DEFAULT_WINDOW_SIZE.height(), height),
        )

    def _center_on_screen(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        # Never let the top of the frame slide under the menu bar / off screen.
        frame.moveTop(max(available.top(), frame.top()))
        frame.moveLeft(max(available.left(), frame.left()))
        self.move(frame.topLeft())

    def _restore_emulator_instances(self, settings: QSettings) -> None:
        """Reopens one Controller Emulator instance per controller that had
        one open at last shutdown (see closeEvent). Must run before
        restoreState() below: Qt's dock-state serialization can only
        reposition a dock that already exists by objectName, so a
        dynamically created instance has to exist first -- its objectName
        is a fresh random id each session regardless (see
        _create_emulator_instance), so exact prior geometry/floating state
        isn't restored, only which controllers were open."""
        saved = settings.value("emulator/open_controllers", [])
        if isinstance(saved, str):
            # QSettings collapses a single-element string list back to a
            # bare string on some platforms/backends.
            saved = [saved]
        for controller in saved:
            if controller:
                self._create_emulator_instance(controller)

    def _restore_user_layout(self) -> None:
        settings = self._layout_settings()
        if settings is None:
            self._center_on_screen()
            return
        geometry = settings.value("window/geometry")
        state = settings.value("window/state")
        self._restore_emulator_instances(settings)
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self._center_on_screen()
        if state:
            self.restoreState(state, 1)
        if settings.value("view/show_all_controllers", False, type=bool):
            # setChecked fires _on_show_all_controllers_toggled, which flips the
            # flag, re-applies the registry filter, and refreshes the combos.
            self._show_all_controllers_action.setChecked(True)
        self.midi_routing_view.restore_state(settings)
        self.metronome_view.restore_state(settings)

    def changeEvent(self, event: QEvent) -> None:
        """Refresh the backing store after native macOS window transitions."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._refresh_window_surface)

    def _refresh_window_surface(self) -> None:
        """Repaint the window after macOS has finished a native transition."""
        if self.isWindow() and not self.isVisible():
            return
        widgets = [self, self.centralWidget(), *self._tool_docks.values()]
        for widget in widgets:
            if widget is not None:
                widget.setUpdatesEnabled(False)
                widget.setUpdatesEnabled(True)
                widget.update()
        self.repaint()

    def _on_midi_ports_changed(self, port_names: list[str]) -> None:
        """Apply a high-confidence controller plugin suggestion to all views."""
        signature = tuple(sorted(port_names))
        if signature == self._last_controller_detection:
            return
        self._last_controller_detection = signature
        detection = detect_controller_ports(port_names)
        best = detection.best
        if best is None:
            return
        if detection.needs_confirmation and self.preferences.detection_policy == "ask":
            answer = QMessageBox.question(
                self,
                "MIDI controller detected",
                f"Enable '{best.name}'?\n{best.score}% confidence — {best.reasons[0]}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        elif detection.needs_confirmation:
            self.statusBar().showMessage(
                f"Detected controller suggestion: {best.name} ({best.score}% confidence)."
            )
            return
        self._apply_detected_controller(best.name, best.score, best.reasons[0])

    def _apply_detected_controller(self, name: str, score: int, reason: str) -> None:
        selected = (
            self.layout_view.set_controller(name)
            and self.deck_layout_view.set_controller(name)
            and self.controller_layout_view.set_controller(name)
            and self.controller_image_view.set_controller(name)
            and self.introduction_view.set_controller(name)
        )
        if selected:
            self.statusBar().showMessage(f"Controller enabled: {name} ({score}% — {reason})")

    def _initialize_pair_splitters(self) -> None:
        for splitter in self._pair_splitters:
            self._set_pair_ratio(splitter, 0.5)

    def _remember_pair_ratio(self, splitter: QSplitter) -> None:
        sizes = splitter.sizes()
        if len(sizes) < 2:
            return
        total = sizes[0] + sizes[1]
        if total <= 0:
            return
        ratio = sizes[0] / total
        # Keep both panes visible even after repeated window resizes.
        self._pair_ratio_by_id[id(splitter)] = min(max(ratio, 0.1), 0.9)

    def _set_pair_ratio(self, splitter: QSplitter, ratio: float) -> None:
        sizes = splitter.sizes()
        total = sum(sizes)
        if total <= 0:
            total = splitter.height()
        if total <= 0:
            return
        top = max(1, int(total * ratio))
        bottom = max(1, total - top)
        splitter.setSizes([top, bottom])

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for splitter in self._pair_splitters:
            ratio = self._pair_ratio_by_id.get(id(splitter), 0.5)
            self._set_pair_ratio(splitter, ratio)

    def _build_menu(self) -> None:
        # On macOS, Qt moves the menu bar into the system-wide bar at the top of
        # the screen by default, which is easy to miss; keep it in-window instead.
        self.menuBar().setNativeMenuBar(False)
        # Organized by object (issue #175): the DJ software mapping first,
        # then the controller profile being built, then imports/exports that
        # used to live only behind buttons in their tabs.
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open Mapping...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)
        self._recent_menu = file_menu.addMenu("Open &Recent Mapping")

        save_action = QAction("&Save Mapping", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Mapping &As...", self)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        self._rollback_action = QAction("Restore &Previous Version...", self)
        self._rollback_action.setToolTip("Replace the mapping with the version saved before its last save.")
        self._rollback_action.setEnabled(False)
        self._rollback_action.triggered.connect(self._on_rollback_last_save)
        file_menu.addAction(self._rollback_action)

        # Issue #189: what changed, trigger by trigger, instead of a raw XML diff.
        self._compare_action = QAction("Co&mpare Mapping With...", self)
        self._compare_action.setToolTip("List what another mapping file does differently from the one open.")
        self._compare_action.setEnabled(False)
        self._compare_action.triggered.connect(self._on_compare_with_file)
        file_menu.addAction(self._compare_action)
        self._compare_backup_action = QAction("Compare With Previous &Version", self)
        self._compare_backup_action.setToolTip("List what changed since the version saved before the last save.")
        self._compare_backup_action.setEnabled(False)
        self._compare_backup_action.triggered.connect(self._on_compare_with_backup)
        file_menu.addAction(self._compare_backup_action)

        self._reveal_action = QAction(_REVEAL_LABEL, self)
        self._reveal_action.setEnabled(False)
        self._reveal_action.triggered.connect(self._on_reveal_mapping)
        file_menu.addAction(self._reveal_action)

        file_menu.addSeparator()
        profile_menu = file_menu.addMenu("&Controller Profile")
        setup = self.controller_setup_view
        for label, handler in (
            ("New Draft", setup._on_new_session_clicked),
            ("Open Draft...", setup._on_load_session_clicked),
            ("Save Draft...", setup._on_save_session_clicked),
            ("Learn Triggers from a Mapping...", setup._on_import_xml_clicked),
            ("Install Profile", setup._on_apply_clicked),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, h=handler: self._run_in_tab("setup", h))
            profile_menu.addAction(action)
        installed_action = QAction("Show Installed Profiles", self)
        installed_action.triggered.connect(self._on_reveal_installed_profiles)
        profile_menu.addAction(installed_action)

        library = self.music_library_view
        import_menu = file_menu.addMenu("&Import")
        for label, handler in (
            ("Serato Crates into the Music Library...", library._on_import_serato_clicked),
            ("Traktor Playlists into the Music Library...", library._on_import_traktor_clicked),
            ("Rekordbox USB Export into the Music Library...", library._on_import_rekordbox_clicked),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, h=handler: self._run_in_tab("library", h))
            import_menu.addAction(action)
        export_menu = file_menu.addMenu("&Export")
        for label, handler in (
            ("Selected Playlist as a Serato Crate...", library._on_export_serato_clicked),
            ("Selected Playlist as a Traktor Playlist...", library._on_export_traktor_clicked),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, h=handler: self._run_in_tab("library", h))
            export_menu.addAction(action)
        log_action = QAction("Live Monitor Log...", self)
        log_action.triggered.connect(self.live_monitor_view._save_log)
        export_menu.addAction(log_action)
        export_menu.addSeparator()
        self._cheat_sheet_action = QAction("Cheat Sheet (PDF)...", self)
        self._cheat_sheet_action.setToolTip(
            "Print each controller's photo with the function the loaded mapping binds to every control"
        )
        self._cheat_sheet_action.setEnabled(False)
        self._cheat_sheet_action.triggered.connect(lambda _checked=False: self._on_export_cheat_sheet())
        export_menu.addAction(self._cheat_sheet_action)

        file_menu.addSeparator()
        backup_action = QAction("&Back Up Workspace...", self)
        backup_action.setToolTip("Save your profiles, sync sets, drafts, preferences (and optionally the library index) in one zip.")
        backup_action.triggered.connect(self._on_backup_workspace)
        file_menu.addAction(backup_action)
        restore_action = QAction("Restore &Workspace...", self)
        restore_action.setToolTip("Restore a workspace backup, after confirming what it overwrites.")
        restore_action.triggered.connect(self._on_restore_workspace)
        file_menu.addAction(restore_action)
        self._rebuild_recent_menu()

        edit_menu = self.menuBar().addMenu("&Edit")

        undo_action = self.undo_stack.createUndoAction(self, "&Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)

        redo_action = self.undo_stack.createRedoAction(self, "&Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        validate_action = QAction("&Validate", self)
        validate_action.triggered.connect(self._on_validate)
        edit_menu.addAction(validate_action)

        view_menu = self.menuBar().addMenu("&View")
        helpful_notes_action = QAction("Helpful Notes...", self)
        helpful_notes_action.triggered.connect(self._show_helpful_notes)
        view_menu.addAction(helpful_notes_action)
        view_menu.addSeparator()
        for key in ("monitor", "routing", "clock", "metronome"):
            dock = self._tool_docks[key]
            view_menu.addAction(dock.toggleViewAction())
        self._new_emulator_action = QAction("New Controller Emulator…", self)
        self._new_emulator_action.setToolTip(
            "Open another Controller Emulator window -- several may be open at "
            "once, each bound to its own controller"
        )
        self._new_emulator_action.triggered.connect(lambda: self._create_emulator_instance())
        view_menu.addAction(self._new_emulator_action)
        view_menu.addSeparator()
        self._show_all_controllers_action = QAction("Show all controllers", self, checkable=True)
        self._show_all_controllers_action.setChecked(self._show_all_controllers)
        self._show_all_controllers_action.setToolTip(
            "Ignore the per-controller Preferences enablement and list every registered controller"
        )
        self._show_all_controllers_action.toggled.connect(self._on_show_all_controllers_toggled)
        view_menu.addAction(self._show_all_controllers_action)

        view_menu.addSeparator()
        self._performance_mode_action = QAction("Performance Mode", self, checkable=True)
        self._performance_mode_action.setToolTip(
            "Hide the mapping tree and enlarge the schematic layout for on-stage use "
            "(session-only, not remembered across restarts)"
        )
        self._performance_mode_action.toggled.connect(self._on_performance_mode_toggled)
        view_menu.addAction(self._performance_mode_action)

        # Preferences moved out of the menu bar (issue #137) into an
        # always-visible corner icon instead of a menu someone has to open
        # first to discover it. Kept as an instance attribute -- unlike
        # addWidget() on a layout, setCornerWidget() doesn't reliably keep
        # PySide6's Python-side wrapper alive on its own, so a purely local
        # variable here gets garbage-collected out from under the C++ widget.
        self._preferences_button = QPushButton("⚙")
        self._preferences_button.setFixedSize(28, 28)
        self._preferences_button.setProperty("compact", True)
        self._preferences_button.setToolTip("Preferences...")
        self._preferences_button.clicked.connect(lambda: self._on_preferences())
        # One-click controller initialization (Sync), beside the gear so it's
        # reachable from every tab; Live Monitor carries the same action.
        self._sync_button = QPushButton("⟳ Sync")
        self._sync_button.setFixedHeight(28)
        self._sync_button.setToolTip(
            "Sync controllers: send each connected controller its recorded initialization set"
        )
        self._sync_button.clicked.connect(self._on_sync_controllers)
        # Active sync scene (issue #188): which named set ⟳ Sync, launch and
        # plug-in sync send, and which scene ● Rec records into.
        self._sync_scene_combo = QComboBox()
        self._sync_scene_combo.setFixedHeight(28)
        self._sync_scene_combo.setMaximumWidth(140)
        self._sync_scene_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._sync_scene_combo.setToolTip(
            "Sync scene: ⟳ Sync, launch and plug-in sync send each controller its set for this scene "
            "(or its Default set when it has none); ● Rec records into it"
        )
        self._refresh_sync_scene_combo()
        self._sync_scene_combo.activated.connect(self._on_sync_scene_activated)
        # Record the controllers' setup in one click: listen to every MIDI
        # input while checked, save one sync set per controller on release.
        self._record_button = QPushButton("● Rec")
        self._record_button.setCheckable(True)
        self._record_button.setFixedHeight(28)
        self._record_button.setToolTip(
            "Record controller setup: press the controls to send at initialization, then click "
            "again to save them as each controller's sync set (played by ⟳ Sync and at launch)"
        )
        self._record_button.toggled.connect(self._on_record_toggled)
        self._record_monitor = MidiMonitor()
        self._record_events: list[MidiEvent] = []
        # Sync-on-plug-in (issue #183): started by _start_controller_sync in
        # the real app only; _poll_plugged_controllers stays callable by tests.
        self._plug_in_tracker = PlugInSyncTracker()
        self._plug_in_timer = QTimer(self)
        self._plug_in_timer.setInterval(_PLUG_IN_POLL_MS)
        self._plug_in_timer.timeout.connect(self._poll_plugged_controllers)
        self._record_timer = QTimer(self)
        self._record_timer.setInterval(20)
        self._record_timer.timeout.connect(self._poll_recording)
        # Same keep-alive concern as the gear button above: hold the container.
        self._menu_corner = QWidget()
        corner_layout = QHBoxLayout(self._menu_corner)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(4)
        corner_layout.addWidget(self._record_button)
        corner_layout.addWidget(self._sync_scene_combo)
        corner_layout.addWidget(self._sync_button)
        corner_layout.addWidget(self._preferences_button)
        self.menuBar().setCornerWidget(self._menu_corner, Qt.Corner.TopRightCorner)

        help_menu = self.menuBar().addMenu("&Help")
        documentation_menu = help_menu.addMenu("Project Documentation")
        for title, relative_path in _LOCAL_HELP_DOCUMENTS:
            action = QAction(title, self)
            action.triggered.connect(
                lambda checked=False, p=relative_path: self._open_local_help(p)
            )
            documentation_menu.addAction(action)

        controller_menu = help_menu.addMenu("Controller References")
        for title, relative_path in _LOCAL_CONTROLLER_DOCUMENTS:
            action = QAction(title, self)
            action.triggered.connect(
                lambda checked=False, p=relative_path: self._open_local_help(p)
            )
            controller_menu.addAction(action)

        help_menu.addSeparator()
        online_menu = help_menu.addMenu("Official and External References")
        for title, url in _REFERENCE_LINKS:
            action = QAction(title, self)
            action.triggered.connect(lambda checked=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            online_menu.addAction(action)

        help_menu.addSeparator()
        self._check_updates_action = QAction("Check for &Updates...", self)
        self._check_updates_action.setToolTip("Ask GitHub whether a newer DJ MIDI Studio release exists.")
        self._check_updates_action.triggered.connect(self._on_check_for_updates)
        help_menu.addAction(self._check_updates_action)

    def _show_helpful_notes(self) -> None:
        self.helpful_notes_dialog.show()
        self.helpful_notes_dialog.raise_()
        self.helpful_notes_dialog.activateWindow()

    def _show_helpful_notes_if_enabled(self) -> None:
        settings = self._layout_settings()
        if settings is not None and not bool(settings.value("ui/helpful_notes_closed", False)):
            self._show_helpful_notes()

    def _persist_helpful_notes_closed(self) -> None:
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue("ui/helpful_notes_closed", True)
            settings.sync()

    def _allow_helpful_notes_next_start(self) -> None:
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue("ui/helpful_notes_closed", False)
            settings.sync()

    def _create_tool_docks(self) -> dict[str, QDockWidget]:
        definitions = {
            "monitor": ("Live Monitor", self.live_monitor_view),
            "routing": ("MIDI Routing", self.midi_routing_view),
            "clock": ("MIDI Clock", self.midi_clock_view),
            "metronome": ("Metronome", self.metronome_view),
        }
        docks: dict[str, QDockWidget] = {}
        for key, (title, widget) in definitions.items():
            dock = QDockWidget(title, self)
            dock.setObjectName(f"{key}Dock")
            dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetClosable
                | QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            )
            dock.setWidget(widget)
            dock.setTitleBarWidget(self._build_dock_title_bar(key, title, dock))
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            dock.hide()
            docks[key] = dock
        return docks

    def _build_dock_title_bar(self, key: str, title: str, dock: QDockWidget) -> QWidget:
        """A title bar with an explicit, clearly-labeled Dock/Undock button.

        QDockWidget's native float button is a tiny, easy-to-miss icon; this
        replaces it with a text button so attaching/detaching is discoverable.
        Dragging this widget still moves/undocks the dock (Qt uses the title
        bar widget's geometry as the drag handle regardless of its contents).
        """
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 4, 4, 4)
        bar_layout.setSpacing(3)
        label = QLabel(title)
        label.setStyleSheet("QLabel { font-weight: bold; }")
        bar_layout.addWidget(label)
        bar_layout.addStretch(1)

        for button in self._build_window_control_buttons(dock):
            bar_layout.addWidget(button)

        dock_button = QPushButton()
        dock_button.setFixedHeight(28)
        dock_button.setMinimumWidth(64)
        dock_button.clicked.connect(lambda: self._set_tool_dock_floating(key, not dock.isFloating()))
        dock.topLevelChanged.connect(lambda floating, button=dock_button: self._update_dock_button(button, floating))
        self._update_dock_button(dock_button, dock.isFloating())
        bar_layout.addWidget(dock_button)

        close_button = QPushButton()
        close_button.setFixedSize(28, 28)
        close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close_button.setToolTip("Close")
        close_button.clicked.connect(dock.close)
        bar_layout.addWidget(close_button)
        return bar

    def _build_window_control_buttons(self, dock: QDockWidget) -> list[QPushButton]:
        """A single compact "Window" menu button, added to every dock's title
        bar (issue #137) alongside the existing Dock/Undock and Close
        buttons: Maximize/Restore, Reduce/Expand, and snap-to-side actions.

        An earlier version of this added one 28px button per action (6 in
        total), which regressed test_tool_dock_geometry_never_extends_past_
        the_window_edge / the emulator equivalent -- at a narrow docked
        width, the title bar's own minimum size drives the dock's minimum
        width, and six extra buttons pushed that past the window edge. One
        menu button keeps the same footprint as the existing Close button.

        Maximize floats the dock (if docked) and showMaximized()s it, like
        any top-level window; Restore returns it to its prior floating
        geometry, not to wherever it was docked before (that's what the
        existing Dock/Undock button already does). Reduce collapses the dock
        to just its title-bar strip (content hidden, a fixed maximum height
        applied) rather than hiding it outright, unlike Close; triggering it
        again re-expands. Both are confirmed maintainer decisions, not a
        guess -- see issue #137.
        """
        # A text glyph, not QStyle.SP_TitleBarMenuButton: on macOS that
        # standard icon is the Qt logo (issue #19).
        button = QPushButton("☰")
        button.setFixedSize(22, 22)
        button.setProperty("compact", True)
        button.setToolTip("Window")

        menu = QMenu(button)
        reduce_action = QAction("Reduce to title bar", button)
        maximize_action = QAction("Maximize", button)
        menu.addAction(reduce_action)
        menu.addAction(maximize_action)
        menu.addSeparator()
        snap_specs = [
            ("Snap left", Qt.DockWidgetArea.LeftDockWidgetArea),
            ("Snap right", Qt.DockWidgetArea.RightDockWidgetArea),
            ("Snap to top", Qt.DockWidgetArea.TopDockWidgetArea),
            ("Snap to bottom", Qt.DockWidgetArea.BottomDockWidgetArea),
        ]
        for label, area in snap_specs:
            snap_action = QAction(label, button)
            snap_action.triggered.connect(lambda checked=False, d=dock, a=area: self._snap_dock_to_area(d, a))
            menu.addAction(snap_action)
        button.setMenu(menu)

        self._init_dock_window_state(dock, reduce_action, maximize_action)
        reduce_action.triggered.connect(lambda: self._toggle_dock_reduced(dock))
        maximize_action.triggered.connect(lambda: self._toggle_dock_maximized(dock))

        return [button]

    @staticmethod
    def _init_dock_window_state(dock: QDockWidget, reduce_action: QAction, maximize_action: QAction) -> None:
        dock._dj_reduced = False
        dock._dj_maximized = False
        dock._dj_premax_geometry = None
        dock._dj_reduce_action = reduce_action
        dock._dj_maximize_action = maximize_action

    def _toggle_dock_reduced(self, dock: QDockWidget) -> None:
        widget = dock.widget()
        if widget is None:
            return
        if not dock._dj_reduced:
            widget.hide()
            title_bar = dock.titleBarWidget()
            dock.setMaximumHeight(title_bar.sizeHint().height() if title_bar is not None else 32)
            dock._dj_reduced = True
            dock._dj_reduce_action.setText("Expand")
        else:
            widget.show()
            dock.setMaximumHeight(16777215)
            dock._dj_reduced = False
            dock._dj_reduce_action.setText("Reduce to title bar")

    def _toggle_dock_maximized(self, dock: QDockWidget) -> None:
        if not dock._dj_maximized:
            if not dock.isFloating():
                dock.setFloating(True)
            dock._dj_premax_geometry = dock.geometry()
            dock.showMaximized()
            dock._dj_maximized = True
            dock._dj_maximize_action.setText("Restore")
        else:
            dock.showNormal()
            if dock._dj_premax_geometry is not None:
                dock.setGeometry(dock._dj_premax_geometry)
            dock._dj_maximized = False
            dock._dj_maximize_action.setText("Maximize")

    def _snap_dock_to_area(self, dock: QDockWidget, area: Qt.DockWidgetArea) -> None:
        if dock._dj_reduced:
            self._toggle_dock_reduced(dock)
        if dock._dj_maximized:
            self._toggle_dock_maximized(dock)
        if dock.isFloating():
            dock.setFloating(False)
        self.addDockWidget(area, dock)
        dock.show()
        dock.raise_()

    @staticmethod
    def _update_dock_button(button: QPushButton, floating: bool) -> None:
        if floating:
            button.setText("Dock")
            button.setToolTip("Attach back into the main window")
        else:
            button.setText("Undock")
            button.setToolTip("Detach into its own window")

    def _show_tool_dock(self, key: str) -> None:
        dock = self._tool_docks.get(key)
        if dock is None:
            return
        dock.show()
        dock.raise_()

    def _create_emulator_instance(self, controller: str | None = None) -> QDockWidget:
        """Opens a new, independent Controller Emulator window (issue #9
        phase 2: unlike the fixed monitor/routing/clock/metronome docks,
        several of these may exist at once, each bound to its own
        controller). The instance id only needs to be unique for the current
        session -- Qt's saveState()/restoreState() only need a stable
        objectName to reposition a dock *within* a session; reopening the
        same set of controllers across a restart is handled separately by
        replaying _create_emulator_instance() calls in _restore_user_layout,
        not by objectName matching a prior session's random id."""
        instance_id = f"emulator_{uuid4().hex[:8]}"
        view = ControllerEmulatorView(config_provider=lambda: self.config, initial_controller=controller)
        dock = QDockWidget("Controller Emulator", self)
        dock.setObjectName(f"{instance_id}Dock")
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        dock.setWidget(view)
        dock.setTitleBarWidget(self._build_emulator_dock_title_bar(instance_id, "Controller Emulator", dock))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._emulator_docks[instance_id] = dock
        dock.show()
        dock.raise_()
        return dock

    def _build_emulator_dock_title_bar(self, instance_id: str, title: str, dock: QDockWidget) -> QWidget:
        """Same look as _build_dock_title_bar, but wired to a dynamically
        created instance: Dock/Undock toggles this specific dock directly
        (no _tool_docks lookup, since this dock isn't in that dict), and
        Close actually tears the instance down (_close_emulator_instance)
        instead of just hiding a permanent singleton widget."""
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 4, 4, 4)
        bar_layout.setSpacing(3)
        label = QLabel(title)
        label.setStyleSheet("QLabel { font-weight: bold; }")
        bar_layout.addWidget(label)
        bar_layout.addStretch(1)

        for button in self._build_window_control_buttons(dock):
            bar_layout.addWidget(button)

        dock_button = QPushButton()
        dock_button.setFixedHeight(28)
        dock_button.setMinimumWidth(64)
        dock_button.clicked.connect(lambda: dock.setFloating(not dock.isFloating()))
        dock.topLevelChanged.connect(lambda floating, button=dock_button: self._update_dock_button(button, floating))
        self._update_dock_button(dock_button, dock.isFloating())
        bar_layout.addWidget(dock_button)

        close_button = QPushButton()
        close_button.setFixedSize(28, 28)
        close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close_button.setToolTip("Close")
        close_button.clicked.connect(lambda: self._close_emulator_instance(instance_id))
        bar_layout.addWidget(close_button)
        return bar

    def _close_emulator_instance(self, instance_id: str) -> None:
        dock = self._emulator_docks.pop(instance_id, None)
        if dock is None:
            return
        self.removeDockWidget(dock)
        dock.deleteLater()

    def _set_tool_dock_floating(self, key: str, floating: bool) -> None:
        """Switch a MIDI tool between the main-window dock and a free window."""
        dock = self._tool_docks.get(key)
        if dock is None or dock.isFloating() == floating:
            return
        dock.setFloating(floating)
        if floating:
            dock.show()
            dock.raise_()

    @staticmethod
    def _resource_root() -> Path:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", Path.cwd()))
        return Path(__file__).resolve().parents[3]

    def _open_local_help(self, relative_path: str) -> None:
        path = self._resource_root() / relative_path
        if not path.exists():
            QMessageBox.warning(self, "Documentation unavailable", str(path))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_os_color_scheme_changed(self, _scheme: object) -> None:
        """Re-apply the stylesheet when the OS flips light/dark, but only while
        the user's theme preference is 'system'."""
        if self.preferences.theme == "system":
            application = QApplication.instance()
            if application is not None:
                apply_theme(application, "system")

    def _on_preferences(self, tab: str | None = None) -> None:
        dialog = PreferencesDialog(self.preferences, self)
        dialog.backupRequested.connect(self._on_backup_workspace)
        # A restore rewrote preferences.json: close without saving, or OK
        # would overwrite it with this session's preferences.
        dialog.restoreRequested.connect(lambda: self._on_restore_workspace() and dialog.reject())
        if tab:
            for index in range(dialog.tabs.count()):
                if dialog.tabs.tabText(index) == tab:
                    dialog.tabs.setCurrentIndex(index)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._save_preferences()
            application = QApplication.instance()
            if application is not None:
                apply_theme(application, self.preferences.theme)
            self._apply_plugin_preferences()
            self._on_controller_applied(self.introduction_view._controller_combo.currentText())
            self.midi_routing_view.set_routing_enabled(self.preferences.routing_enabled)
            self.controller_setup_view.set_default_file(self.preferences.controller_setup_default_file)
            log_path = self.preferences.log_path or current_log_path()
            configure_logging(self.preferences.log_level, log_path)
            if self._layout_settings() is not None:
                self._update_plug_in_watch()
            if self.preferences.auto_start_live_monitor and self.config is not None:
                # Turning the setting on with a mapping already loaded starts
                # monitoring immediately, matching "Enable MIDI routing
                # policies" applying right away above -- no-op if already running.
                self.live_monitor_view.ensure_monitoring_started()
            self._refresh_file_actions()
            self.statusBar().showMessage("Preferences saved")

    def _on_sync_controllers(self) -> list[SyncResult]:
        """Sends each controller its sync set for the active scene."""
        sync_sets = self.preferences.active_sync_sets()
        if not sync_sets:
            recorded = (
                f"No initialization set is recorded for the scene \"{self.preferences.active_sync_scene}\" "
                "and no controller has a Default set."
                if self.preferences.controller_sync_sets
                else "No initialization set is recorded yet."
            )
            QMessageBox.information(
                self,
                "No controller sync set",
                recorded + "\n\n"
                "Click ● Rec, press the controls to send at initialization, then click ■ Stop -- or, in "
                "Controller Setup, start learning, press the controls, then click \"Save as controller sync set\".",
            )
            return []
        results = run_sync(sync_sets, list_output_ports())
        self.statusBar().showMessage(summarize_results(results), 10_000)
        return results

    def _sync_at_startup(self, ports: list[str] | None = None) -> list[SyncResult]:
        """Launch-time Sync: silent when nothing is recorded, status bar only.
        Seeds the plug-in tracker with the same port list, so a controller
        synced here isn't synced again by the first plug-in poll."""
        if ports is None:
            ports = list_output_ports()
        self._plug_in_tracker.seed(ports)
        sync_sets = self.preferences.active_sync_sets()
        if not sync_sets:
            return []
        results = run_sync(sync_sets, ports)
        self.statusBar().showMessage(summarize_results(results), 10_000)
        return results

    def _start_controller_sync(self) -> None:
        """Launch-time entry point (real app only): the Sync at launch, if
        enabled, then watching for controllers being plugged in."""
        if self.preferences.auto_sync_on_startup:
            self._sync_at_startup()
        self._update_plug_in_watch()

    def _update_plug_in_watch(self) -> None:
        """Starts or stops the plug-in poll to match the preference. Starting
        it seeds the tracker with what's connected now (without sending), so
        only controllers plugged in from then on are synced."""
        if not self.preferences.auto_sync_on_plug_in:
            self._plug_in_timer.stop()
            self._plug_in_tracker.reset()
            return
        if self._plug_in_timer.isActive():
            return
        if not self._plug_in_tracker.seeded:
            self._plug_in_tracker.seed(list_output_ports())
        self._plug_in_timer.start()

    def _poll_plugged_controllers(self) -> list[SyncResult]:
        """Sends a sync set once to each controller whose port just appeared."""
        ports = list_output_ports()
        due = self._plug_in_tracker.due(self.preferences.active_sync_sets(), ports)
        if not due:
            return []
        results = run_sync(due, ports)
        self.statusBar().showMessage("Plugged in -- " + summarize_results(results), 10_000)
        return results

    def _check_for_updates_at_startup(self) -> bool:
        """Launch-time update check: at most once per 24 h, silent unless newer."""
        settings = self._layout_settings()
        if settings is None or not self.preferences.check_for_updates:
            return False
        try:
            last_check = float(settings.value(_LAST_UPDATE_CHECK_SETTINGS_KEY, 0) or 0) or None
        except (TypeError, ValueError):
            last_check = None
        if not is_check_due(last_check, datetime.now(UTC).timestamp()):
            return False
        return self._update_checker.start(manual=False)

    def _on_check_for_updates(self) -> None:
        if not self._update_checker.start(manual=True):
            self.statusBar().showMessage("Already checking for updates...", 5_000)
            return
        self.statusBar().showMessage("Checking for updates...")

    def _on_update_check_finished(self, release: ReleaseInfo | None, manual: bool) -> None:
        local = current_version()
        newer = release is not None and is_newer(release.version, local)
        if release is not None:
            # Only a successful check counts toward the daily limit, so an
            # offline launch tries again next time.
            settings = self._layout_settings()
            if settings is not None:
                settings.setValue(_LAST_UPDATE_CHECK_SETTINGS_KEY, datetime.now(UTC).timestamp())
        if manual:
            self.statusBar().clearMessage()
        if newer:
            version = ".".join(map(str, release.version))
            self._update_label.setText(f'<a href="{release.url}">Update available: v{version}</a>')
            self._update_label.setToolTip(f"Open the {release.tag} release page in your browser")
            self._update_label.show()
            self.statusBar().showMessage(f"DJ MIDI Studio v{version} is available (you have v{local}).", 15_000)
        if not manual:
            return
        if release is None:
            QMessageBox.information(
                self,
                "Check for Updates",
                "Couldn't reach GitHub to check for a new version. Check your connection and try again.",
            )
        elif newer:
            answer = QMessageBox.question(
                self,
                "Check for Updates",
                f"DJ MIDI Studio v{'.'.join(map(str, release.version))} is available "
                f"(you have v{local}).\n\nOpen the release page to download it?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(release.url))
        elif local is None:
            QMessageBox.information(
                self,
                "Check for Updates",
                f"The latest release is {release.tag}, but this copy's own version is unknown.",
            )
        else:
            QMessageBox.information(
                self, "Check for Updates", f"You're up to date (v{local}, latest release {release.tag})."
            )

    def _on_record_toggled(self, recording: bool) -> None:
        if recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        self._record_events = []
        opened = []
        for name in list_input_ports():
            try:
                self._record_monitor.open_input(name)
            except Exception as exc:  # noqa: BLE001 - one busy port must not block the others
                _LOGGER.warning("Record: cannot open MIDI input %r: %s", name, exc)
                continue
            opened.append(name)
        if not opened:
            QMessageBox.warning(self, "Cannot record", "No MIDI input could be opened: is a controller connected?")
            self._record_button.blockSignals(True)
            self._record_button.setChecked(False)
            self._record_button.blockSignals(False)
            return
        self._record_button.setText("■ Stop")
        self._record_timer.start()
        _LOGGER.info("Record: listening on %s", opened)
        self.statusBar().showMessage(
            f"Recording on {len(opened)} MIDI input(s): press the controls to send at initialization, "
            "then click ■ Stop"
        )

    def _poll_recording(self) -> None:
        self._record_events.extend(self._record_monitor.poll())

    def _stop_recording(self) -> list[ControllerSyncSet]:
        self._record_timer.stop()
        self._poll_recording()
        self._record_monitor.close_all()
        self._record_button.setText("● Rec")
        scene = self.preferences.active_sync_scene
        sync_sets = [
            sync_set.in_scene(scene)
            for sync_set in sync_sets_from_recording(self._record_events, self._controller_name_for_port)
        ]
        self._record_events = []
        if not sync_sets:
            self.statusBar().showMessage("Recording stopped: no MIDI note/CC received, nothing saved", 10_000)
            return []
        replaced = [
            f"{sync_set.label} ({len(existing.messages)} message(s))"
            for sync_set in sync_sets
            if (existing := self.preferences.sync_set_for(sync_set.controller, scene)) is not None
        ]
        if replaced:
            reply = QMessageBox.question(
                self,
                "Replace sync sets",
                "Replace the sync set(s) already stored for:\n" + "\n".join(replaced),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Recording discarded", 10_000)
                return []
        for sync_set in sync_sets:
            self.preferences.set_sync_set(sync_set)
        self._save_preferences()
        self.statusBar().showMessage(
            "Sync set(s) saved: "
            + ", ".join(f"{sync_set.label} ({len(sync_set.messages)} msg)" for sync_set in sync_sets),
            10_000,
        )
        return sync_sets

    @staticmethod
    def _controller_name_for_port(port: str) -> str:
        matches = catalog.detect_controller(port)
        return matches[0].controller.name if matches else ""

    def _on_sync_set_save_requested(self, sync_set: ControllerSyncSet) -> None:
        # Controller Setup records into the active scene, like ● Rec.
        sync_set = sync_set.in_scene(self.preferences.active_sync_scene)
        existing = self.preferences.sync_set_for(sync_set.controller, sync_set.scene)
        if existing is not None:
            reply = QMessageBox.question(
                self,
                "Replace sync set",
                f"Replace the {len(existing.messages)}-message sync set already stored for "
                f"{sync_set.label} with this {len(sync_set.messages)}-message recording?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.preferences.set_sync_set(sync_set)
        self._save_preferences()
        self.statusBar().showMessage(
            f"Sync set saved for {sync_set.label} ({len(sync_set.messages)} message(s))", 10_000
        )

    _NEW_SCENE_DATA = "\x00new-scene"

    def _refresh_sync_scene_combo(self) -> None:
        """Fills the scene combo: every scene in use (plus the active one,
        which may not have a set yet), then "New scene…"."""
        combo = self._sync_scene_combo
        active = self.preferences.active_sync_scene
        combo.blockSignals(True)
        combo.clear()
        for name in scene_names(self.preferences.controller_sync_sets, active):
            combo.addItem(name, name)
        combo.insertSeparator(combo.count())
        combo.addItem("New scene…", self._NEW_SCENE_DATA)
        combo.setCurrentIndex(max(combo.findData(active), 0))
        combo.blockSignals(False)

    def _on_sync_scene_activated(self, index: int) -> None:
        data = self._sync_scene_combo.itemData(index)
        if data == self._NEW_SCENE_DATA:
            name, accepted = QInputDialog.getText(
                self, "New sync scene", "Scene name (e.g. Tek, DnB, Warm-up):"
            )
            if not accepted or not name.strip():
                self._refresh_sync_scene_combo()  # back to the active scene
                return
            data = name
        self._set_active_sync_scene(str(data))

    def _set_active_sync_scene(self, scene: str) -> list[SyncResult]:
        """Makes ``scene`` active (persisted). By default nothing is sent --
        ⟳ Sync does that, so switching scenes mid-set never surprises a
        controller -- unless "Sync when switching scene" (issue #212) is on:
        then an actual change sends the new scene's sets right away, silently
        like the launch-time Sync (status bar only, no dialog without sets).
        Re-picking the scene that is already active sends nothing."""
        scene = normalize_scene(scene)
        changed = scene != self.preferences.active_sync_scene
        self.preferences.active_sync_scene = scene
        self._save_preferences()
        message = f"Sync scene: {scene}"
        results: list[SyncResult] = []
        if changed and self.preferences.sync_on_scene_switch:
            sync_sets = self.preferences.active_sync_sets()
            if sync_sets:
                results = run_sync(sync_sets, list_output_ports())
                message += f" -- {summarize_results(results)}"
        self.statusBar().showMessage(message, 10_000 if results else 5_000)
        return results

    def _apply_plugin_preferences(self) -> None:
        controller_ids = {
            definition.plugin_id or definition.name
            for definition in catalog.all_controller_definitions()
            if self.preferences.is_enabled(definition.plugin_id or definition.name)
        }
        software_ids = {
            definition.plugin_id
            for definition in software.all_definitions()
            if self.preferences.is_enabled(definition.plugin_id)
        }
        software.set_enabled_plugin_ids(software_ids)
        # The View-menu "Show all controllers" override wins over the
        # per-controller Preferences checkboxes without discarding them —
        # unticking it restores exactly this enabled set.
        catalog.set_enabled_plugin_ids(None if self._show_all_controllers else controller_ids)

    def _on_performance_mode_toggled(self, checked: bool) -> None:
        self._performance_mode = checked
        if checked:
            self._performance_saved_ratios = dict(self._pair_ratio_by_id)
            for splitter in self._pair_splitters:
                self._pair_ratio_by_id[id(splitter)] = _PERFORMANCE_TREE_RATIO
                self._set_pair_ratio(splitter, _PERFORMANCE_TREE_RATIO)
        else:
            if self._performance_saved_ratios is not None:
                self._pair_ratio_by_id.update(self._performance_saved_ratios)
            self._performance_saved_ratios = None
            for splitter in self._pair_splitters:
                ratio = self._pair_ratio_by_id.get(id(splitter), 0.5)
                self._set_pair_ratio(splitter, ratio)
        zoom = _PERFORMANCE_ZOOM_FACTOR if checked else 1.0
        for view in (self.layout_view, self.deck_layout_view, self.controller_layout_view):
            view.set_zoom(zoom)
        self.statusBar().showMessage(
            "Performance mode on — tree hidden, layout enlarged"
            if checked
            else "Performance mode off"
        )

    def _on_left_tab_changed(self, index: int) -> None:
        """Show the edit / validation column only on the tree tabs."""
        self._right_splitter.setVisible(index in self._editing_tab_indexes)

    def _on_show_all_controllers_toggled(self, checked: bool) -> None:
        self._show_all_controllers = checked
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue("view/show_all_controllers", checked)
        self._apply_plugin_preferences()
        # Repopulate every controller combo/tree from the now-changed registry.
        self._on_controller_applied(self.introduction_view._controller_combo.currentText())
        self.statusBar().showMessage(
            "Showing all controllers" if checked else "Showing enabled controllers only"
        )

    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open DJ mapping",
            str(self._mapping_start_dir()),
            "Supported mapping files (*.xml *.nml *.tsi);;All files (*)",
        )
        if not path_str:
            return
        self._load_mapping_from_path(Path(path_str))

    def _on_open_mapping_requested(self, path_str: str) -> None:
        """Controller Setup's "open this XML for editing too" follow-up — the
        same as File -> Open on that path."""
        self._load_mapping_from_path(Path(path_str))
        if self.config is not None:
            self.left_tabs.setCurrentIndex(self._tab_indexes["channel"])

    def _load_mapping_from_path(self, path: Path, software_id: str | None = None) -> None:
        """Open a mapping. With `software_id` (a reopened file whose software
        is already known) the detection prompt is skipped."""
        _LOGGER.info("Opening mapping file %s", path)
        try:
            mapping_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            _LOGGER.exception("Failed to read %s", path)
            QMessageBox.critical(self, "Failed to open file", str(exc))
            return
        definitions = software.active_definitions()
        names = [definition.name for definition in definitions]
        detection = detect_software_mapping(mapping_text, path.suffix)
        detected = detection.best
        detected_index = next(
            (
                index
                for index, definition in enumerate(definitions)
                if detected is not None and definition.plugin_id == detected.plugin_id
            ),
            -1,
        )
        current = detected_index if detected_index >= 0 else next(
            (index for index, definition in enumerate(definitions) if definition.plugin_id == self.software_id),
            0,
        )
        prompt = "Mapping software:"
        if detected is not None:
            prompt = f"Mapping software (detected: {detected.name}, {detected.score}% — {detected.reasons[0]}):"
        known = next((definition for definition in definitions if definition.plugin_id == software_id), None)
        if known is not None:
            selected = known
        elif detected is not None and detection.status == "match" and self.preferences.detection_policy == "suggest":
            selected = definitions[detected_index]
        else:
            software_name, accepted = QInputDialog.getItem(
                self,
                "Open DJ mapping",
                prompt,
                names,
                current,
                False,
            )
            if not accepted:
                return
            selected = definitions[names.index(software_name)]
        try:
            self.config = selected.parser(mapping_text)
        except Exception as exc:
            _LOGGER.exception("Failed to parse %s as %s", path, selected.plugin_id)
            QMessageBox.critical(self, "Failed to open file", str(exc))
            return
        self.current_path = path
        self.software_id = selected.plugin_id
        self.undo_stack.clear()
        self._load_tree()
        self.issues_table.setRowCount(0)
        self.statusBar().showMessage(f"Loaded {len(self.config.controls)} controls from {self.current_path.name}")
        self._remember_mapping(path)
        _LOGGER.info("Loaded %d control(s) from %s (software=%s)", len(self.config.controls), path, selected.plugin_id)

    def _update_window_title(self) -> None:
        """Reflects the loaded file and its software (issue #121) -- the
        title used to stay a static "DJ MIDI Studio" for the entire session,
        the one-time "which software?" load dialog being the only place that
        ever named it."""
        if self.current_path is None or self.config is None:
            self.setWindowTitle("DJ MIDI Studio")
            return
        definition = software.get_definition(self.software_id)
        self.setWindowTitle(f"DJ MIDI Studio — {self.current_path.name} [{definition.name}]")

    def _load_tree(self) -> None:
        assert self.config is not None
        definition = software.get_definition(self.software_id)
        self.introduction_view.set_loaded_config_info(
            self.current_path,
            len(self.config.controls),
            software_id=self.software_id,
            software_name=definition.name,
        )
        self._update_window_title()
        self._rebuild_channel_columns()
        self._refresh_layout_usage()
        self._refresh_deck_view()
        self.function_search_view.set_config(self.config)
        self.live_monitor_view.set_config(self.config)
        if self.preferences.auto_start_live_monitor:
            self.live_monitor_view.ensure_monitoring_started()

    def _rebuild_channel_columns(self) -> None:
        assert self.config is not None
        self.channel_splitter = replace_splitter(self._channel_columns_scroll, self.channel_splitter)

        self.node_to_item = {}
        self._channel_model_owner = {}
        self.channel_proxies = []
        search_text = self.search_box.text()

        for _channel, model, node_to_item in build_channel_columns(self.config):
            self.node_to_item.update(node_to_item)

            proxy = QSortFilterProxyModel(self)
            proxy.setRecursiveFilteringEnabled(True)
            proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            proxy.setSourceModel(model)
            if search_text:
                proxy.setFilterFixedString(search_text)
            self.channel_proxies.append(proxy)

            view = QTreeView()
            view.setMinimumWidth(MAPPING_COLUMN_MIN_WIDTH)
            self._style_mapping_tree(view)
            view.setHeaderHidden(False)
            view.setModel(proxy)
            view.expandToDepth(0)
            view.selectionModel().selectionChanged.connect(
                lambda *_, v=view, p=proxy: self._on_channel_selection_changed(v, p)
            )
            self._channel_model_owner[id(model)] = (view, proxy)
            self.channel_splitter.addWidget(view)

    def _refresh_deck_view(self) -> None:
        assert self.config is not None
        self.deck_splitter = replace_splitter(self._deck_columns_scroll, self.deck_splitter)
        self._deck_tree_views = []

        for _deck_id, model in build_deck_columns(self.config):
            view = QTreeView()
            view.setMinimumWidth(MAPPING_COLUMN_MIN_WIDTH)
            self._style_mapping_tree(view)
            view.setHeaderHidden(False)
            view.setModel(model)
            view.expandToDepth(0)
            view.selectionModel().selectionChanged.connect(lambda *_, v=view: self._on_deck_column_selection_changed(v))
            view.doubleClicked.connect(lambda index, v=view: self._on_deck_item_double_clicked(v, index))
            self.deck_splitter.addWidget(view)
            self._deck_tree_views.append(view)

    def _on_deck_column_selection_changed(self, view: QTreeView) -> None:
        indexes = view.selectionModel().selectedIndexes()
        if not indexes:
            self.edit_panel.set_node(None)
            self._update_layout_selection(None, None, None)
            return
        group = view.model().itemFromIndex(indexes[0]).data(NODE_ROLE)
        if not isinstance(group, MappingGroup):
            self.edit_panel.set_node(None)
            self._update_layout_selection(None, None, None)
            return
        self.edit_panel.set_node(group)
        self._update_layout_selection(group.channel, group.event_type, group.control_no)

    def _on_deck_item_double_clicked(self, view: QTreeView, index) -> None:
        group = view.model().itemFromIndex(index).data(NODE_ROLE)
        if not isinstance(group, MappingGroup):
            return
        control = group.members[0][0]
        self._select_control_in_channel_columns(control)
        self.left_tabs.setCurrentIndex(self._tab_indexes["channel"])

    def _on_group_edit_applied(self) -> None:
        # A group edit may touch every duplicate's deck/slot label (main columns)
        # and can move the group to a different deck/slot column, so the deck
        # columns need a full rebuild rather than a single relabel.
        current_group = self.edit_panel.current_node
        if isinstance(current_group, MappingGroup):
            for _, _, mapping in current_group.members:
                item = self.node_to_item.get(id(mapping))
                if item is not None:
                    relabel_item(item, mapping)
        QTimer.singleShot(0, self._refresh_edit_panel)
        QTimer.singleShot(0, self._refresh_layout_usage)
        QTimer.singleShot(0, self._refresh_deck_view)

    def _refresh_layout_usage(self) -> None:
        assert self.config is not None
        usage: dict[layout_mod.CellKey, dict[str, set[str]]] = {}
        linked_cells: dict[layout_mod.CellKey, set[layout_mod.CellKey]] = {}
        for control in self.config.controls:
            hits = catalog.lookup(control.channel, control.event_type, control.control)
            if not hits:
                continue
            # A single raw (channel, event_type, control) trigger can match both
            # controllers' catalogs at once (a merged config doesn't record which
            # physical device sent it) — link those cells so the layout can show
            # each controller's interpretation of the same trigger side by side.
            # presentation_key_for_hit() (not the merged cell_key()) so a link
            # from DDJ-XP2's right pad grid points at XDJ-XZ's own right-side
            # hit for the same trigger, not whichever side happens to share
            # the merged key.
            hit_keys = {layout_mod.presentation_key_for_hit(hit) for hit in hits}
            for key in hit_keys:
                others = {other for other in hit_keys if other[0] != key[0]}
                if others:
                    linked_cells.setdefault(key, set()).update(others)
            for userio in control.userios:
                for mapping in userio.mappings:
                    if not mapping.deck_id:
                        continue
                    for hit in hits:
                        # Stays keyed by the *merged* cell here (unlike
                        # linked_cells above): the "By Controller" text tree
                        # and the classic card grid both read this same
                        # usage dict with no per-side concept at all, so
                        # splitting it at the source would silently
                        # under-report their aggregate deck/tag counts.
                        # ControllerLayoutView._cell_decks_and_tags() does
                        # the side-narrowing itself, downstream, only for
                        # the real-position schematic.
                        cell = usage.setdefault(layout_mod.cell_key(hit), {})
                        cell.setdefault(mapping.deck_id, set()).add(mapping.tag)
        self.layout_view.set_usage(usage, linked_cells)
        self.deck_layout_view.set_usage(usage, linked_cells)
        self.controller_layout_view.set_usage(usage, linked_cells)
        self.introduction_view.set_usage_summary(usage)
        self._refresh_controller_columns(usage)

    def _refresh_controller_columns(self, usage: dict[layout_mod.CellKey, dict[str, set[str]]]) -> None:
        self.controller_splitter = replace_splitter(self._controller_columns_scroll, self.controller_splitter)
        self._controller_tree_views = []

        for _controller, model, expand_flags in build_controller_columns(usage):
            view = QTreeView()
            view.setMinimumWidth(MAPPING_COLUMN_MIN_WIDTH)
            self._style_mapping_tree(view)
            view.setHeaderHidden(False)
            view.setModel(model)
            view.selectionModel().selectionChanged.connect(lambda *_, v=view: self._on_controller_selection_changed(v))
            self.controller_splitter.addWidget(view)
            self._controller_tree_views.append(view)
            # Deferred: expanding items right after setModel(), before the view has
            # done its first layout pass, is unreliable in some Qt/platform
            # combinations (the row exists in the model but the view hasn't built
            # its internal expand-state tracking for it yet).
            QTimer.singleShot(0, lambda v=view, m=model, flags=expand_flags: self._apply_controller_expand_state(v, m, flags))

    @staticmethod
    def _style_mapping_tree(view: QTreeView) -> None:
        """Apply the DJ booth palette to a mapping tree at construction
        time. This used to set a literal hardcoded copy of the dark
        palette's colors, so By Channel/Deck/Controller stayed dark even
        after picking Light -- theme.mapping_tree_stylesheet() builds this
        from the same tokens theme.py substitutes its own app-wide QSS
        from.

        A live Settings -> Preferences theme switch is handled centrally by
        _restyle_mapping_trees (one connection, made once in __init__),
        not by a per-tree theme.signals.themeChanged connection here -- see
        that method's docstring for why the per-tree version, tried first,
        turned out to leak."""
        view.setAlternatingRowColors(True)
        view.setIndentation(16)
        view.setAnimated(True)
        view.setStyleSheet(mapping_tree_stylesheet())

    def _restyle_mapping_trees(self, *_args: object) -> None:
        """Rebuild every *currently live* mapping tree's stylesheet (and
        force-repaint its visible rows -- see _refresh_tree_row_layout) on
        a live Settings -> Preferences theme switch.

        The first version connected each tree individually to
        theme.signals.themeChanged via a closure, at construction
        (_style_mapping_tree). That leaked: reloading a mapping replaces
        self._channel_model_owner / _deck_tree_views / _controller_tree_views
        wholesale (splitter_utils.replace_splitter -> deleteLater() on the
        old widgets) without ever disconnecting their individual
        connections, and a plain closure isn't a bound QObject method
        PySide auto-disconnects on the tree's destruction. Each dead
        connection kept paying for a full restyle on every future theme
        switch for as long as the underlying widget lingered (Qt's
        deferred-deletion timing, not instant) -- measured compounding
        linearly across repeated reloads within a single session, not just
        an artifact of a test file constructing many windows.

        Iterating these three lists instead has nothing to ever go stale:
        they're always replaced, never appended to, so an old tree simply
        isn't in them anymore once something rebuilds the columns -- one
        connection, tied to MainWindow's own genuinely-app-session-long
        lifetime, covers every tree that currently exists no matter how
        many times the mapping has been reloaded."""
        for view, _proxy in self._channel_model_owner.values():
            view.setStyleSheet(mapping_tree_stylesheet())
            _refresh_tree_row_layout(view)
        for view in (*self._deck_tree_views, *self._controller_tree_views):
            view.setStyleSheet(mapping_tree_stylesheet())
            _refresh_tree_row_layout(view)

    def _apply_controller_expand_state(self, view: QTreeView, model: QStandardItemModel, expand_flags: list[tuple[int, bool]]) -> None:
        for row, has_used_leaf in expand_flags:
            view.setExpanded(model.index(row, 0), has_used_leaf)

    def _on_controller_selection_changed(self, view: QTreeView) -> None:
        indexes = view.selectionModel().selectedIndexes()
        if not indexes:
            return
        cell_key = view.model().itemFromIndex(indexes[0]).data(CELL_KEY_ROLE)
        if cell_key is not None:
            self._on_layout_cell_activated(cell_key)

    def _select_control_in_channel_columns(self, control: Control) -> bool:
        item = self.node_to_item.get(id(control))
        if item is None:
            return False
        owner = self._channel_model_owner.get(id(item.model()))
        if owner is None:
            return False
        view, proxy = owner
        proxy_index = proxy.mapFromSource(item.index())
        view.setCurrentIndex(proxy_index)
        view.scrollTo(proxy_index)
        return True

    def _select_model_index(self, view: QTreeView, index: QModelIndex) -> None:
        selection = view.selectionModel()
        selection.clearSelection()
        selection.select(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
        )
        view.setCurrentIndex(index)
        view.scrollTo(index)

    def _find_index_with_data(self, model, value: object, role: int, parent: QModelIndex | None = None) -> QModelIndex:
        if parent is None:
            parent = QModelIndex()
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            if index.data(role) == value:
                return index
            found = self._find_index_with_data(model, value, role, index)
            if found.isValid():
                return found
        return QModelIndex()

    def _select_controller_cell(self, key: layout_mod.CellKey) -> bool:
        """The "By Controller" text tree (gui/controller_tree.py) has no
        separate row for a right-side real-position marker at all -- it's
        built from build_layout()'s own cells, a merged, aggregate-usage
        view by design (unlike the schematic layout, it never modeled two
        physical grids/clusters as distinct rows), so a right-side key
        simply finds no row here and this returns False.

        Deliberately does NOT fall back to selecting the merged row: doing
        so would select a tree row whose own CELL_KEY_ROLE is the *merged*
        key, and _on_controller_selection_changed's selectionChanged
        handler would immediately re-run _on_layout_cell_activated with
        that merged key -- silently overwriting the correct side-aware
        selection this call was trying to make with whatever the merged
        cell's first (often left-side) match happens to be. Confirmed by a
        real offscreen click simulation: this exact feedback loop is what
        produced a right-side click landing on a left-side deck. Known,
        disclosed limitation -- not silently dropped."""
        for view in self._controller_tree_views:
            index = self._find_index_with_data(view.model(), key, CELL_KEY_ROLE)
            if index.isValid():
                self._select_model_index(view, index)
                return True
        return False

    def _select_deck_group(self, key: layout_mod.CellKey) -> bool:
        for view in self._deck_tree_views:
            model = view.model()
            for row in range(model.rowCount()):
                slot_index = model.index(row, 0)
                for child_row in range(model.rowCount(slot_index)):
                    index = model.index(child_row, 0, slot_index)
                    group = index.data(NODE_ROLE)
                    if not isinstance(group, MappingGroup):
                        continue
                    if any(
                        layout_mod.presentation_key_for_hit(hit) == key
                        for hit in catalog.lookup(group.channel, group.event_type, group.control_no)
                    ):
                        self._select_model_index(view, index)
                        return True
        return False

    def _on_layout_cell_activated(self, key: tuple, source_tab: str = "channel") -> None:
        if self.config is None:
            return
        # find_controls_for_cell() (not a manual cell_key(hit) == key scan)
        # so a right-side real-position marker's presentation key (DDJ-XP2/
        # XDJ-XZ decks 2/4) only matches controls actually on that physical
        # side, instead of jumping to whatever control happens to share the
        # left side's merged cell -- the By Channel/Deck/Controller tabs'
        # own follow-up to the Controller Emulator's identical fix.
        matches = layout_mod.find_controls_for_cell(self.config, key)
        if not matches:
            self.statusBar().showMessage(f"No control in this file uses '{key[2]}'")
            self._update_layout_selection(None, None, None)
            return
        if source_tab == "controller":
            self._select_controller_cell(key)
        elif source_tab == "deck":
            if not self._select_deck_group(key):
                self._select_control_in_channel_columns(matches[0])
        else:
            self._select_control_in_channel_columns(matches[0])
        self.left_tabs.setCurrentIndex(self._tab_indexes[source_tab])
        self.statusBar().showMessage(f"'{key[2]}': {len(matches)} control(s) in this file, showing first")
        # setCurrentIndex above already re-highlights via _on_channel_selection_changed,
        # but do it directly too in case the selection didn't actually change
        # (clicking the same physical control's other half again).
        self._update_layout_selection(matches[0].channel, matches[0].event_type, matches[0].control)

    def _on_function_result_selected(self, result: FunctionResult) -> None:
        """A Find-function result: select its first control in the current
        mapping tab (like a layout cell click), then outline *every* control
        bound to it on the three layouts -- after the selection, whose own
        selectionChanged handler narrows the outline to one control."""
        if self.config is None or not result.controls:
            return
        tab = next(
            (key for key in ("channel", "deck", "controller") if self._tab_indexes[key] == self.left_tabs.currentIndex()),
            "channel",
        )
        first = result.controls[0]
        first_keys = [
            layout_mod.presentation_key_for_hit(hit)
            for hit in catalog.lookup(first.channel, first.event_type, first.control)
        ]
        selected = False
        if tab == "deck":
            selected = self._select_deck_group_for_mappings(result.mappings)
        elif tab == "controller":
            selected = any(self._select_controller_cell(key) for key in first_keys)
            # The tree row stands for a whole cell, and its own handler picks
            # *some* control on it; point the edit panel at this exact one.
            self._select_control_in_channel_columns(first)
        if not selected:
            tab = "channel"
            self._select_control_in_channel_columns(first)
        self.left_tabs.setCurrentIndex(self._tab_indexes[tab])
        keys = {
            layout_mod.presentation_key_for_hit(hit)
            for control in result.controls
            for hit in catalog.lookup(control.channel, control.event_type, control.control)
        }
        self.layout_view.set_selected_keys(keys)
        self.deck_layout_view.set_selected_keys(keys)
        self.controller_layout_view.set_selected_keys(keys)
        self.statusBar().showMessage(
            f"'{result.label}' ({result.location()}): {len(result.triggers)} control(s), "
            f"{len(keys)} highlighted on the layout"
        )

    def _select_deck_group_for_mappings(self, mappings: list[MappingElement]) -> bool:
        """Selects the By Deck row whose group holds one of `mappings` --
        the exact deck/slot row, unlike _select_deck_group's first cell hit."""
        wanted = {id(mapping) for mapping in mappings}
        for view in self._deck_tree_views:
            model = view.model()
            for row in range(model.rowCount()):
                slot_index = model.index(row, 0)
                for child_row in range(model.rowCount(slot_index)):
                    index = model.index(child_row, 0, slot_index)
                    group = index.data(NODE_ROLE)
                    if isinstance(group, MappingGroup) and any(id(m) in wanted for _, _, m in group.members):
                        self._select_model_index(view, index)
                        return True
        return False

    def _update_layout_selection(self, channel: str | None, event_type: str | None, control_no: str | None) -> None:
        keys: set[layout_mod.CellKey] = set()
        if channel and event_type and control_no:
            # presentation_key_for_hit() (not the merged cell_key()) so
            # selecting a control mapped to, say, DDJ-XP2's deck 2/4 pad
            # grid highlights only that physical marker, not both left and
            # right at once.
            keys = {
                layout_mod.presentation_key_for_hit(hit)
                for hit in catalog.lookup(channel, event_type, control_no)
            }
        self.layout_view.set_selected_keys(keys)
        self.deck_layout_view.set_selected_keys(keys)
        self.controller_layout_view.set_selected_keys(keys)

    def _on_live_midi_event(self, event: MidiEvent) -> None:
        try:
            value = int(event.data2)
        except (TypeError, ValueError):
            value = None

        # Output-direction traffic (Serato -> controller LED feedback, seen on
        # the virtual monitor port) drives a *latched* LED highlight, kept
        # separate from the input-direction momentary "held" state so an
        # input release can't clear an LED the software is still driving. We
        # assume the LED note number equals the input trigger note (Serato's
        # own convention for almost every mapping; there's no per-control
        # led_note field in the catalog). No flash, no selection change --
        # this is passive state, not a user gesture.
        if event.direction == "out":
            self._on_output_led_event(event, value)
            return

        # A jog-wheel turn is a stream of relative Control Change ticks that
        # deliberately have no catalog entry (continuous controls are out of
        # catalog scope), so it can't flow through the lookup path below.
        # Resolve it against gui/jog.py's small per-controller table instead
        # and integrate the ticks into each jog glyph's notch angle. Handled
        # before _update_layout_selection so a jog turn never clears the
        # cross-tab selection -- it isn't a "the user picked this control"
        # gesture, just motion feedback.
        jog_keys = jog_mod.jog_cell_keys_for_event(
            event.channel, event.event_type, event.data1
        )
        if jog_keys:
            delta = jog_mod.decode_jog_delta(value)
            if delta:
                for lv in (
                    self.layout_view,
                    self.deck_layout_view,
                    self.controller_layout_view,
                ):
                    for key in jog_keys:
                        lv.spin_jog(key, delta)
                for dock in self._emulator_docks.values():
                    view = dock.widget()
                    if isinstance(view, ControllerEmulatorView):
                        for key in jog_keys:
                            view.spin_jog_from_key(key, delta)
                # The Controller Images overlay only carries the one
                # "Jog wheel" geometry entry (no left/right split), so strip
                # the mirror suffix and spin it when this tab shows that
                # controller.
                image_controller = self.controller_image_view.current_controller_name()
                for key in jog_keys:
                    if key[0] == image_controller:
                        label = key[2].removesuffix(layout_mod._RIGHT_GRID_SUFFIX)
                        self.controller_image_view.spin_jog(label, delta)
            return

        # A note release arrives as "Note Off" or as "Note On" with velocity
        # 0 (running status). Catalog entries are all stored as "Note On", so
        # resolve a release against "Note On" too -- the selection/highlight
        # should track the control that was just let go, not vanish.
        is_release = event.event_type == "Note Off" or (
            event.event_type == "Note On" and value == 0
        )
        is_press = event.event_type == "Note On" and (value or 0) > 0
        lookup_type = "Note On" if event.event_type == "Note Off" else event.event_type

        self._update_layout_selection(event.channel, lookup_type, event.data1)
        if not (event.channel and event.event_type and event.data1):
            return
        hits = catalog.lookup(event.channel, lookup_type, event.data1)
        # Same reasoning as _update_layout_selection(): flash/value/hold only
        # the physical marker the live hit's own deck actually belongs to,
        # not both sides of a split cell.
        keys = {layout_mod.presentation_key_for_hit(hit) for hit in hits}
        layouts = (self.layout_view, self.deck_layout_view, self.controller_layout_view)
        for key in keys:
            # Persistent "held down" amber highlight first -- lit on press,
            # cleared on release; a plain CC (neither) leaves it be -- so the
            # 220ms white flash_key() pulse below always paints on top of it
            # for a press (Controller Images mutates its marker in place;
            # order matters there).
            if is_press or is_release:
                for lv in layouts:
                    lv.set_active(key, is_press)
            if not is_release:
                for lv in layouts:
                    lv.flash_key(key)
            if value is not None:
                for lv in layouts:
                    lv.set_value(key, value)

        # The Controller Images tab's real-photo overlay, for whichever
        # controller it currently shows (gui/geometry.py).
        image_controller = self.controller_image_view.current_controller_name()
        for hit in hits:
            if hit.controller != image_controller:
                continue
            label = resolve_geometry_label(hit.controller, hit.name)
            if label is None:
                continue
            if is_press or is_release:
                self.controller_image_view.set_active(label, is_press)
            if not is_release:
                self.controller_image_view.flash_key(label)

        # Every open Controller Emulator dock -- the flash_live_hit /
        # set_live_active_from_hit calls self-filter to the controller each
        # instance shows, so this can run unconditionally over all of them.
        for dock in self._emulator_docks.values():
            view = dock.widget()
            if not isinstance(view, ControllerEmulatorView):
                continue
            for hit in hits:
                if is_press or is_release:
                    view.set_live_active_from_hit(hit, is_press)
                if not is_release:
                    view.flash_live_hit(hit)

    def _on_output_led_event(self, event: MidiEvent, value: int | None) -> None:
        """Latch/clear the amber LED highlight from an output-direction MIDI
        note. Only note events count -- a CC on the output port (rare, e.g. a
        motorised fader) has no LED meaning here and is ignored."""
        led_on = event.event_type == "Note On" and (value or 0) > 0
        led_off = event.event_type == "Note Off" or (
            event.event_type == "Note On" and value == 0
        )
        if not (led_on or led_off):
            return
        if not (event.channel and event.data1):
            return
        hits = catalog.lookup(event.channel, "Note On", event.data1)
        keys = {layout_mod.presentation_key_for_hit(hit) for hit in hits}
        layouts = (self.layout_view, self.deck_layout_view, self.controller_layout_view)
        for key in keys:
            for lv in layouts:
                lv.set_led(key, led_on)

        image_controller = self.controller_image_view.current_controller_name()
        for hit in hits:
            if hit.controller == image_controller:
                label = resolve_geometry_label(hit.controller, hit.name)
                if label is not None:
                    self.controller_image_view.set_led(label, led_on)

        for dock in self._emulator_docks.values():
            view = dock.widget()
            if not isinstance(view, ControllerEmulatorView):
                continue
            for hit in hits:
                view.set_led_from_hit(hit, led_on)

    def _on_intro_drilldown_requested(self, target: str, controller_name: str) -> None:
        if target in self._tool_docks:
            self._show_tool_dock(target)
            return
        self.layout_view.set_controller(controller_name)
        self.deck_layout_view.set_controller(controller_name)
        self.controller_layout_view.set_controller(controller_name)
        self.controller_image_view.set_controller(controller_name)
        target_index = self._tab_indexes.get(target)
        if target_index is not None:
            self.left_tabs.setCurrentIndex(target_index)

    def _on_controller_applied(self, name: str) -> None:
        """A Controller Setup draft was registered into the live catalog registry
        (in-memory only) — refresh every view whose controller combo/columns
        were only ever populated once, at construction time, so it shows up
        immediately instead of only after restarting the app."""
        layout_mod.clear_reverse_lookup_cache()
        layout_mod.clear_label_to_key_cache()
        self.layout_view.refresh_controllers()
        self.deck_layout_view.refresh_controllers()
        self.controller_layout_view.refresh_controllers()
        self.controller_image_view.refresh_controllers()
        self.introduction_view.refresh_controllers()
        for dock in self._emulator_docks.values():
            widget = dock.widget()
            if isinstance(widget, ControllerEmulatorView):
                widget.refresh_controllers()
        if self.config is not None:
            self._refresh_layout_usage()
        self.statusBar().showMessage(f"'{name}' applied for this session.")

    def closeEvent(self, event) -> None:
        self._record_timer.stop()
        self._plug_in_timer.stop()
        self._record_monitor.close_all()
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue("window/geometry", self.saveGeometry())
            settings.setValue("window/state", self.saveState(1))
            self.midi_routing_view.save_state(settings)
            self.metronome_view.save_state(settings)
            open_controllers = [
                widget.current_controller()
                for dock in self._emulator_docks.values()
                if isinstance(widget := dock.widget(), ControllerEmulatorView)
            ]
            settings.setValue("emulator/open_controllers", open_controllers)
            settings.sync()
        self.live_monitor_view.shutdown()
        self.midi_routing_view.shutdown()
        self.music_library_view.close_db()
        self.metronome_view.shutdown()
        self.controller_setup_view.shutdown()
        super().closeEvent(event)

    def _find_ancestor_control(self, item) -> Control | None:
        while item is not None:
            node = item.data(NODE_ROLE)
            if isinstance(node, Control):
                return node
            item = item.parent()
        return None

    def _on_search_text_changed(self, text: str) -> None:
        for proxy in self.channel_proxies:
            proxy.setFilterFixedString(text)

    def _on_channel_selection_changed(self, view: QTreeView, proxy: QSortFilterProxyModel) -> None:
        indexes = view.selectionModel().selectedIndexes()
        if not indexes:
            self.edit_panel.set_node(None)
            self._update_layout_selection(None, None, None)
            return
        source_index = proxy.mapToSource(indexes[0])
        item = proxy.sourceModel().itemFromIndex(source_index)
        self.edit_panel.set_node(item.data(NODE_ROLE))
        control = self._find_ancestor_control(item)
        if control is not None:
            self._update_layout_selection(control.channel, control.event_type, control.control)
        else:
            self._update_layout_selection(None, None, None)

    def _on_command_applied(self, relabel_node: object) -> None:
        item = self.node_to_item.get(id(relabel_node))
        if item is not None:
            relabel_item(item, relabel_node)
        # Deferred so we never rebuild the edit panel from inside the very
        # widget signal (editingFinished/itemChanged) that triggered the edit.
        QTimer.singleShot(0, self._refresh_edit_panel)
        if isinstance(relabel_node, (Control, MappingElement)):
            QTimer.singleShot(0, self._refresh_layout_usage)
            QTimer.singleShot(0, self._refresh_deck_view)

    def _refresh_edit_panel(self) -> None:
        self.edit_panel.set_node(self.edit_panel.current_node)

    def _on_save(self) -> None:
        if self.config is None:
            return
        if self.current_path is None:
            self._on_save_as()
            return
        definition = software.get_definition(self.software_id)
        self._safe_save(self.current_path, definition)

    def _on_save_as(self) -> None:
        if self.config is None:
            return
        definition = software.get_definition(self.software_id)
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {definition.name} mapping",
            str(self.current_path or self._mapping_start_dir()),
            f"{definition.name} files (*{' *'.join(definition.extensions)})",
        )
        if not path_str:
            return
        target = Path(path_str)
        if self._safe_save(target, definition):
            self.current_path = target
            self._remember_mapping(target)
            self.statusBar().showMessage(f"Saved to {self.current_path}")

    def _safe_save(self, target: Path, definition) -> bool:
        _LOGGER.info("Preparing to save %s as %s", target, definition.plugin_id)
        try:
            plan = prepare_update(
                target,
                definition.exporter(self.config),
                definition.parser,
                summarize=definition.change_summary,
            )
        except (OSError, TypeError, ValueError) as exc:
            _LOGGER.exception("Failed to prepare save for %s", target)
            QMessageBox.critical(self, "Failed to save mapping", str(exc))
            return False
        dialog = SafeUpdateDialog(str(target), plan.diff, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            _LOGGER.info("Save to %s cancelled by user at the preview/diff step", target)
            return False
        try:
            plan.apply()
        except OSError as exc:
            _LOGGER.exception("Failed to apply save to %s", target)
            QMessageBox.critical(self, "Failed to save mapping", str(exc))
            return False
        self._last_save_plan = plan
        self._refresh_file_actions()
        self.statusBar().showMessage(f"Saved to {target}")
        return True

    def _on_rollback_last_save(self) -> None:
        """Restore the version saved before the mapping's last save: the
        `.bak` every save keeps next to the file, so this also works for a
        save made in an earlier session (it used to need this session's)."""
        if self.current_path is None:
            return
        backup = file_locations.backup_path(self.current_path)
        if not backup.is_file():
            self._refresh_file_actions()
            return
        when = datetime.fromtimestamp(backup.stat().st_mtime, tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M")
        answer = QMessageBox.question(
            self,
            "Restore previous version",
            f"Replace {self.current_path.name} with the version saved before its last save ({when})?\n\n"
            "Unsaved edits in the app are lost.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.copy2(backup, self.current_path)
        except OSError as exc:
            _LOGGER.exception("Failed to restore %s from %s", self.current_path, backup)
            QMessageBox.critical(self, "Failed to restore the previous version", str(exc))
            return
        _LOGGER.info("Restored %s from %s", self.current_path, backup)
        self._last_save_plan = None
        restored = self.current_path
        self._load_mapping_from_path(restored)
        self.statusBar().showMessage(f"Restored the previous version of {restored.name}")

    def _on_compare_with_file(self) -> None:
        if self.config is None:
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Compare with mapping",
            str(self._mapping_start_dir()),
            "Supported mapping files (*.xml *.nml *.tsi *.bak);;All files (*)",
        )
        if path_str:
            self._compare_with_path(Path(path_str))

    def _on_compare_with_backup(self) -> None:
        if self.config is None or self.current_path is None:
            return
        backup = file_locations.backup_path(self.current_path)
        if not backup.is_file():
            self._refresh_file_actions()
            return
        self._compare_with_path(backup, name=f"previous version ({backup.name})")

    def _parse_other_mapping(self, path: Path) -> MidiConfig:
        """Parse a file to compare against: as the software detection says
        when it is sure, else with the open mapping's software (a `.bak` has
        no telling suffix but is always the same format)."""
        text = path.read_text(encoding="utf-8")
        definition = software.get_definition(self.software_id)
        detection = detect_software_mapping(text, path.suffix)
        if detection.best is not None and detection.status == "match":
            definition = next(
                (d for d in software.active_definitions() if d.plugin_id == detection.best.plugin_id),
                definition,
            )
        return definition.parser(text)

    def _compare_with_path(self, path: Path, name: str | None = None) -> MappingDiffDialog | None:
        """Diff `path` (the reference) against the mapping as it is in the
        app now, unsaved edits included, and show the result."""
        assert self.config is not None
        try:
            other = self._parse_other_mapping(path)
        except Exception as exc:
            _LOGGER.exception("Failed to read %s for comparison", path)
            QMessageBox.critical(self, "Failed to compare", str(exc))
            return None
        diff = diff_configs(other, self.config)
        current = self.current_path.name if self.current_path is not None else "the open mapping"
        if self.undo_stack.count() and not self.undo_stack.isClean():
            current += " (with unsaved edits)"
        if self._diff_dialog is not None:
            self._diff_dialog.close()
        dialog = MappingDiffDialog(diff, name or path.name, current, self)
        dialog.triggerSelected.connect(self._on_diff_trigger_selected)
        self._diff_dialog = dialog
        dialog.show()
        self.statusBar().showMessage(f"Compared with {path.name}: {len(diff.entries)} difference(s)")
        return dialog

    def _on_diff_trigger_selected(self, channel: str, event_type: str, control_no: str) -> None:
        """Like a layout click: select the control in By Channel when the open
        mapping has it (a removed one only exists in the other file) and
        highlight it on the layouts either way."""
        if self.config is not None:
            match = next(
                (
                    c
                    for c in self.config.controls
                    if (c.channel, c.event_type, c.control) == (channel, event_type, control_no)
                ),
                None,
            )
            if match is not None and self._select_control_in_channel_columns(match):
                self.left_tabs.setCurrentIndex(self._tab_indexes["channel"])
        self._update_layout_selection(channel, event_type, control_no)

    def _on_backup_workspace(self) -> Path | None:
        """File → Back Up Workspace (issue #187): one zip of the workspace
        folder, preferences.json and, if asked, the library index."""
        include_library = False
        size = backup.library_db_size()
        if size is not None:
            answer = QMessageBox.question(
                self,
                "Back up workspace",
                f"Also include the music library index ({_human_size(size)})?\n\n"
                "It lists your tracks, categories and playlists -- never the audio files -- "
                "but it can be large, and a fresh scan rebuilds it.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return None
            include_library = answer == QMessageBox.StandardButton.Yes
        exports = user_paths.subfolder(user_paths.EXPORTS)
        exports.mkdir(parents=True, exist_ok=True)
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Back Up Workspace", str(exports / backup.default_backup_name()), _BACKUP_FILTER
        )
        if not path_str:
            return None
        target = Path(path_str)
        if target.suffix.lower() != ".zip":
            target = target.with_name(target.name + backup.BACKUP_SUFFIX)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            manifest = backup.create_backup(target, include_library=include_library)
        except (OSError, sqlite3.Error) as exc:
            _LOGGER.exception("Workspace backup to %s failed", target)
            QMessageBox.critical(self, "Backup failed", str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        _LOGGER.info("Backed up %d files to %s", len(manifest.entries), target)
        self.statusBar().showMessage(f"Backed up {len(manifest.entries)} files to {target}", 10_000)
        return target

    def _confirm_restore(self, plan: backup.RestorePlan) -> bool | None:
        """Ask before a restore writes anything. Returns whether to include
        the library index, or None when cancelled."""
        overwrites = plan.overwrites
        lines = [
            (
                f"Backup made {plan.manifest.created_at or 'at an unknown date'} "
                f"with DJ MIDI Studio {plan.manifest.app_version}."
            ),
            f"{len(plan.creates)} file(s) will be added, {len(overwrites)} existing file(s) overwritten.",
        ]
        if overwrites:
            shown = [str(item.target) for item in overwrites[:8]]
            if len(overwrites) > len(shown):
                shown.append(f"... and {len(overwrites) - len(shown)} more")
            lines.append("Overwritten:\n" + "\n".join(shown))
        lines.append("Files that are not in the backup are kept.")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Restore workspace")
        box.setText("Restore this backup over your current files?")
        box.setInformativeText("\n\n".join(lines))
        library_check = None
        if plan.manifest.has(backup.LIBRARY):
            library_check = QCheckBox("Also restore the music library index (replaces the current one)")
            library_check.setChecked(backup.library_db_size() is None)
            box.setCheckBox(library_check)
        restore_button = box.addButton("Restore", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not restore_button:
            return None
        return library_check is not None and library_check.isChecked()

    def _on_restore_workspace(self) -> bool:
        """File → Restore Workspace (issue #187). The restored preferences,
        profiles and library are picked up at the next launch."""
        exports = user_paths.subfolder(user_paths.EXPORTS)
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Restore Workspace", str(exports if exports.is_dir() else Path.home()), _BACKUP_FILTER
        )
        if not path_str:
            return False
        try:
            plan = backup.restore_backup(path_str)
        except (backup.BackupError, OSError) as exc:
            QMessageBox.critical(self, "Cannot restore this backup", str(exc))
            return False
        include_library = self._confirm_restore(plan)
        if include_library is None:
            return False
        if include_library:
            self.music_library_view.close_db()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            backup.restore_backup(path_str, dry_run=False, include_library=include_library)
        except (backup.BackupError, OSError, sqlite3.Error) as exc:
            _LOGGER.exception("Workspace restore from %s failed", path_str)
            QMessageBox.critical(self, "Restore failed", str(exc))
            return False
        finally:
            QApplication.restoreOverrideCursor()
        _LOGGER.info("Restored workspace backup %s", path_str)
        self.statusBar().showMessage(f"Restored {Path(path_str).name}", 10_000)
        answer = QMessageBox.question(
            self,
            "Workspace restored",
            "Your files are restored. Restart DJ MIDI Studio to load the restored preferences, "
            "controller profiles and library -- until then, saving preferences would overwrite "
            "the restored ones.\n\nQuit now?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.close()
        return True

    def _remember_draft(self, path: str) -> None:
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue(_LAST_DRAFT_SETTINGS_KEY, path)

    def _prepare_reopen_last_files(self) -> None:
        """Pick up where the user left off (issue #175): reopen the last
        mapping with its software -- no detection prompt -- and hand the last
        Controller Setup draft to that tab, which loads it the first time
        it's shown (unless a default file is set in Preferences). Real app
        only: tests and screenshot scripts have no settings."""
        settings = self._layout_settings()
        if settings is None or not self.preferences.reopen_last_files:
            return
        draft = settings.value(_LAST_DRAFT_SETTINGS_KEY, "", type=str)
        if draft and not self.preferences.controller_setup_default_file and Path(draft).is_file():
            self.controller_setup_view.set_default_file(draft)
        mapping = settings.value(_LAST_MAPPING_SETTINGS_KEY, "", type=str)
        software_id = settings.value(_LAST_SOFTWARE_SETTINGS_KEY, "", type=str) or None
        if mapping and Path(mapping).is_file():
            QTimer.singleShot(0, lambda: self._reopen_mapping(Path(mapping), software_id))

    def _reopen_mapping(self, path: Path, software_id: str | None) -> None:
        if self.config is not None:
            return  # something was opened meanwhile
        _LOGGER.info("Reopening the last mapping %s", path)
        self._load_mapping_from_path(path, software_id=software_id)

    def _save_preferences(self) -> None:
        """preferences.json, plus the Sync folder mirroring the sync sets."""
        self.preferences.save(self.preferences_path)
        sync_store.save_sync_sets(user_paths.sync_dir(), self.preferences.controller_sync_sets)
        if hasattr(self, "_sync_scene_combo"):
            self._refresh_sync_scene_combo()

    def _on_dashboard_file_action(self, action: str) -> None:
        """The Dashboard's "Your files" card buttons."""
        if action == "open":
            self._on_open()
        elif action == "reveal":
            self._on_reveal_mapping()
        elif action == "restore":
            self._on_rollback_last_save()
        elif action == "sync":
            self._on_preferences(tab="Controller sync")
        elif action.startswith("recent:"):
            self._load_mapping_from_path(Path(action.removeprefix("recent:")))

    def _on_reveal_installed_profiles(self) -> None:
        folder = user_paths.controllers_dir()
        folder.mkdir(parents=True, exist_ok=True)
        reveal_in_file_manager(folder)

    def _cheat_sheet_preselection(self, candidates: list[str]) -> set[str]:
        """Which candidate controllers the cheat-sheet dialog ticks first:
        the ones connected right now (by MIDI port name) and the one the
        Controller Images tab shows; failing both, the best-matching one."""
        guessed: set[str] = set()
        for port in list_input_ports():
            guessed.update(match.controller.name for match in catalog.detect_controller(port))
        guessed.add(self.controller_image_view.current_controller_name())
        chosen = guessed & set(candidates)
        return chosen or set(candidates[:1])

    def _on_export_cheat_sheet(
        self, controllers: list[str] | None = None, path: Path | None = None
    ) -> Path | None:
        """File -> Export -> Cheat Sheet (PDF) (issue #182). `controllers`
        and `path` skip the dialogs (tests)."""
        if self.config is None:
            QMessageBox.information(self, "Cheat Sheet", "Open a mapping first.")
            return None
        if controllers is None:
            candidates = cheat_sheet.candidate_controllers(self.config)
            if not candidates:
                QMessageBox.information(
                    self, "Cheat Sheet", "No registered controller recognizes the triggers of this mapping."
                )
                return None
            names = [name for name, _count in candidates]
            dialog = CheatSheetExportDialog(candidates, self._cheat_sheet_preselection(names), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            controllers = dialog.selected_controllers()
        if path is None:
            stem = self.current_path.stem if self.current_path is not None else "mapping"
            path_str, _ = QFileDialog.getSaveFileName(
                self,
                "Export cheat sheet",
                str(user_paths.subfolder(user_paths.EXPORTS) / f"{stem}-cheat-sheet.pdf"),
                "PDF files (*.pdf)",
            )
            if not path_str:
                return None
            path = Path(path_str)
        sheets = cheat_sheet.build_sheets(self.config, controllers)
        source = self.current_path.name if self.current_path is not None else None
        try:
            pages = write_cheat_sheet_pdf(path, sheets, source)
        except OSError as exc:
            QMessageBox.warning(self, "Cheat Sheet", f"Could not write {path}:\n{exc}")
            return None
        self.statusBar().showMessage(f"Cheat sheet exported: {path} ({pages} page(s))")
        return path

    def _on_reveal_mapping(self) -> None:
        if self.current_path is not None:
            reveal_in_file_manager(self.current_path)

    def _run_in_tab(self, tab_key: str, handler) -> None:
        """Show the tab an action belongs to, then run it, so a File menu
        entry lands the user where its result appears."""
        self.left_tabs.setCurrentIndex(self._tab_indexes[tab_key])
        handler()

    def _mapping_start_dir(self) -> Path:
        settings = self._layout_settings()
        last_dir = settings.value(_LAST_DIR_SETTINGS_KEY, "", type=str) if settings is not None else ""
        return file_locations.mapping_start_dir(self.software_id, last_dir or None)

    def _remember_mapping(self, path: Path) -> None:
        self._recent_mappings = file_locations.push_recent(self._recent_mappings, path)
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue(_RECENT_SETTINGS_KEY, self._recent_mappings)
            settings.setValue(_LAST_DIR_SETTINGS_KEY, str(path.parent))
            settings.setValue(_LAST_MAPPING_SETTINGS_KEY, str(path))
            settings.setValue(_LAST_SOFTWARE_SETTINGS_KEY, self.software_id)
        self._rebuild_recent_menu()
        self._refresh_file_actions()

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        recents = file_locations.existing_recents(self._recent_mappings)
        for entry in recents:
            action = QAction(f"{Path(entry).name}  —  {Path(entry).parent}", self)
            action.triggered.connect(lambda _checked=False, e=entry: self._load_mapping_from_path(Path(e)))
            self._recent_menu.addAction(action)
        self._recent_menu.setEnabled(bool(recents))

    def _refresh_file_actions(self) -> None:
        """Enable the mapping file actions and refresh the Dashboard's
        "Your files" card from the current state."""
        has_file = self.current_path is not None
        backup = file_locations.backup_path(self.current_path) if has_file else None
        self._rollback_action.setEnabled(backup is not None and backup.is_file())
        self._compare_action.setEnabled(self.config is not None)
        self._compare_backup_action.setEnabled(self.config is not None and backup is not None and backup.is_file())
        self._reveal_action.setEnabled(has_file)
        self._cheat_sheet_action.setEnabled(self.config is not None)
        self.introduction_view.set_files_summary(
            mapping=self.current_path,
            backup=backup if backup is not None and backup.is_file() else None,
            sync_sets=[sync_set.label for sync_set in self.preferences.controller_sync_sets],
            recents=file_locations.existing_recents(self._recent_mappings),
        )

    def _on_validate(self) -> None:
        if self.config is None:
            return
        issues: list[ValidationIssue] = validate(self.config)
        self.issues_table.setRowCount(0)
        for issue in issues:
            row = self.issues_table.rowCount()
            self.issues_table.insertRow(row)
            severity_item = QTableWidgetItem(issue.severity)
            message_item = QTableWidgetItem(issue.message)
            location_item = QTableWidgetItem(issue.location)
            color = _SEVERITY_COLORS.get(issue.severity)
            if color is not None:
                for cell in (severity_item, message_item, location_item):
                    cell.setBackground(color)
            self.issues_table.setItem(row, 0, severity_item)
            self.issues_table.setItem(row, 1, message_item)
            self.issues_table.setItem(row, 2, location_item)

        errors = sum(1 for i in issues if i.severity == "error")
        warnings = sum(1 for i in issues if i.severity == "warning")
        infos = sum(1 for i in issues if i.severity == "info")
        self.statusBar().showMessage(f"Validation: {errors} error(s), {warnings} warning(s), {infos} info")
