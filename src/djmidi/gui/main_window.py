from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import PySide6
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QSettings,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    QUrl,
    qVersion,
)
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QUndoStack,
)

# Read or patched on this module by tests (issue #429 split).
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,  # noqa: F401
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from djmidi import (
    catalog,
    first_run,
    midi_macros,
    pad_colours,
    software,
    sync_store,
    user_paths,
)
from djmidi.catalog.library import (
    connected_library_profiles,
    install_library_profile,
    list_library_profiles,
)
from djmidi.catalog.profile import (
    USER_PLUGIN_PREFIX,
    find_user_profile_file,
    load_user_profiles,
)
from djmidi.controller_sync import (
    ControllerSyncSet,
    PlugInSyncTracker,
    SyncResult,
    normalize_scene,
    recorded_sync_sets,
    resolve_output_port,
    run_sync,
    scene_names,
    summarize_results,
)
from djmidi.first_run import FirstRunChoices
from djmidi.gui import jog as jog_mod  # noqa: F401
from djmidi.gui import layout as layout_mod
from djmidi.gui.accessibility import name_icon_buttons
from djmidi.gui.atelier_view import AtelierView
from djmidi.gui.controller_emulator import ControllerEmulatorView
from djmidi.gui.controller_image_view import ControllerImageView
from djmidi.gui.controller_setup import ControllerSetupView
from djmidi.gui.edit_panel import EditPanel
from djmidi.gui.first_run_wizard import FirstRunWizard
from djmidi.gui.function_search_view import FunctionSearchView
from djmidi.gui.geometry import (
    sync_profile_geometry,
)
from djmidi.gui.geometry_editor import GeometryEditorDialog
from djmidi.gui.hardware_session_dialog import HardwareSessionDialog
from djmidi.gui.helpful_notes_dialog import HelpfulNotesDialog
from djmidi.gui.introduction_view import IntroductionView
from djmidi.gui.layer_map_dialog import LayerMapDialog
from djmidi.gui.layout_view import ControllerLayoutView
from djmidi.gui.live_monitor import LiveMonitorView
from djmidi.gui.live_ready_dialog import LiveReadyDialog
from djmidi.gui.macro_editor import MacroManagerDialog
from djmidi.gui.macro_player import MacroPlayer
from djmidi.gui.main_window_parts import (
    DockWindowsMixin,
    LiveMidiMixin,
    MacrosMixin,
    MappingFilesMixin,
    MappingViewsMixin,
    ToolsMixin,
)
from djmidi.gui.main_window_parts._shared import (  # noqa: F401 -- re-exported
    _DISMISSED_LIBRARY_PROFILES_KEY,
    _LAST_ANNOUNCED_VERSION_SETTINGS_KEY,
    _LAST_DIR_SETTINGS_KEY,
    _LAST_DRAFT_SETTINGS_KEY,
    _LAST_MAPPING_SETTINGS_KEY,
    _LAST_SOFTWARE_SETTINGS_KEY,
    _LAST_UPDATE_CHECK_SETTINGS_KEY,
    _LOCAL_CONTROLLER_DOCUMENTS,
    _LOCAL_HELP_DOCUMENTS,
    _PERFORMANCE_TREE_RATIO,
    _PERFORMANCE_ZOOM_FACTOR,
    _PLUG_IN_POLL_MS,
    _RECENT_SETTINGS_KEY,
    _REFERENCE_LINKS,
    _SEVERITY_COLORS,
    _STARTUP_LIBRARY_SUGGEST_DELAY_MS,
    _STARTUP_SYNC_DELAY_MS,
    _STARTUP_UPDATE_CHECK_DELAY_MS,
    MAPPING_COLUMN_MIN_WIDTH,
    _detection_translate,
    _human_size,
    _live_ready_translate,
    _macro_translate,
    _refresh_tree_row_layout,
    _sync_translate,
    _validator_translate,
)
from djmidi.gui.mapping_diff_dialog import MappingDiffDialog
from djmidi.gui.metronome_view import MetronomeView
from djmidi.gui.midi_clock_view import MidiClockView
from djmidi.gui.midi_latency_dialog import MidiLatencyDialog
from djmidi.gui.midi_routing_view import MidiRoutingView
from djmidi.gui.mixxx_export_dialog import MixxxExportDialog
from djmidi.gui.music_library_view import MusicLibraryView
from djmidi.gui.nav_tabs import NavTabs
from djmidi.gui.preferences_dialog import PreferencesDialog
from djmidi.gui.profile_check_dialog import ProfileCheckDialog
from djmidi.gui.profile_library_dialog import ProfileLibraryDialog
from djmidi.gui.report_problem_dialog import ReportProblemDialog
from djmidi.gui.scroll_utils import AutoSizeScrollArea
from djmidi.gui.snapshots_dialog import SnapshotsDialog
from djmidi.gui.splitter_utils import scrollable_columns
from djmidi.gui.stage_window import StageWindow
from djmidi.gui.theme import apply_theme
from djmidi.gui.theme import signals as theme_signals
from djmidi.gui.update_notice import UpdateChecker
from djmidi.gui.whats_new_dialog import WhatsNewDialog
from djmidi.hardware_session import SESSION_FILE_NAME
from djmidi.integration_detection import (
    detect_controller_ports,
)
from djmidi.library.set_prep import SetTrack, set_track_from_row
from djmidi.logging_config import (
    configure_logging,
    current_log_path,
    default_log_path,
    enable_crash_log,
)
from djmidi.midi_io import MidiEvent, MidiMonitor, list_input_ports, list_output_ports
from djmidi.model import MidiConfig
from djmidi.plugins import PluginPreferences, default_preferences_path
from djmidi.problem_report import ReportContext, collect_context
from djmidi.stage import suggest_next_tracks
from djmidi.update_check import ReleaseInfo, current_version, is_check_due, is_newer

_LOGGER = logging.getLogger("djmidi.gui.main_window")


class MainWindow(DockWindowsMixin, MappingViewsMixin, LiveMidiMixin, MappingFilesMixin, MacrosMixin, ToolsMixin, QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.preferences_path = default_preferences_path()
        # Read before anything saves preferences: no file = a first launch,
        # which offers the first-run wizard (issue #251).
        self._preferences_existed = self.preferences_path.exists()
        # The build smoke test turns it off: its screenshot must not wait on a modal wizard.
        self.first_run_wizard_enabled = True
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
        sync_profile_geometry()
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
        # MIDI macros (issue #228): one file per macro in the Macros folder.
        self.macros: list[midi_macros.MidiMacro] = midi_macros.load_macros(user_paths.macros_dir())
        self._macro_player = MacroPlayer(parent=self)
        # Which side each toggle macro plays next (issue #367), session only.
        self._macro_toggles: dict[str, bool] = {}
        # Remembers recent presses so a trigger sequence can complete.
        self._macro_matcher = midi_macros.MacroTriggerMatcher()
        # Where Stage Mode's set panel stood when it last closed (issue #366).
        self._stage_set_index = 0
        self._snapshots_dialog: SnapshotsDialog | None = None
        self._mixxx_export_dialog: MixxxExportDialog | None = None
        self._stage_candidates: list[SetTrack] = []
        self._stage_candidates_key: tuple[int, int] | None = None
        # The open "Verify Profile" window (issue #364), fed every live event.
        self._profile_check_dialog: ProfileCheckDialog | None = None
        self._hardware_session_dialog: HardwareSessionDialog | None = None
        # Library profiles declined this session, when there are no QSettings (tests).
        self._session_dismissed_profiles: set[str] = set()
        self._macro_player.finished.connect(self._on_macro_finished)
        # The open Manage Macros dialog, fed live events for its Learn button
        # (issue #252); macros don't fire from the controller while it's open.
        self._macro_dialog: MacroManagerDialog | None = None
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
        # Stage Mode (issue #230): the full-screen emulator + compact monitor
        # window while it is open, else None. Session-only, like Performance
        # Mode -- never persisted.
        self._stage_window: StageWindow | None = None

        self.undo_stack = QUndoStack(self)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(self.tr("Filter by channel, control, event type, function, deck, slot..."))
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
        self.controller_image_view.placeControlsRequested.connect(lambda name: self.open_geometry_editor(name))

        self.live_monitor_view = LiveMonitorView(on_event=self._on_live_midi_event)
        self.live_monitor_view.syncRequested.connect(self._on_sync_controllers)
        self.live_monitor_view.batchStarted.connect(self._begin_live_batch)
        self.live_monitor_view.batchFinished.connect(self._end_live_batch)
        self._live_batch_views: list = []

        self.controller_setup_view = ControllerSetupView()
        self.controller_setup_view.set_default_file(self.preferences.controller_setup_default_file)
        self.controller_setup_view.controllerApplied.connect(self._on_controller_applied)
        self.controller_setup_view.openMappingRequested.connect(self._on_open_mapping_requested)
        self.controller_setup_view.syncSetSaveRequested.connect(self._on_sync_set_save_requested)

        self.midi_routing_view = MidiRoutingView()
        self.midi_routing_view.ensure_listening = self._ensure_learn_listening
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
        # Preview volume / auto-advance persist only in the real app (#210).
        self.music_library_view.audio_preview.set_settings(self._layout_settings())

        # The Atelier (issue #413, step 4): a controller's LED state per sync
        # scene, designed on its photo and stored as that scene's sync set.
        self.atelier_view = AtelierView(
            sync_set_provider=lambda controller, scene: self.preferences.sync_set_for(controller, scene),
            scene_names_provider=lambda: scene_names(self.preferences.controller_sync_sets),
            active_scene_provider=lambda: self.preferences.active_sync_scene,
        )
        self.atelier_view.saveRequested.connect(self._on_atelier_save_requested)
        self.atelier_view.sendRequested.connect(self._on_atelier_send_requested)
        self.atelier_view.sendAllRequested.connect(self._on_atelier_send_all_requested)
        self.atelier_view.macro_panel.macrosSaved.connect(self._on_atelier_macros_saved)
        self.atelier_view.libraryChanged.connect(self._on_controller_library_changed)
        self.atelier_view.macro_panel.set_macros(self.macros)
        # Step 6: remaps go through the MIDI Routing tab's routes.
        self.atelier_view.route_labels_provider = self.midi_routing_view.route_labels
        self.atelier_view.route_transform_provider = self.midi_routing_view.route_transform
        self.atelier_view.routeTransformChanged.connect(self.midi_routing_view.set_route_transform)
        self.midi_routing_view.routesChanged.connect(self.atelier_view.refresh_routes)
        self.atelier_view.refresh_routes()

        # Dashboard · Controller (Setup, Images, Studio, By…) · Music: the
        # nested tabs keep the flat page indexes the window used before.
        self.left_tabs = NavTabs()
        controller_tabs = self.left_tabs.add_group(self.tr("Controller"))
        self._tab_indexes = {"intro": self.left_tabs.add_page("intro", self.introduction_view, self.tr("Dashboard"))}
        # The group sits second, after the Dashboard.
        self.left_tabs.top.tabBar().moveTab(0, 1)
        self._tab_indexes["setup"] = self.left_tabs.add_page(
            "setup", self.controller_setup_view, self.tr("Setup"), controller_tabs
        )
        self._tab_indexes["images"] = self.left_tabs.add_page(
            "images", self.controller_image_view, self.tr("Images"), controller_tabs
        )
        self._tab_indexes["atelier"] = self.left_tabs.add_page(
            "atelier", self.atelier_view, self.tr("Studio"), controller_tabs
        )
        by_tabs = self.left_tabs.add_group(self.tr("By…"), controller_tabs)
        self._tab_indexes["channel"] = self.left_tabs.add_page("channel", channel_pair, self.tr("By Channel"), by_tabs)
        self._tab_indexes["deck"] = self.left_tabs.add_page("deck", deck_pair, self.tr("By Deck"), by_tabs)
        self._tab_indexes["controller"] = self.left_tabs.add_page(
            "controller", controller_pair, self.tr("By Controller"), by_tabs
        )
        self._tab_indexes["library"] = self.left_tabs.add_page("library", self.music_library_view, self.tr("Music"))
        self.left_tabs.setCurrentIndex(self._tab_indexes["intro"])
        self.edit_panel = EditPanel(
            self.undo_stack,
            self._on_command_applied,
            self._on_group_edit_applied,
            config_provider=lambda: self.config,
            ensure_listening=self._ensure_learn_listening,
            on_layers_changed=self._on_layers_changed,
        )

        self.issues_table = QTableWidget(0, 3)
        self.issues_table.setHorizontalHeaderLabels([self.tr("Severity"), self.tr("Message"), self.tr("Location")])
        self.issues_table.horizontalHeader().setStretchLastSection(True)
        self.issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # The validation area: the issue table under a strip with the two
        # checks (issue #254 added "Ready for live", a pre-gig report).
        self.validate_button = QPushButton(self.tr("Validate"))
        self.validate_button.setToolTip(self.tr("Check the mapping's structure and conflicts (Edit → Validate)."))
        self.validate_button.clicked.connect(self._on_validate)
        self.live_ready_button = QPushButton(self.tr("Ready for live…"))
        self.live_ready_button.setToolTip(
            self.tr("Before a gig: missing Play/Cue/Sync/Load per deck, conflicts, buttons without LED feedback.")
        )
        self.live_ready_button.clicked.connect(self._on_live_ready_check)
        validation_bar = QHBoxLayout()
        validation_bar.setContentsMargins(0, 0, 0, 0)
        validation_bar.addWidget(self.validate_button)
        validation_bar.addWidget(self.live_ready_button)
        validation_bar.addStretch(1)
        self._validation_area = QWidget()
        validation_layout = QVBoxLayout(self._validation_area)
        validation_layout.setContentsMargins(0, 0, 0, 0)
        validation_layout.addLayout(validation_bar)
        validation_layout.addWidget(self.issues_table, 1)
        self._live_ready_dialog: LiveReadyDialog | None = None

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
        self._right_splitter.addWidget(self._validation_area)
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
        self._layer_map_dialog: LayerMapDialog | None = None
        self.helpful_notes_dialog = HelpfulNotesDialog(self)
        self.helpful_notes_dialog.closedPersistently.connect(self._persist_helpful_notes_closed)
        self.helpful_notes_dialog.closedForSession.connect(self._allow_helpful_notes_next_start)
        self._restore_user_layout()
        name_icon_buttons(self)
        self.controller_setup_view.draftFileChanged.connect(self._remember_draft)
        self._prepare_reopen_last_files()
        if self._layout_settings() is not None:
            # Real app only, like reopening files: tests never touch MIDI here.
            QTimer.singleShot(_STARTUP_SYNC_DELAY_MS, self._start_controller_sync)
            # Controller-triggered macros (issue #252) need the inputs open.
            QTimer.singleShot(0, self._ensure_macro_triggers_listening)
            QTimer.singleShot(_STARTUP_LIBRARY_SUGGEST_DELAY_MS, self._suggest_library_profiles)
        self._update_checker = UpdateChecker(self)
        self._update_checker.finished.connect(self._on_update_check_finished)
        self.whats_new_dialog_factory = WhatsNewDialog
        self._update_label = QLabel()
        self._update_label.setTextFormat(Qt.TextFormat.RichText)
        self._update_label.setOpenExternalLinks(True)
        self._update_label.hide()
        self.statusBar().addPermanentWidget(self._update_label)
        if self._layout_settings() is not None and self.preferences.check_for_updates:
            # Real app only, like Sync at launch: tests never touch the network.
            QTimer.singleShot(_STARTUP_UPDATE_CHECK_DELAY_MS, self._check_for_updates_at_startup)
        QTimer.singleShot(0, self._initialize_pair_splitters)
        QTimer.singleShot(0, self._show_startup_dialog)
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
        detection = detect_controller_ports(port_names, translate=_detection_translate)
        best = detection.best
        if best is None:
            return
        if detection.needs_confirmation and self.preferences.detection_policy == "ask":
            answer = QMessageBox.question(
                self,
                self.tr("MIDI controller detected"),
                self.tr("Enable '{name}'?\n{score}% confidence — {reason}").format(
                    name=best.name, score=best.score, reason=best.reasons[0]
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        elif detection.needs_confirmation:
            self.statusBar().showMessage(
                self.tr("Detected controller suggestion: {name} ({score}% confidence).").format(
                    name=best.name, score=best.score
                )
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
            self.statusBar().showMessage(
                self.tr("Controller enabled: {name} ({score}% — {reason})").format(name=name, score=score, reason=reason)
            )

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
        file_menu = self.menuBar().addMenu(self.tr("&File"))

        open_action = QAction(self.tr("&Open Mapping..."), self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)
        self._recent_menu = file_menu.addMenu(self.tr("Open &Recent Mapping"))

        save_action = QAction(self.tr("&Save Mapping"), self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction(self.tr("Save Mapping &As..."), self)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        self._rollback_action = QAction(self.tr("Restore &Previous Version..."), self)
        self._rollback_action.setToolTip(self.tr("Replace the mapping with the version saved before its last save."))
        self._rollback_action.setEnabled(False)
        self._rollback_action.triggered.connect(self._on_rollback_last_save)
        file_menu.addAction(self._rollback_action)

        # Issue #189: what changed, trigger by trigger, instead of a raw XML diff.
        self._compare_action = QAction(self.tr("Co&mpare Mapping With..."), self)
        self._compare_action.setToolTip(self.tr("List what another mapping file does differently from the one open."))
        self._compare_action.setEnabled(False)
        self._compare_action.triggered.connect(self._on_compare_with_file)
        file_menu.addAction(self._compare_action)
        self._compare_backup_action = QAction(self.tr("Compare With Previous &Version"), self)
        self._compare_backup_action.setToolTip(self.tr("List what changed since the version saved before the last save."))
        self._compare_backup_action.setEnabled(False)
        self._compare_backup_action.triggered.connect(self._on_compare_with_backup)
        file_menu.addAction(self._compare_backup_action)

        self._save_snapshot_action = QAction(self.tr("Save S&napshot..."), self)
        self._save_snapshot_action.setToolTip(self.tr("Keep the mapping as it is now under a name, to compare or restore later."))
        self._save_snapshot_action.setEnabled(False)
        self._save_snapshot_action.triggered.connect(lambda _checked=False: self.save_snapshot())
        file_menu.addAction(self._save_snapshot_action)
        self._snapshots_action = QAction(self.tr("Snapshots..."), self)
        self._snapshots_action.setToolTip(self.tr("Compare, restore or delete this mapping's snapshots."))
        self._snapshots_action.setEnabled(False)
        self._snapshots_action.triggered.connect(lambda _checked=False: self.open_snapshots())
        file_menu.addAction(self._snapshots_action)

        reveal_label = (
            self.tr("Show Mapping in Finder") if sys.platform == "darwin" else self.tr("Show Mapping in File Manager")
        )
        self._reveal_action = QAction(reveal_label, self)
        self._reveal_action.setEnabled(False)
        self._reveal_action.triggered.connect(self._on_reveal_mapping)
        file_menu.addAction(self._reveal_action)

        file_menu.addSeparator()
        profile_menu = file_menu.addMenu(self.tr("&Controller Profile"))
        setup = self.controller_setup_view
        for label, handler in (
            (self.tr("New Draft"), setup._on_new_session_clicked),
            (self.tr("Open Draft..."), setup._on_load_session_clicked),
            (self.tr("Save Draft..."), setup._on_save_session_clicked),
            (self.tr("Learn Triggers from a Mapping..."), setup._on_import_xml_clicked),
            (self.tr("Install Profile"), setup._on_apply_clicked),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, h=handler: self._run_in_tab("setup", h))
            profile_menu.addAction(action)
        check_action = QAction(self.tr("Verify Profile with the Controller..."), self)
        check_action.triggered.connect(lambda: self.open_profile_check())
        profile_menu.addAction(check_action)
        place_action = QAction(self.tr("Place Controls on a Picture..."), self)
        place_action.triggered.connect(lambda: self.open_geometry_editor())
        profile_menu.addAction(place_action)
        library_action = QAction(self.tr("Install from Library..."), self)
        library_action.triggered.connect(lambda: self.open_profile_library())
        profile_menu.addAction(library_action)
        installed_action = QAction(self.tr("Show Installed Profiles"), self)
        installed_action.triggered.connect(self._on_reveal_installed_profiles)
        profile_menu.addAction(installed_action)

        library = self.music_library_view
        import_menu = file_menu.addMenu(self.tr("&Import"))
        for label, handler in (
            (self.tr("Serato Crates into the Music Library..."), library._on_import_serato_clicked),
            (self.tr("Traktor Playlists into the Music Library..."), library._on_import_traktor_clicked),
            (self.tr("Rekordbox USB Export into the Music Library..."), library._on_import_rekordbox_clicked),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, h=handler: self._run_in_tab("library", h))
            import_menu.addAction(action)
        export_menu = file_menu.addMenu(self.tr("&Export"))
        for label, handler in (
            (self.tr("Selected Playlist as a Serato Crate..."), library._on_export_serato_clicked),
            (self.tr("Selected Playlist as a Traktor Playlist..."), library._on_export_traktor_clicked),
        ):
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, h=handler: self._run_in_tab("library", h))
            export_menu.addAction(action)
        log_action = QAction(self.tr("Live Monitor Log..."), self)
        log_action.triggered.connect(self.live_monitor_view._save_log)
        export_menu.addAction(log_action)
        export_menu.addSeparator()
        self._cheat_sheet_action = QAction(self.tr("Cheat Sheet (PDF)..."), self)
        self._cheat_sheet_action.setToolTip(
            self.tr("Print each controller's photo with the function the loaded mapping binds to every control")
        )
        self._cheat_sheet_action.setEnabled(False)
        self._cheat_sheet_action.triggered.connect(lambda _checked=False: self._on_export_cheat_sheet())
        export_menu.addAction(self._cheat_sheet_action)
        self._cheat_sheet_web_action = QAction(self.tr("Cheat Sheet (Web Page)..."), self)
        self._cheat_sheet_web_action.setToolTip(
            self.tr("One offline web page to open on a phone or tablet: tap a control to see its functions")
        )
        self._cheat_sheet_web_action.setEnabled(False)
        self._cheat_sheet_web_action.triggered.connect(lambda _checked=False: self._on_export_cheat_sheet(web=True))
        export_menu.addAction(self._cheat_sheet_web_action)
        mixxx_export_action = QAction(self.tr("Mixxx Mapping from Profile..."), self)
        mixxx_export_action.setToolTip(self.tr("Write a Mixxx mapping for a controller profile, a function per button"))
        mixxx_export_action.triggered.connect(lambda _checked=False: self.open_mixxx_export())
        export_menu.addAction(mixxx_export_action)

        file_menu.addSeparator()
        backup_action = QAction(self.tr("&Back Up Workspace..."), self)
        backup_action.setToolTip(self.tr("Save your profiles, sync sets, drafts, preferences (and optionally the library index) in one zip."))
        backup_action.triggered.connect(self._on_backup_workspace)
        file_menu.addAction(backup_action)
        restore_action = QAction(self.tr("Restore &Workspace..."), self)
        restore_action.setToolTip(self.tr("Restore a workspace backup, after confirming what it overwrites."))
        restore_action.triggered.connect(self._on_restore_workspace)
        file_menu.addAction(restore_action)
        self._rebuild_recent_menu()

        edit_menu = self.menuBar().addMenu(self.tr("&Edit"))

        undo_action = self.undo_stack.createUndoAction(self, self.tr("&Undo"))
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)

        redo_action = self.undo_stack.createRedoAction(self, self.tr("&Redo"))
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        validate_action = QAction(self.tr("&Validate"), self)
        validate_action.triggered.connect(self._on_validate)
        edit_menu.addAction(validate_action)

        self._deck_copy_action = QAction(self.tr("Copy &Deck Mappings…"), self)
        self._deck_copy_action.setStatusTip(self.tr("Copy one deck's mappings onto another deck."))
        self._deck_copy_action.triggered.connect(lambda _checked=False: self.open_deck_copy())
        edit_menu.addAction(self._deck_copy_action)

        live_ready_action = QAction(self.tr("Ready for &Live…"), self)
        live_ready_action.setStatusTip(self.tr("Check the mapping before a gig (read-only)."))
        live_ready_action.triggered.connect(self._on_live_ready_check)
        edit_menu.addAction(live_ready_action)

        view_menu = self.menuBar().addMenu(self.tr("&View"))
        # Issue #222: one keyboard search over everything below. Ctrl maps to
        # Cmd on macOS; application-wide so it also works from a floating dock.
        self._command_palette_action = QAction(self.tr("Command Palette..."), self)
        self._command_palette_action.setShortcut(QKeySequence("Ctrl+K"))
        self._command_palette_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._command_palette_action.setToolTip(self.tr("Search every action, tab, mapping function and library track"))
        self._command_palette_action.triggered.connect(lambda _checked=False: self.open_command_palette())
        view_menu.addAction(self._command_palette_action)
        view_menu.addSeparator()
        helpful_notes_action = QAction(self.tr("Helpful Notes..."), self)
        helpful_notes_action.triggered.connect(self._show_helpful_notes)
        view_menu.addAction(helpful_notes_action)
        view_menu.addSeparator()
        for key in ("monitor", "routing", "clock", "metronome"):
            dock = self._tool_docks[key]
            view_menu.addAction(dock.toggleViewAction())
        self._new_emulator_action = QAction(self.tr("New Controller Emulator…"), self)
        self._new_emulator_action.setToolTip(
            self.tr(
                "Open another Controller Emulator window -- several may be open at "
                "once, each bound to its own controller"
            )
        )
        self._new_emulator_action.triggered.connect(lambda: self._create_emulator_instance())
        view_menu.addAction(self._new_emulator_action)
        self._latency_action = QAction(self.tr("MIDI Latency Test…"), self)
        self._latency_action.setToolTip(
            self.tr("Measure MIDI round-trip latency through a port or device that echoes what it receives")
        )
        self._latency_action.triggered.connect(self._on_midi_latency_test)
        view_menu.addAction(self._latency_action)
        self._layer_map_action = QAction(self.tr("Layer Map…"), self)
        self._layer_map_action.setToolTip(
            self.tr(
                "What each control of a controller does in every layer (normal, SHIFT, "
                "pad modes), with the free combinations highlighted"
            )
        )
        self._layer_map_action.setEnabled(False)
        self._layer_map_action.triggered.connect(lambda _checked=False: self._on_show_layer_map())
        view_menu.addAction(self._layer_map_action)
        view_menu.addSeparator()
        self._show_all_controllers_action = QAction(self.tr("Show all controllers"), self, checkable=True)
        self._show_all_controllers_action.setChecked(self._show_all_controllers)
        self._show_all_controllers_action.setToolTip(
            self.tr("Ignore the per-controller Preferences enablement and list every registered controller")
        )
        self._show_all_controllers_action.toggled.connect(self._on_show_all_controllers_toggled)
        view_menu.addAction(self._show_all_controllers_action)

        view_menu.addSeparator()
        self._performance_mode_action = QAction(self.tr("Performance Mode"), self, checkable=True)
        self._performance_mode_action.setToolTip(
            self.tr(
                "Hide the mapping tree and enlarge the schematic layout for on-stage use "
                "(session-only, not remembered across restarts)"
            )
        )
        self._performance_mode_action.toggled.connect(self._on_performance_mode_toggled)
        view_menu.addAction(self._performance_mode_action)
        self._stage_mode_action = QAction(self.tr("Stage Mode"), self, checkable=True)
        self._stage_mode_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self._stage_mode_action.setToolTip(
            self.tr(
                "Full-screen, high-contrast Controller Emulator and compact Live Monitor "
                "for on-stage use -- Esc to exit (session-only, not remembered across restarts)"
            )
        )
        self._stage_mode_action.toggled.connect(self._on_stage_mode_toggled)
        view_menu.addAction(self._stage_mode_action)

        # MIDI macros (issue #228): one entry per macro, each with its own
        # shortcut, rebuilt by _rebuild_macro_menu whenever the list changes.
        self._macro_menu = self.menuBar().addMenu(self.tr("&Macros"))
        self._macro_actions: list[QAction] = []
        self._rebuild_macro_menu()

        # Preferences moved out of the menu bar (issue #137) into an
        # always-visible corner icon instead of a menu someone has to open
        # first to discover it. Kept as an instance attribute -- unlike
        # addWidget() on a layout, setCornerWidget() doesn't reliably keep
        # PySide6's Python-side wrapper alive on its own, so a purely local
        # variable here gets garbage-collected out from under the C++ widget.
        self._preferences_button = QPushButton("⚙")
        self._preferences_button.setFixedSize(28, 28)
        self._preferences_button.setProperty("compact", True)
        self._preferences_button.setToolTip(self.tr("Preferences..."))
        self._preferences_button.clicked.connect(lambda: self._on_preferences())
        # One-click controller initialization (Sync), beside the gear so it's
        # reachable from every tab; Live Monitor carries the same action.
        self._sync_button = QPushButton(self.tr("⟳ Sync"))
        self._sync_button.setFixedHeight(28)
        self._sync_button.setToolTip(
            self.tr("Sync controllers: send each connected controller its recorded initialization set")
        )
        self._sync_button.clicked.connect(self._on_sync_controllers)
        # Active sync scene (issue #188): which named set ⟳ Sync, launch and
        # plug-in sync send, and which scene ● Rec records into.
        self._sync_scene_combo = QComboBox()
        self._sync_scene_combo.setFixedHeight(28)
        self._sync_scene_combo.setMaximumWidth(140)
        self._sync_scene_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._sync_scene_combo.setToolTip(
            self.tr(
                "Sync scene: ⟳ Sync, launch and plug-in sync send each controller its set for this scene "
                "(or its Default set when it has none); ● Rec records into it"
            )
        )
        self._refresh_sync_scene_combo()
        self._sync_scene_combo.activated.connect(self._on_sync_scene_activated)
        # Record the controllers' setup in one click: listen to every MIDI
        # input while checked, save one sync set per controller on release.
        self._record_button = QPushButton(self.tr("● Rec"))
        self._record_button.setCheckable(True)
        self._record_button.setFixedHeight(28)
        self._record_button.setToolTip(
            self.tr(
                "Record controller setup: press the controls to send at initialization, then click "
                "again to save them as each controller's sync set (played by ⟳ Sync and at launch)"
            )
        )
        self._record_button.toggled.connect(self._on_record_toggled)
        self._record_monitor = MidiMonitor()
        self._record_events: list[MidiEvent] = []
        # Inputs the Live Monitor already holds while recording: their events
        # come from its stream (_on_live_midi_event), never a second open.
        self._record_shared_ports: frozenset[str] = frozenset()
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

        help_menu = self.menuBar().addMenu(self.tr("&Help"))
        documentation_menu = help_menu.addMenu(self.tr("Project Documentation"))
        for title, relative_path in _LOCAL_HELP_DOCUMENTS:
            action = QAction(self.tr(title), self)
            action.triggered.connect(
                lambda checked=False, p=relative_path: self._open_local_help(p)
            )
            documentation_menu.addAction(action)

        controller_menu = help_menu.addMenu(self.tr("Controller References"))
        for title, relative_path in _LOCAL_CONTROLLER_DOCUMENTS:
            # Only the index is marked; document names are official titles.
            action = QAction(self.tr(title), self)
            action.triggered.connect(
                lambda checked=False, p=relative_path: self._open_local_help(p)
            )
            controller_menu.addAction(action)

        help_menu.addSeparator()
        online_menu = help_menu.addMenu(self.tr("Official and External References"))
        for title, url in _REFERENCE_LINKS:
            action = QAction(title, self)
            action.triggered.connect(lambda checked=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            online_menu.addAction(action)

        help_menu.addSeparator()
        self._first_run_action = QAction(self.tr("First-Run &Setup..."), self)
        self._first_run_action.setToolTip(
            self.tr("Detect your controllers, open your Serato mapping and record a controller sync set.")
        )
        self._first_run_action.triggered.connect(lambda: self._on_first_run_wizard())
        help_menu.addAction(self._first_run_action)
        self._hardware_session_action = QAction(self.tr("&Hardware Session..."), self)
        self._hardware_session_action.setToolTip(
            self.tr("The checks still waiting for real controllers and DJ software, with a report to share.")
        )
        self._hardware_session_action.triggered.connect(lambda: self.open_hardware_session())
        help_menu.addAction(self._hardware_session_action)
        self._check_updates_action = QAction(self.tr("Check for &Updates..."), self)
        self._check_updates_action.setToolTip(self.tr("Ask GitHub whether a newer DJ MIDI Studio release exists."))
        self._check_updates_action.triggered.connect(self._on_check_for_updates)
        help_menu.addAction(self._check_updates_action)
        self._report_problem_action = QAction(self.tr("&Report a Problem..."), self)
        self._report_problem_action.setToolTip(
            self.tr(
                "Preview a bug report with your app version, system and recent log lines, "
                "then open it as a pre-filled GitHub issue."
            )
        )
        self._report_problem_action.triggered.connect(self._on_report_problem)
        help_menu.addAction(self._report_problem_action)

    def _show_helpful_notes(self) -> None:
        self.helpful_notes_dialog.show()
        self.helpful_notes_dialog.raise_()
        self.helpful_notes_dialog.activateWindow()

    def _show_startup_dialog(self) -> None:
        """The first-run wizard on a genuine first launch, else Helpful Notes."""
        if self._should_show_first_run_wizard():
            self._on_first_run_wizard()
        else:
            self._show_helpful_notes_if_enabled()

    def _should_show_first_run_wizard(self) -> bool:
        """Real app only (tests and doc captures have no settings), and only
        without a preferences file and before the wizard was finished/skipped."""
        settings = self._layout_settings()
        if settings is None or not self.first_run_wizard_enabled:
            return False
        done = settings.value(first_run.WIZARD_DONE_SETTINGS_KEY, False, type=bool)
        return first_run.should_show_wizard(self._preferences_existed, bool(done))

    def _on_first_run_wizard(self, wizard: FirstRunWizard | None = None) -> FirstRunChoices | None:
        """Runs the wizard (Help → First-Run Setup, or a first launch) and
        applies its choices; finished or skipped, it won't open by itself again."""
        if wizard is None:
            wizard = FirstRunWizard(list_input_ports, parent=self)
        accepted = wizard.exec() == QDialog.DialogCode.Accepted
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue(first_run.WIZARD_DONE_SETTINGS_KEY, True)
            settings.sync()
        if not accepted:
            return None
        choices = wizard.choices()
        self._apply_first_run_choices(choices)
        return choices

    def _apply_first_run_choices(self, choices: FirstRunChoices) -> None:
        if choices.controller:
            self.introduction_view.set_controller(choices.controller)
        if choices.mapping is not None:
            # Opening only reads the file; the Serato folder is never written
            # unless the user saves the mapping themselves.
            self._load_mapping_from_path(choices.mapping, software_id="serato")
        if choices.record_sync_set and not self._record_button.isChecked():
            self._record_button.setChecked(True)

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

    @staticmethod
    def _resource_root() -> Path:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", Path.cwd()))
        return Path(__file__).resolve().parents[3]

    def _open_local_help(self, relative_path: str) -> None:
        path = self._resource_root() / relative_path
        if not path.exists():
            QMessageBox.warning(self, self.tr("Documentation unavailable"), str(path))
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
            # Matched on the untranslated key (tab data), not the shown title.
            for index in range(dialog.tabs.count()):
                if dialog.tabs.tabBar().tabData(index) == tab:
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
            log_path = configure_logging(self.preferences.log_level, log_path)
            enable_crash_log(log_path, only_if_enabled=True)
            if self._layout_settings() is not None:
                self._update_plug_in_watch()
            if self.preferences.auto_start_live_monitor and self.config is not None:
                # Turning the setting on with a mapping already loaded starts
                # monitoring immediately, matching "Enable MIDI routing
                # policies" applying right away above -- no-op if already running.
                self.live_monitor_view.ensure_monitoring_started()
            self._refresh_file_actions()
            self.statusBar().showMessage(self.tr("Preferences saved"))

    def _on_sync_controllers(self) -> list[SyncResult]:
        """Sends each controller its sync set for the active scene."""
        sync_sets = self.preferences.active_sync_sets()
        if not sync_sets:
            recorded = (
                self.tr(
                    "No initialization set is recorded for the scene \"{scene}\" and no controller has a Default set."
                ).format(scene=self.preferences.active_sync_scene)
                if self.preferences.controller_sync_sets
                else self.tr("No initialization set is recorded yet.")
            )
            QMessageBox.information(
                self,
                self.tr("No controller sync set"),
                recorded
                + "\n\n"
                + self.tr(
                    "Click ● Rec, press the controls to send at initialization, then click ■ Stop -- or, in "
                    "Controller Setup, start learning, press the controls, then click \"Save as controller sync set\"."
                ),
            )
            return []
        ports = list_output_ports()
        results = run_sync(self._aim_sync_sets(sync_sets, ports), ports)
        self.statusBar().showMessage(summarize_results(results, _sync_translate), 10_000)
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
        results = run_sync(self._aim_sync_sets(sync_sets, ports), ports)
        self.statusBar().showMessage(summarize_results(results, _sync_translate), 10_000)
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
        due = self._plug_in_tracker.due(self._aim_sync_sets(self.preferences.active_sync_sets(), ports), ports)
        if not due:
            return []
        results = run_sync(due, ports)
        self.statusBar().showMessage(self.tr("Plugged in -- ") + summarize_results(results, _sync_translate), 10_000)
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
            self.statusBar().showMessage(self.tr("Already checking for updates..."), 5_000)
            return
        self.statusBar().showMessage(self.tr("Checking for updates..."))

    def _problem_report_context(self) -> ReportContext:
        """Facts for Help → Report a Problem: versions, the plugins enabled in
        Preferences and the log tail — never mapping or library content."""
        controllers = [
            definition.name
            for definition in catalog.all_controller_definitions()
            if self.preferences.is_enabled(definition.plugin_id or definition.name)
        ]
        softwares = [
            definition.name
            for definition in software.all_definitions()
            if self.preferences.is_enabled(definition.plugin_id)
        ]
        log_path = current_log_path() or default_log_path()
        return collect_context(
            app_version=current_version(),
            qt_version=f"{qVersion()} (PySide6 {PySide6.__version__})",
            controller_plugins=controllers,
            software_plugins=softwares,
            log_path=log_path if log_path.exists() else None,
        )

    def _on_midi_latency_test(self) -> None:
        # Non-modal and kept alive: a test can run while the user keeps working,
        # and reopening shows the same dialog with its last result.
        dialog = getattr(self, "_latency_dialog", None)
        if dialog is None:
            dialog = self._latency_dialog = MidiLatencyDialog(self)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_report_problem(self) -> None:
        dialog = ReportProblemDialog(self._problem_report_context(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.last_inlined:
            self.statusBar().showMessage(
                self.tr("Problem report copied to the clipboard and opened as a GitHub issue."), 10_000
            )
        else:
            self.statusBar().showMessage(
                self.tr("The report was too long for the link: it's on your clipboard — paste it into the issue."),
                15_000,
            )

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
            self._update_label.setText(
                '<a href="{url}">{text}</a>'.format(
                    url=release.url, text=self.tr("Update available: v{version}").format(version=version)
                )
            )
            self._update_label.setToolTip(
                self.tr("Open the {tag} release page in your browser").format(tag=release.tag)
            )
            self._update_label.show()
            self.statusBar().showMessage(
                self.tr("DJ MIDI Studio v{version} is available (you have v{local}).").format(
                    version=version, local=local
                ),
                15_000,
            )
            if not manual:
                self._maybe_show_whats_new(release)
        if not manual:
            return
        title = self.tr("Check for Updates")
        if release is None:
            QMessageBox.information(
                self,
                title,
                self.tr("Couldn't reach GitHub to check for a new version. Check your connection and try again."),
            )
        elif newer:
            answer = QMessageBox.question(
                self,
                title,
                self.tr(
                    "DJ MIDI Studio v{version} is available (you have v{local}).\n\n"
                    "Open the release page to download it?"
                ).format(version=".".join(map(str, release.version)), local=local),
            )
            if answer == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(release.url))
        elif local is None:
            QMessageBox.information(
                self,
                title,
                self.tr("The latest release is {tag}, but this copy's own version is unknown.").format(
                    tag=release.tag
                ),
            )
        else:
            QMessageBox.information(
                self,
                title,
                self.tr("You're up to date (v{local}, latest release {tag}).").format(local=local, tag=release.tag),
            )

    def _maybe_show_whats_new(self, release: ReleaseInfo) -> bool:
        """Shows the full release notes once per newly detected version
        (issue #409), from a silent background check -- a manual check
        already asks its own question. False when there is nothing new to
        announce (already shown for this version, or no settings to
        remember it in, i.e. the test suite)."""
        settings = self._layout_settings()
        if settings is None:
            return False
        version = ".".join(map(str, release.version))
        if settings.value(_LAST_ANNOUNCED_VERSION_SETTINGS_KEY, "") == version:
            return False
        settings.setValue(_LAST_ANNOUNCED_VERSION_SETTINGS_KEY, version)
        self.whats_new_dialog_factory(release, self).exec()
        return True

    def _on_record_toggled(self, recording: bool) -> None:
        if recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        self._record_events = []
        # Windows lets one client only open a MIDI input: record the ports the
        # Live Monitor already listens on from its stream (like MIDI Learn)
        # and open only the others.
        shared = list(self.live_monitor_view.listening_input_ports())
        self._record_shared_ports = frozenset(shared)
        opened, failed = list(shared), []
        # Two identical units can share a port name on macOS; it opens once.
        for name in dict.fromkeys(list_input_ports()):
            if name in self._record_shared_ports:
                continue
            try:
                self._record_monitor.open_input(name)
            except Exception as exc:  # noqa: BLE001 - one busy port must not block the others
                _LOGGER.warning("Record: cannot open MIDI input %r: %s", name, exc)
                failed.append(name)
                continue
            opened.append(name)
        if not opened:
            QMessageBox.warning(
                self,
                self.tr("Cannot record"),
                self.tr(
                    "None of the MIDI inputs could be opened ({ports}): another program, or the "
                    "Live Monitor, may be using them."
                ).format(ports=", ".join(failed))
                if failed
                else self.tr("No MIDI input could be opened: is a controller connected?"),
            )
            self._record_shared_ports = frozenset()
            self._record_button.blockSignals(True)
            self._record_button.setChecked(False)
            self._record_button.blockSignals(False)
            return
        self._record_button.setText(self.tr("■ Stop"))
        self._relayout_menu_corner()
        # Issue #307: the recording depends on which ports the Live Monitor
        # holds right now, so freeze them until ■ Stop (an auto-start on a
        # mapping load waits for it too).
        self.live_monitor_view.set_locked(
            self.tr("● Rec is recording: the Live Monitor keeps its current inputs until you click ■ Stop")
        )
        self._record_timer.start()
        _LOGGER.info("Record: listening on %s", opened)
        self.statusBar().showMessage(
            self.tr(
                "Recording on {count} MIDI input(s): press the controls to send at initialization, "
                "then click ■ Stop (macros and MIDI Learn are paused meanwhile)"
            ).format(count=len(opened))
            + (self.tr(" (couldn't open: {ports})").format(ports=", ".join(failed)) if failed else "")
        )

    def _poll_recording(self) -> None:
        self._record_events.extend(self._record_monitor.poll())

    def _stop_recording(self) -> list[ControllerSyncSet]:
        self._record_timer.stop()
        self._poll_recording()
        self._record_monitor.close_all()
        self._record_shared_ports = frozenset()
        self.live_monitor_view.set_locked(None)
        self._record_button.setText(self.tr("● Rec"))
        self._relayout_menu_corner()
        scene = self.preferences.active_sync_scene
        recorded, collapsed_by_port = recorded_sync_sets(self._record_events, self._controller_name_for_port)
        self._record_events = []
        # Only recognized controllers: a loopback bus (IAC Driver) or another
        # program's virtual port would otherwise be replayed at every launch.
        # An unknown device records through Controller Setup instead.
        ignored = [sync_set.output_port for sync_set in recorded if not self._controller_name_for_port(sync_set.output_port)]
        recorded = [sync_set for sync_set in recorded if sync_set.output_port not in ignored]
        if ignored:
            _LOGGER.info("Record: ignored unrecognized port(s) %s", ignored)
        if not recorded:
            self.statusBar().showMessage(
                self.tr("Recording stopped: no MIDI note/CC received from a recognized controller, nothing saved")
                + (
                    self.tr(" (ignored: {ports}; use Controller Setup for these)").format(ports=", ".join(ignored))
                    if ignored
                    else ""
                ),
                10_000,
            )
            return []
        sync_sets = [sync_set.in_scene(scene) for sync_set in recorded]
        stored = {
            sync_set.controller: existing
            for sync_set in sync_sets
            if (existing := self.preferences.sync_set_for(sync_set.controller, scene)) is not None
        }
        if stored:
            reply = QMessageBox.question(
                self,
                self.tr("Replace sync sets"),
                self.tr("Replace the sync set(s) already stored for:")
                + "\n"
                + "\n".join(
                    self.tr("{name} ({count} message(s))").format(name=existing.label, count=len(existing.messages))
                    for existing in stored.values()
                )
                + "\n\n"
                + self.tr("No keeps them; what you recorded on other controllers is saved either way."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                # Declining keeps those sets; it's no reason to drop the
                # recording of a controller that had none.
                sync_sets = [sync_set for sync_set in sync_sets if sync_set.controller not in stored]
                if not sync_sets:
                    self.statusBar().showMessage(
                        self.tr("Recording discarded: the stored sync set(s) were kept"), 10_000
                    )
                    return []
        for sync_set in sync_sets:
            self.preferences.set_sync_set(sync_set)
        self._save_preferences()
        collapsed = sum(collapsed_by_port.get(sync_set.output_port, 0) for sync_set in sync_sets)
        self.statusBar().showMessage(
            self.tr("Sync set(s) saved: ")
            + ", ".join(
                self.tr("{name} ({count} msg)").format(name=sync_set.label, count=len(sync_set.messages))
                for sync_set in sync_sets
            )
            + (self.tr("; {count} CC message(s) collapsed to their last value").format(count=collapsed) if collapsed else "")
            + (self.tr(" (ignored unrecognized: {ports})").format(ports=", ".join(ignored)) if ignored else ""),
            10_000,
        )
        return sync_sets

    @staticmethod
    def _controller_name_for_port(port: str) -> str:
        """The catalog controller behind a MIDI port, or "" (a recorded set
        is then named after the port). Only a match on the controller's own
        name or port names counts: a manufacturer-only match (score 75) says
        who made the device, not which one it is -- "Pioneer DJ DDJ-400"
        would otherwise be filed as the DDJ-XP2's set, replacing it and, while
        that port is gone, sending its messages to a connected DDJ-XP2."""
        matches = catalog.detect_controller(port, include_disabled=True)
        # Disabled plugins count too: the name is stored, and must not change
        # (a second set for the same device) when one is switched off.
        exact = [match for match in matches if match.score >= 100]
        return exact[0].controller.name if exact else ""

    def _aim_sync_sets(self, sync_sets: list[ControllerSyncSet], ports: list[str]) -> list[ControllerSyncSet]:
        """The sets to send, each one its names can't place among ``ports``
        aimed at the single connected output detected as its catalog
        controller. A set records its input port, but Windows numbers the
        input and output lists separately and renumbers them as devices come
        and go ("CMD Micro 0" recorded, "CMD Micro 2" now), some devices name
        the two differently, and a catalog name may not appear in the port
        name at all ("Behringer CMD Micro"). Stored sets stay as recorded."""
        aimed = []
        for sync_set in sync_sets:
            if resolve_output_port(sync_set, ports) is None:
                same = [port for port in ports if self._controller_name_for_port(port) == sync_set.controller]
                if len(same) == 1:
                    sync_set = ControllerSyncSet(sync_set.controller, same[0], sync_set.messages, sync_set.scene)
            aimed.append(sync_set)
        return aimed

    def _relayout_menu_corner(self) -> None:
        """QMenuBar sizes its corner widget when it is set, shown or the bar
        resized -- not when the corner's contents grow ("● Rec" → "■ Stop", a
        longer scene name) -- so set it again; otherwise a neighbour stays
        squeezed below its minimum until the window is next resized."""
        corner = getattr(self, "_menu_corner", None)
        if corner is not None:
            self.menuBar().setCornerWidget(corner, Qt.Corner.TopRightCorner)

    def _on_sync_set_save_requested(self, sync_set: ControllerSyncSet) -> None:
        # Controller Setup records into the active scene, like ● Rec.
        sync_set = sync_set.in_scene(self.preferences.active_sync_scene)
        existing = self.preferences.sync_set_for(sync_set.controller, sync_set.scene)
        if existing is not None:
            reply = QMessageBox.question(
                self,
                self.tr("Replace sync set"),
                self.tr(
                    "Replace the {old}-message sync set already stored for {name} with this {new}-message recording?"
                ).format(old=len(existing.messages), name=sync_set.label, new=len(sync_set.messages)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.preferences.set_sync_set(sync_set)
        self._save_preferences()
        self.statusBar().showMessage(
            self.tr("Sync set saved for {name} ({count} message(s))").format(
                name=sync_set.label, count=len(sync_set.messages)
            ),
            10_000,
        )

    def _on_pad_colours_save_requested(self, controller: str, colours: dict) -> ControllerSyncSet | None:
        """A Controller Emulator's painted pad colours (issue #232): merged
        into the controller's sync set for the active scene -- each pad's
        previous colour message is replaced, everything else in the set is
        kept, so no confirmation is needed."""
        palette = pad_colours.palette_for(controller)
        if palette is None or not colours:
            return None
        scene = self.preferences.active_sync_scene
        sync_set = pad_colours.merge_into_sync_set(
            palette, self.preferences.sync_set_for(controller, scene), colours, scene
        )
        self.preferences.set_sync_set(sync_set)
        self._save_preferences()
        self._reload_emulator_pad_colours()
        self.statusBar().showMessage(
            self.tr("{pads} pad colour(s) saved in the sync set for {name} ({count} message(s))").format(
                pads=len(colours), name=sync_set.label, count=len(sync_set.messages)
            ),
            10_000,
        )
        return sync_set

    def _on_atelier_save_requested(self, sync_set: ControllerSyncSet) -> None:
        """The Atelier's scene, stored as that controller's sync set for its
        scene (the set is rebuilt from the scene, keeping every message the
        Atelier didn't recognise, so no confirmation is needed)."""
        self.preferences.set_sync_set(sync_set)
        self._save_preferences()
        self._reload_emulator_pad_colours()
        self.statusBar().showMessage(
            self.tr("Atelier scene saved in the sync set for {name} ({count} message(s))").format(
                name=sync_set.label, count=len(sync_set.messages)
            ),
            10_000,
        )

    def _on_atelier_send_requested(self, sync_set: ControllerSyncSet | None) -> list[SyncResult]:
        """Sends the Atelier's scene to its controller now, unsaved."""
        if sync_set is None:
            return []
        ports = list_output_ports()
        results = run_sync(self._aim_sync_sets([sync_set], ports), ports)
        self.statusBar().showMessage(summarize_results(results, _sync_translate), 10_000)
        return results

    def _on_atelier_send_all_requested(self, sync_sets: list[ControllerSyncSet]) -> list[SyncResult]:
        """Sends the Atelier's scene to every controller it covers (issue #427)."""
        sets = [sync_set for sync_set in sync_sets if sync_set is not None]
        if not sets:
            return []
        ports = list_output_ports()
        results = run_sync(self._aim_sync_sets(sets, ports), ports)
        self.statusBar().showMessage(summarize_results(results, _sync_translate), 10_000)
        return results

    def _on_atelier_macros_saved(self, macros: list) -> None:
        """The Atelier's Macros tab saved (issue #428): stored like Manage Macros."""
        self.macros = list(macros)
        midi_macros.save_macros(user_paths.macros_dir(), self.macros)
        self._rebuild_macro_menu()
        self._ensure_macro_triggers_listening()
        self.statusBar().showMessage(self.tr("{count} macro(s) saved").format(count=len(self.macros)), 5000)

    def _reload_emulator_pad_colours(self) -> None:
        """Every open Controller Emulator re-reads its saved pad colours."""
        for dock in self._emulator_docks.values():
            view = dock.widget()
            if isinstance(view, ControllerEmulatorView):
                view.reload_pad_colours()

    _NEW_SCENE_DATA = "\x00new-scene"

    def _refresh_sync_scene_combo(self) -> None:
        """Fills the scene combo: every scene in use (plus the active one,
        which may not have a set yet), then "New scene…"."""
        combo = self._sync_scene_combo
        active = self.preferences.active_sync_scene
        if hasattr(self, "atelier_view"):
            self.atelier_view.refresh_scenes()
        combo.blockSignals(True)
        combo.clear()
        for name in scene_names(self.preferences.controller_sync_sets, active):
            combo.addItem(name, name)
        combo.insertSeparator(combo.count())
        combo.addItem(self.tr("New scene…"), self._NEW_SCENE_DATA)
        combo.setCurrentIndex(max(combo.findData(active), 0))
        combo.blockSignals(False)
        self._relayout_menu_corner()

    def _on_sync_scene_activated(self, index: int) -> None:
        data = self._sync_scene_combo.itemData(index)
        if data == self._NEW_SCENE_DATA:
            name, accepted = QInputDialog.getText(
                self, self.tr("New sync scene"), self.tr("Scene name (e.g. Tek, DnB, Warm-up):")
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
        if changed:
            self._reload_emulator_pad_colours()
        message = self.tr("Sync scene: {scene}").format(scene=scene)
        results: list[SyncResult] = []
        if changed and self.preferences.sync_on_scene_switch:
            sync_sets = self.preferences.active_sync_sets()
            if sync_sets:
                ports = list_output_ports()
                results = run_sync(self._aim_sync_sets(sync_sets, ports), ports)
                message += f" -- {summarize_results(results, _sync_translate)}"
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
            self.tr("Performance mode on — tree hidden, layout enlarged")
            if checked
            else self.tr("Performance mode off")
        )

    def _on_stage_mode_toggled(self, checked: bool) -> None:
        """Open or close the full-screen Stage Mode window (issue #230). It
        shows the controller of the first open emulator, else the one the
        Controller Images tab shows, and starts live monitoring (a no-op when a
        session already runs) since a stage view without live input would
        be empty."""
        if checked:
            if self._stage_window is not None:
                return
            controller = next(
                (view.current_controller() for view in self._emulator_views()),
                self.controller_image_view.current_controller_name(),
            )
            window = StageWindow(
                config_provider=lambda: self.config,
                initial_controller=controller,
                set_provider=self._stage_set,
                set_index=self._stage_set_index,
                suggestion_provider=self._stage_suggestions,
            )
            window.closed.connect(self._on_stage_window_closed)
            self._stage_window = window
            window.showFullScreen()
            self.live_monitor_view.ensure_monitoring_started()
            self.statusBar().showMessage(self.tr("Stage mode on — press Esc to exit"))
        elif self._stage_window is not None:
            # close() emits closed -> _on_stage_window_closed, which clears
            # the reference and unchecks the action (already unchecked here).
            self._stage_window.close()

    def _stage_set(self):
        """The set prepared in Music Library → Set, for Stage Mode (issue
        #366); opens the library index if the tab wasn't shown yet."""
        try:
            self.music_library_view.ensure_open()
        except Exception:
            _LOGGER.warning("Could not open the music library for Stage Mode's set", exc_info=True)
            return (), ()
        panel = self.music_library_view.set_panel
        return panel.tracks, panel.transitions

    def _stage_suggestions(self, current: SetTrack, set_paths: set[str]) -> list[SetTrack]:
        """Library tracks that mix after `current`, within the set panel's own
        BPM tolerance. The rows' SetTracks are cached per loaded row list."""
        rows = self.music_library_view.table_model.rows()
        key = (len(rows), id(self.music_library_view.table_model._rows))
        if self._stage_candidates_key != key:
            self._stage_candidates = [set_track_from_row(row) for row in rows]
            self._stage_candidates_key = key
        tolerance = self.music_library_view.set_panel.tolerance_spin.value()
        return suggest_next_tracks(current, self._stage_candidates, set_paths, tolerance)

    def _on_stage_window_closed(self) -> None:
        window = self._stage_window
        self._stage_window = None
        if window is not None:
            # Reopening Stage Mode this session resumes at the same track.
            self._stage_set_index = window.set_index
        if window is not None:
            window.deleteLater()
        if self._stage_mode_action.isChecked():
            self._stage_mode_action.setChecked(False)
        self.statusBar().showMessage(self.tr("Stage mode off"))

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
            self.tr("Showing all controllers") if checked else self.tr("Showing enabled controllers only")
        )

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
        # The enabled-controller filter was computed from the controllers
        # registered at startup; recompute it so a new one isn't filtered out.
        self._apply_plugin_preferences()
        sync_profile_geometry()
        layout_mod.clear_reverse_lookup_cache()
        self.atelier_view.refresh_controllers()
        layout_mod.clear_label_to_key_cache()
        self.layout_view.refresh_controllers()
        self.deck_layout_view.refresh_controllers()
        self.controller_layout_view.refresh_controllers()
        self.controller_image_view.refresh_controllers()
        self.introduction_view.refresh_controllers()
        for view in self._emulator_views():
            view.refresh_controllers()
        if self.config is not None:
            self._refresh_layout_usage()
        self.statusBar().showMessage(self.tr("'{name}' applied for this session.").format(name=name))

    def open_mixxx_export(self, controller: str | None = None) -> MixxxExportDialog:
        """File → Export → Mixxx Mapping from Profile…: one non-modal window,
        preselecting the controller Controller Images shows."""
        if self._mixxx_export_dialog is not None:
            self._mixxx_export_dialog.raise_()
            return self._mixxx_export_dialog
        names = sorted(catalog.CONTROLLER_NAMES, key=str.casefold)
        dialog = MixxxExportDialog(
            names,
            initial=controller or self.controller_image_view.current_controller_name(),
            parent=self,
            save_dir=user_paths.subfolder(user_paths.EXPORTS),
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(lambda _obj=None: setattr(self, "_mixxx_export_dialog", None))
        self._mixxx_export_dialog = dialog
        dialog.show()
        return dialog

    def open_profile_check(self, controller: str | None = None) -> ProfileCheckDialog:
        """File → Controller Profile → Verify Profile with the Controller…:
        one non-modal window, preselecting the controller detected on an
        input (else the one Controller Images shows)."""
        if self._profile_check_dialog is not None:
            self._profile_check_dialog.raise_()
            self._profile_check_dialog.activateWindow()
            return self._profile_check_dialog
        ports = list(dict.fromkeys(list_input_ports()))
        if controller is None:
            detected = [match.controller.name for port in ports for match in catalog.detect_controller(port)]
            controller = detected[0] if detected else self.controller_image_view.current_controller_name()
        dialog = ProfileCheckDialog(
            catalog.CONTROLLER_NAMES,
            ports,
            self,
            ensure_listening=self._ensure_learn_listening,
            initial=controller,
            reports_dir=user_paths.subfolder(user_paths.EXPORTS),
            output_ports=list(dict.fromkeys(list_output_ports())),
            judge_delay_ms=800,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_profile_check_closed)
        dialog.libraryChanged.connect(self._on_controller_library_changed)
        self._profile_check_dialog = dialog
        dialog.show()
        return dialog

    def _on_controller_library_changed(self, controller: str) -> None:
        """A capture or verified LED was recorded: every view showing that
        controller's features re-reads them (issue #451)."""
        if self.sender() is not self.atelier_view:
            self.atelier_view.refresh_library(controller)
        for view in self._emulator_views():
            card = view.feature_card
            if card.feature is not None and card.feature.controller == controller:
                card.refresh()
        dialog = self._profile_check_dialog
        if dialog is not None and self.sender() is not dialog and dialog.controller == controller:
            dialog.refresh_audit()

    def _on_profile_check_closed(self, _result: int = 0) -> None:
        self._profile_check_dialog = None

    def open_hardware_session(self) -> HardwareSessionDialog:
        """Help → Hardware Session… (issue #426): one non-modal window, its
        session saved in the workspace's Exports folder."""
        if self._hardware_session_dialog is not None:
            self._hardware_session_dialog.raise_()
            self._hardware_session_dialog.activateWindow()
            return self._hardware_session_dialog
        dialog = HardwareSessionDialog(
            user_paths.subfolder(user_paths.EXPORTS) / SESSION_FILE_NAME,
            self,
            ensure_listening=self._ensure_learn_listening,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._on_hardware_session_closed)
        self._hardware_session_dialog = dialog
        dialog.show()
        return dialog

    def _on_hardware_session_closed(self, _result: int = 0) -> None:
        self._hardware_session_dialog = None

    def open_geometry_editor(self, name: str | None = None, dialog_factory=None) -> GeometryEditorDialog | None:
        """Place a profile's controls on a picture (issue #363). Without a
        name: the controller Controller Images shows when it is an installed
        profile, else a choice among the installed profiles."""
        installed = sorted(
            definition.name
            for definition in catalog.all_controller_definitions()
            if (definition.plugin_id or "").startswith(USER_PLUGIN_PREFIX)
        )
        if name is None:
            shown = self.controller_image_view.current_controller_name()
            if shown in installed:
                name = shown
            elif not installed:
                QMessageBox.information(
                    self,
                    self.tr("Place controls"),
                    self.tr(
                        "Only an installed profile can get a picture and a layout: install one from "
                        "File → Controller Profile → Install from Library…, or make one in Controller Setup."
                    ),
                )
                return None
            else:
                name, accepted = QInputDialog.getItem(
                    self, self.tr("Place controls"), self.tr("Profile:"), installed, 0, False
                )
                if not accepted:
                    return None
        path = find_user_profile_file(name, user_paths.controllers_dir())
        if path is None:
            QMessageBox.warning(
                self, self.tr("Place controls"), self.tr("No installed profile file found for '{name}'.").format(name=name)
            )
            return None
        dialog = (dialog_factory or GeometryEditorDialog)(name, path, self)
        dialog.saved.connect(self._on_geometry_saved)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
        return dialog

    def _on_geometry_saved(self, name: str) -> None:
        self._on_controller_applied(name)
        self.controller_image_view.set_controller(name)
        self.statusBar().showMessage(self.tr("Layout of '{name}' saved.").format(name=name), 8000)

    def open_profile_library(self, dialog_factory=None) -> ProfileLibraryDialog:
        """File → Controller Profile → Install from Library…: the dialog is
        non-modal; each install refreshes the controller lists at once."""
        factory = dialog_factory or ProfileLibraryDialog
        dialog = factory(list_library_profiles(), user_paths.controllers_dir(), self)
        dialog.installed.connect(self._on_library_profile_installed)
        dialog.uninstalled.connect(self._on_library_profile_uninstalled)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
        return dialog

    def _on_library_profile_installed(self, name: str) -> None:
        self._on_controller_applied(name)
        self.statusBar().showMessage(self.tr("'{name}' installed from the profile library.").format(name=name), 8000)

    def _on_library_profile_uninstalled(self, name: str) -> None:
        self._on_controller_applied(name)
        self.statusBar().showMessage(self.tr("'{name}' uninstalled.").format(name=name), 8000)

    def _dismissed_library_profiles(self) -> set[str]:
        settings = self._layout_settings()
        if settings is None:
            return set(self._session_dismissed_profiles)
        value = settings.value(_DISMISSED_LIBRARY_PROFILES_KEY, [])
        return {str(item) for item in (value if isinstance(value, list) else [value]) if item}

    def _dismiss_library_profiles(self, names: list[str]) -> None:
        dismissed = self._dismissed_library_profiles() | set(names)
        self._session_dismissed_profiles = dismissed
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue(_DISMISSED_LIBRARY_PROFILES_KEY, sorted(dismissed))

    def _suggest_library_profiles(self, ports: list[str] | None = None, ask=None) -> list[str]:
        """At launch: a connected controller with an uninstalled library
        profile (a DDJ-400 plugged in) gets one question offering to install
        it. "No" is remembered per profile, so it is asked once. Returns the
        names installed. Skipped while another window (the first-run wizard)
        is modal."""
        if ask is None and QApplication.activeModalWidget() is not None:
            return []
        dismissed = self._dismissed_library_profiles()
        matches = [
            (profile, port)
            for profile, port in connected_library_profiles(
                list_input_ports() if ports is None else ports, list_library_profiles()
            )
            if profile.name not in dismissed
        ]
        if not matches:
            return []
        lines = "\n".join(f"• {profile.name} ({port})" for profile, port in matches)
        question = self.tr(
            "These connected controllers have a ready-made profile in the library:\n\n{lines}\n\n"
            "Install them? (File → Controller Profile → Install from Library… does it later too.)"
        ).format(lines=lines)
        if ask is None:
            answer = QMessageBox.question(self, self.tr("Controller profiles available"), question)
            accepted = answer == QMessageBox.StandardButton.Yes
        else:
            accepted = ask(question)
        if not accepted:
            self._dismiss_library_profiles([profile.name for profile, _port in matches])
            return []
        installed: list[str] = []
        for profile, _port in matches:
            try:
                install_library_profile(profile, user_paths.controllers_dir())
            except (OSError, ValueError, TypeError) as exc:
                _LOGGER.warning("Could not install library profile %s: %s", profile.name, exc)
                continue
            installed.append(profile.name)
            self._on_controller_applied(profile.name)
        if installed:
            self.statusBar().showMessage(
                self.tr("Installed from the profile library: {names}").format(names=", ".join(installed)), 8000
            )
        return installed

    def closeEvent(self, event) -> None:
        if self._record_button.isChecked():
            reply = QMessageBox.question(
                self,
                self.tr("Recording in progress"),
                self.tr("A controller sync recording is in progress. Save it before quitting?"),
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Discard:
                # Stopped below without saving anything.
                self._record_events = []
                self._record_button.blockSignals(True)
                self._record_button.setChecked(False)
                self._record_button.blockSignals(False)
            else:
                self._record_button.setChecked(False)  # stops and saves
        if self._stage_window is not None:
            self._stage_window.close()
        self._record_timer.stop()
        self._plug_in_timer.stop()
        self._record_monitor.close_all()
        self._macro_player.stop_all()  # a waiting macro holds its port open (#314)
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

    def _save_preferences(self) -> None:
        """preferences.json, plus the Sync folder mirroring the sync sets --
        and what shows them: the scene combo and the Dashboard's "Your files"
        card (both built with the menu)."""
        self.preferences.save(self.preferences_path)
        sync_store.save_sync_sets(user_paths.sync_dir(), self.preferences.controller_sync_sets)
        if hasattr(self, "_sync_scene_combo"):
            self._refresh_sync_scene_combo()
            self._refresh_file_actions()

    # --- MIDI macros (issue #228) ---------------------------------------------

    def _on_manage_macros(self, dialog_factory=None) -> bool:
        """Opens the macro editor; on OK saves the macros and rebuilds the menu."""
        factory = dialog_factory or MacroManagerDialog
        dialog = factory(
            self.macros,
            list_output_ports(),
            list(self.preferences.controller_sync_sets),
            self._reserved_shortcuts(),
            parent=self,
            ensure_listening=self._ensure_learn_listening,
        )
        self._macro_dialog = dialog
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._macro_dialog = None
            # Presses made while editing (Learn, tests) never start a sequence.
            self._macro_matcher.reset()
        if not accepted:
            return False
        self.macros = list(dialog.edited_macros())
        midi_macros.save_macros(user_paths.macros_dir(), self.macros)
        self._rebuild_macro_menu()
        self.atelier_view.macro_panel.set_macros(self.macros)
        self._ensure_macro_triggers_listening()
        self.statusBar().showMessage(self.tr("{count} macro(s) saved").format(count=len(self.macros)), 5000)
        return True

    def _play_macro(self, name: str) -> midi_macros.MacroResult | None:
        macro = next((macro for macro in self.macros if macro.name == name), None)
        if macro is None:
            return None
        return self._macro_player.play(self._macro_to_play(macro), list_output_ports())

    def _play_triggered_macros(self, event: MidiEvent) -> list[str]:
        """Plays every macro this controller press fires -- a one-press
        trigger, or the last press of a trigger sequence, among the macros
        allowed in the active sync scene; returns their names. A press a
        playing macro's wait step was waiting for resumes it instead."""
        if self._macro_player.feed_event(event):
            return []
        scene = self.preferences.active_sync_scene
        fired = self._macro_matcher.feed([m for m in self.macros if m.plays_in_scene(scene)], event)
        if fired:
            ports = list_output_ports()
            for macro in fired:
                self._macro_player.play(self._macro_to_play(macro), ports)
        return [macro.name for macro in fired]

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

    # --- command palette (issue #222) -----------------------------------------

