from __future__ import annotations

import logging
import sys
from pathlib import Path

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
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
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

from djmidi import catalog, software
from djmidi.gui import layout as layout_mod
from djmidi.gui.controller_image_view import ControllerImageView
from djmidi.gui.controller_setup import ControllerSetupView
from djmidi.gui.controller_tree import CELL_KEY_ROLE, build_controller_columns
from djmidi.gui.deck_tree import build_deck_columns
from djmidi.gui.edit_panel import EditPanel
from djmidi.gui.helpful_notes_dialog import HelpfulNotesDialog
from djmidi.gui.introduction_view import IntroductionView
from djmidi.gui.layout_view import ControllerLayoutView
from djmidi.gui.live_monitor import LiveMonitorView
from djmidi.gui.mapping_group import MappingGroup
from djmidi.gui.metronome_view import MetronomeView
from djmidi.gui.midi_clock_view import MidiClockView
from djmidi.gui.midi_routing_view import MidiRoutingView
from djmidi.gui.preferences_dialog import PreferencesDialog
from djmidi.gui.safe_update_dialog import SafeUpdateDialog
from djmidi.gui.splitter_utils import replace_splitter
from djmidi.gui.theme import apply_theme
from djmidi.gui.tree_model import NODE_ROLE, build_channel_columns, relabel_item
from djmidi.integration_detection import (
    detect_controller_ports,
    detect_software_mapping,
)
from djmidi.logging_config import configure_logging, current_log_path
from djmidi.midi_io import MidiEvent
from djmidi.model import Control, MappingElement, MidiConfig
from djmidi.plugins import PluginPreferences, default_preferences_path
from djmidi.safe_update import prepare_update
from djmidi.validator import ValidationIssue, validate

_SEVERITY_COLORS = {
    "error": QColor(255, 200, 200),
    "warning": QColor(255, 235, 180),
    "info": QColor(225, 225, 225),
}

# The official docs catalog.py was transcribed from (see README.md "Technical References").
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

_LOCAL_HELP_DOCUMENTS = [
    ("Documentation Home", "docs/README.md"),
    ("Quickstart", "docs/quickstart.md"),
    ("User Guide", "docs/user-guide.md"),
    ("Screens and Layouts", "docs/screens-and-layouts.md"),
    ("Architecture", "docs/architecture.md"),
    ("End-to-End Examples", "docs/examples.md"),
    ("MIDI Clock Compatibility", "docs/midi-clock-compatibility.md"),
    ("Testing and Quality", "docs/testing-and-quality.md"),
    ("Quality Gates", "docs/quality-gates.md"),
    ("Build and Release", "docs/build-and-release.md"),
    ("Release Checklist", "docs/release-checklist.md"),
]

_LOCAL_CONTROLLER_DOCUMENTS = [
    ("Controller documentation index", "docs/controllers/README.md"),
    ("DDJ-XP2 MIDI Message List", "docs/controllers/ddj-xp2-midi-message-list-e1.pdf"),
    ("XDJ-XZ MIDI Message List", "docs/controllers/xdj-xz-midi-message-list-e3.pdf"),
    ("DDJ-1000 MIDI Message List", "docs/controllers/ddj-1000-midi-message-list-e1.pdf"),
    ("DDJ-FLX10 MIDI Message List", "docs/controllers/ddj-flx10-midi-message-list-e1.pdf"),
    ("DDJ-REV1 MIDI Message List", "docs/controllers/ddj-rev1-midi-message-list-e1.pdf"),
    ("Numark Mixtrack Pro FX User Guide", "docs/controllers/numark-mixtrack-pro-fx-user-guide-v1.2.pdf"),
    ("Hercules DJControl Inpulse 500 Product Sheet", "docs/controllers/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf"),
]


_LOGGER = logging.getLogger(__name__)


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
        # "Show all controllers" (View menu) bypasses the per-controller
        # Preferences enablement so the mapping tabs list every registered
        # controller again; the real state is restored from QSettings in
        # _restore_user_layout once the menu action exists.
        self._show_all_controllers = False
        self._apply_plugin_preferences()
        self._last_save_plan = None
        self.node_to_item: dict[int, object] = {}
        self.channel_proxies: list[QSortFilterProxyModel] = []
        self._channel_model_owner: dict[int, tuple[QTreeView, QSortFilterProxyModel]] = {}
        self._deck_tree_views: list[QTreeView] = []
        self._controller_tree_views: list[QTreeView] = []
        self._pair_splitters: list[QSplitter] = []
        self._pair_ratio_by_id: dict[int, float] = {}
        self._last_controller_detection: tuple[str, ...] = ()

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
        channel_layout.addWidget(self.channel_splitter)

        self.layout_view = ControllerLayoutView()
        self.layout_view.cellActivated.connect(lambda key: self._on_layout_cell_activated(key, "channel"))

        self.deck_columns_container = QWidget()
        deck_columns_layout = QVBoxLayout(self.deck_columns_container)
        deck_columns_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_splitter = QSplitter(Qt.Orientation.Horizontal)
        deck_columns_layout.addWidget(self.deck_splitter)

        self.deck_layout_view = ControllerLayoutView(show_deck_filter=True)
        self.deck_layout_view.cellActivated.connect(lambda key: self._on_layout_cell_activated(key, "deck"))

        self.controller_columns_container = QWidget()
        controller_columns_layout = QVBoxLayout(self.controller_columns_container)
        controller_columns_layout.setContentsMargins(0, 0, 0, 0)
        self.controller_splitter = QSplitter(Qt.Orientation.Horizontal)
        controller_columns_layout.addWidget(self.controller_splitter)

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

        self.controller_setup_view = ControllerSetupView()
        self.controller_setup_view.controllerApplied.connect(self._on_controller_applied)
        self.controller_setup_view.openMappingRequested.connect(self._on_open_mapping_requested)

        self.midi_routing_view = MidiRoutingView()
        self.midi_routing_view.set_routing_enabled(self.preferences.routing_enabled)
        self.midi_clock_view = MidiClockView(self.midi_routing_view.take_clock_panel())
        self.metronome_view = MetronomeView(
            all_rows_provider=self.controller_setup_view.session_rows,
            selected_rows_provider=self.controller_setup_view.selected_session_rows,
            session_name_provider=self.controller_setup_view.session_controller_name,
        )

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

        self.left_tabs = QTabWidget()
        self._tab_indexes = {
            "intro": self.left_tabs.addTab(self.introduction_view, "Dashboard"),
            "setup": self.left_tabs.addTab(self.controller_setup_view, "Controller Setup"),
            "images": self.left_tabs.addTab(self.controller_image_view, "Controller Images"),
            "channel": self.left_tabs.addTab(channel_pair, "By Channel"),
            "deck": self.left_tabs.addTab(deck_pair, "By Deck"),
            "controller": self.left_tabs.addTab(controller_pair, "By Controller"),
        }
        self.edit_panel = EditPanel(self.undo_stack, self._on_command_applied, self._on_group_edit_applied)

        self.issues_table = QTableWidget(0, 3)
        self.issues_table.setHorizontalHeaderLabels(["Severity", "Message", "Location"])
        self.issues_table.horizontalHeader().setStretchLastSection(True)
        self.issues_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.addWidget(self.edit_panel)
        self._right_splitter.addWidget(self.issues_table)
        self._right_splitter.setStretchFactor(0, 2)
        self._right_splitter.setStretchFactor(1, 1)

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

        self._build_menu()
        self.helpful_notes_dialog = HelpfulNotesDialog(self)
        self.helpful_notes_dialog.closedPersistently.connect(self._persist_helpful_notes_closed)
        self.helpful_notes_dialog.closedForSession.connect(self._allow_helpful_notes_next_start)
        self._restore_user_layout()
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

    def _restore_user_layout(self) -> None:
        settings = self._layout_settings()
        if settings is None:
            self._center_on_screen()
            return
        geometry = settings.value("window/geometry")
        state = settings.value("window/state")
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
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        self._rollback_action = QAction("Rollback Last Save", self)
        self._rollback_action.setEnabled(False)
        self._rollback_action.triggered.connect(self._on_rollback_last_save)
        file_menu.addAction(self._rollback_action)

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
        view_menu.addSeparator()
        self._show_all_controllers_action = QAction("Show all controllers", self, checkable=True)
        self._show_all_controllers_action.setChecked(self._show_all_controllers)
        self._show_all_controllers_action.setToolTip(
            "Ignore the per-controller Preferences enablement and list every registered controller"
        )
        self._show_all_controllers_action.toggled.connect(self._on_show_all_controllers_toggled)
        view_menu.addAction(self._show_all_controllers_action)

        settings_menu = self.menuBar().addMenu("&Settings")
        preferences_action = QAction("&Preferences...", self)
        preferences_action.triggered.connect(self._on_preferences)
        settings_menu.addAction(preferences_action)

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
        bar_layout.setContentsMargins(8, 4, 4, 4)
        bar_layout.setSpacing(6)
        label = QLabel(title)
        label.setStyleSheet("QLabel { font-weight: bold; }")
        bar_layout.addWidget(label)
        bar_layout.addStretch(1)

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

    def _on_preferences(self) -> None:
        dialog = PreferencesDialog(self.preferences, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.preferences.save(self.preferences_path)
            application = QApplication.instance()
            if application is not None:
                apply_theme(application, self.preferences.theme)
            self._apply_plugin_preferences()
            self._on_controller_applied(self.introduction_view._controller_combo.currentText())
            self.midi_routing_view.set_routing_enabled(self.preferences.routing_enabled)
            log_path = self.preferences.log_path or current_log_path()
            configure_logging(self.preferences.log_level, log_path)
            self.statusBar().showMessage("Preferences saved")

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
            "",
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

    def _load_mapping_from_path(self, path: Path) -> None:
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
        if detected is not None and detection.status == "match" and self.preferences.detection_policy == "suggest":
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
        _LOGGER.info("Loaded %d control(s) from %s (software=%s)", len(self.config.controls), path, selected.plugin_id)

    def _load_tree(self) -> None:
        assert self.config is not None
        self.introduction_view.set_loaded_config_info(self.current_path, len(self.config.controls))
        self._rebuild_channel_columns()
        self._refresh_layout_usage()
        self._refresh_deck_view()
        self.live_monitor_view.set_config(self.config)

    def _rebuild_channel_columns(self) -> None:
        assert self.config is not None
        self.channel_splitter = replace_splitter(self.channel_columns_container, self.channel_splitter)

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
        self.deck_splitter = replace_splitter(self.deck_columns_container, self.deck_splitter)
        self._deck_tree_views = []

        for _deck_id, model in build_deck_columns(self.config):
            view = QTreeView()
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
            hit_keys = {layout_mod.cell_key(hit) for hit in hits}
            for key in hit_keys:
                others = {other for other in hit_keys if other[0] != key[0]}
                if others:
                    linked_cells.setdefault(key, set()).update(others)
            for userio in control.userios:
                for mapping in userio.mappings:
                    if not mapping.deck_id:
                        continue
                    for hit in hits:
                        cell = usage.setdefault(layout_mod.cell_key(hit), {})
                        cell.setdefault(mapping.deck_id, set()).add(mapping.tag)
        self.layout_view.set_usage(usage, linked_cells)
        self.deck_layout_view.set_usage(usage, linked_cells)
        self.controller_layout_view.set_usage(usage, linked_cells)
        self.introduction_view.set_usage_summary(usage)
        self._refresh_controller_columns(usage)

    def _refresh_controller_columns(self, usage: dict[layout_mod.CellKey, dict[str, set[str]]]) -> None:
        self.controller_splitter = replace_splitter(self.controller_columns_container, self.controller_splitter)
        self._controller_tree_views = []

        for _controller, model, expand_flags in build_controller_columns(usage):
            view = QTreeView()
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
        """Apply the DJ booth palette to every mapping tree consistently."""
        view.setAlternatingRowColors(True)
        view.setIndentation(16)
        view.setAnimated(True)
        view.setStyleSheet(
            """
            QTreeView {
                background: #0e1724;
                alternate-background-color: #121e2d;
                color: #dce7f5;
                border: 1px solid #2b3b53;
                border-radius: 8px;
                padding: 5px;
                outline: none;
            }
            QTreeView::item {
                padding: 6px 8px;
                border-radius: 4px;
            }
            QTreeView::item:hover {
                background: #263b56;
                color: #ffffff;
            }
            QTreeView::item:selected {
                background: #d33c72;
                color: #ffffff;
            }
            QHeaderView::section {
                background: #202d42;
                color: #b9c9dc;
                border: 0;
                border-bottom: 1px solid #3a506d;
                padding: 7px;
                font-weight: 600;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #111a28;
                border: none;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #405875;
                border-radius: 5px;
                min-height: 24px;
                min-width: 24px;
            }
            QScrollBar::handle:hover {
                background: #00b9d9;
            }
            """
        )

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
                        layout_mod.cell_key(hit) == key
                        for hit in catalog.lookup(group.channel, group.event_type, group.control_no)
                    ):
                        self._select_model_index(view, index)
                        return True
        return False

    def _on_layout_cell_activated(self, key: tuple, source_tab: str = "channel") -> None:
        if self.config is None:
            return
        matches: list[Control] = []
        for control in self.config.controls:
            for hit in catalog.lookup(control.channel, control.event_type, control.control):
                if layout_mod.cell_key(hit) == key:
                    matches.append(control)
                    break
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

    def _update_layout_selection(self, channel: str | None, event_type: str | None, control_no: str | None) -> None:
        keys: set[layout_mod.CellKey] = set()
        if channel and event_type and control_no:
            keys = {layout_mod.cell_key(hit) for hit in catalog.lookup(channel, event_type, control_no)}
        self.layout_view.set_selected_keys(keys)
        self.deck_layout_view.set_selected_keys(keys)
        self.controller_layout_view.set_selected_keys(keys)

    def _on_live_midi_event(self, event: MidiEvent) -> None:
        self._update_layout_selection(event.channel, event.event_type, event.data1)
        if event.channel and event.event_type and event.data1:
            keys = {layout_mod.cell_key(hit) for hit in catalog.lookup(event.channel, event.event_type, event.data1)}
            for key in keys:
                self.layout_view.flash_key(key)
                self.deck_layout_view.flash_key(key)
                self.controller_layout_view.flash_key(key)

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
        self.layout_view.refresh_controllers()
        self.deck_layout_view.refresh_controllers()
        self.controller_layout_view.refresh_controllers()
        self.controller_image_view.refresh_controllers()
        self.introduction_view.refresh_controllers()
        if self.config is not None:
            self._refresh_layout_usage()
        self.statusBar().showMessage(f"'{name}' applied for this session.")

    def closeEvent(self, event) -> None:
        settings = self._layout_settings()
        if settings is not None:
            settings.setValue("window/geometry", self.saveGeometry())
            settings.setValue("window/state", self.saveState(1))
            self.midi_routing_view.save_state(settings)
            self.metronome_view.save_state(settings)
            settings.sync()
        self.live_monitor_view.shutdown()
        self.midi_routing_view.shutdown()
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
            "",
            f"{definition.name} files (*{' *'.join(definition.extensions)})",
        )
        if not path_str:
            return
        target = Path(path_str)
        if self._safe_save(target, definition):
            self.current_path = target
            self.statusBar().showMessage(f"Saved to {self.current_path}")

    def _safe_save(self, target: Path, definition) -> bool:
        _LOGGER.info("Preparing to save %s as %s", target, definition.plugin_id)
        try:
            plan = prepare_update(
                target,
                definition.exporter(self.config),
                definition.parser,
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
        self._rollback_action.setEnabled(plan.backup_path.exists())
        self.statusBar().showMessage(f"Saved to {target}")
        return True

    def _on_rollback_last_save(self) -> None:
        if self._last_save_plan is None:
            return
        try:
            self._last_save_plan.rollback()
        except OSError as exc:
            _LOGGER.exception("Failed to rollback save for %s", self._last_save_plan.path)
            QMessageBox.critical(self, "Failed to rollback save", str(exc))
            return
        self._rollback_action.setEnabled(False)
        self.statusBar().showMessage(f"Rolled back {self._last_save_plan.path}")

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
