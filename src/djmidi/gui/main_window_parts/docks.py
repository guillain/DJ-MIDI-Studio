"""MainWindow, part: Tool docks and Controller Emulator windows: title bars, the ☰ window menu (maximize, reduce, snap), creating / closing / restoring emulator instances.

A mixin of `djmidi.gui.main_window.MainWindow` (issue #429); its strings keep the
"MainWindow" translation context."""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import (
    QCoreApplication,
    QSettings,
    Qt,
)
from PySide6.QtGui import (
    QAction,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStyle,
    QWidget,
)

from djmidi.gui.accessibility import name_icon_buttons
from djmidi.gui.controller_emulator import ControllerEmulatorView


class DockWindowsMixin:
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

    def _create_tool_docks(self) -> dict[str, QDockWidget]:
        definitions = {
            "monitor": (QCoreApplication.translate("MainWindow", "Live Monitor"), self.live_monitor_view),
            "routing": (QCoreApplication.translate("MainWindow", "MIDI Routing"), self.midi_routing_view),
            "clock": (QCoreApplication.translate("MainWindow", "MIDI Clock"), self.midi_clock_view),
            "metronome": (QCoreApplication.translate("MainWindow", "Metronome"), self.metronome_view),
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
        close_button.setToolTip(QCoreApplication.translate("MainWindow", "Close"))
        close_button.clicked.connect(dock.close)
        bar_layout.addWidget(close_button)
        name_icon_buttons(bar)
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
        button.setToolTip(QCoreApplication.translate("MainWindow", "Window"))

        menu = QMenu(button)
        reduce_action = QAction(QCoreApplication.translate("MainWindow", "Reduce to title bar"), button)
        maximize_action = QAction(QCoreApplication.translate("MainWindow", "Maximize"), button)
        menu.addAction(reduce_action)
        menu.addAction(maximize_action)
        menu.addSeparator()
        snap_specs = [
            (QCoreApplication.translate("MainWindow", "Snap left"), Qt.DockWidgetArea.LeftDockWidgetArea),
            (QCoreApplication.translate("MainWindow", "Snap right"), Qt.DockWidgetArea.RightDockWidgetArea),
            (QCoreApplication.translate("MainWindow", "Snap to top"), Qt.DockWidgetArea.TopDockWidgetArea),
            (QCoreApplication.translate("MainWindow", "Snap to bottom"), Qt.DockWidgetArea.BottomDockWidgetArea),
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
            dock._dj_reduce_action.setText(QCoreApplication.translate("MainWindow", "Expand"))
        else:
            widget.show()
            dock.setMaximumHeight(16777215)
            dock._dj_reduced = False
            dock._dj_reduce_action.setText(QCoreApplication.translate("MainWindow", "Reduce to title bar"))

    def _toggle_dock_maximized(self, dock: QDockWidget) -> None:
        if not dock._dj_maximized:
            if not dock.isFloating():
                dock.setFloating(True)
            dock._dj_premax_geometry = dock.geometry()
            dock.showMaximized()
            dock._dj_maximized = True
            dock._dj_maximize_action.setText(QCoreApplication.translate("MainWindow", "Restore"))
        else:
            dock.showNormal()
            if dock._dj_premax_geometry is not None:
                dock.setGeometry(dock._dj_premax_geometry)
            dock._dj_maximized = False
            dock._dj_maximize_action.setText(QCoreApplication.translate("MainWindow", "Maximize"))

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

    def _update_dock_button(self, button: QPushButton, floating: bool) -> None:
        if floating:
            button.setText(QCoreApplication.translate("MainWindow", "Dock"))
            button.setToolTip(QCoreApplication.translate("MainWindow", "Attach back into the main window"))
        else:
            button.setText(QCoreApplication.translate("MainWindow", "Undock"))
            button.setToolTip(QCoreApplication.translate("MainWindow", "Detach into its own window"))

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
        view = ControllerEmulatorView(
            config_provider=lambda: self.config,
            initial_controller=controller,
            sync_set_provider=lambda name: self.preferences.sync_set_for(name, self.preferences.active_sync_scene),
        )
        view.padColoursSaveRequested.connect(self._on_pad_colours_save_requested)
        dock = QDockWidget(QCoreApplication.translate("MainWindow", "Controller Emulator"), self)
        dock.setObjectName(f"{instance_id}Dock")
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        dock.setWidget(view)
        dock.setTitleBarWidget(self._build_emulator_dock_title_bar(instance_id, QCoreApplication.translate("MainWindow", "Controller Emulator"), dock))
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
        close_button.setToolTip(QCoreApplication.translate("MainWindow", "Close"))
        close_button.clicked.connect(lambda: self._close_emulator_instance(instance_id))
        bar_layout.addWidget(close_button)
        name_icon_buttons(bar)
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

    def _emulator_views(self) -> list[ControllerEmulatorView]:
        """Every live Controller Emulator: each emulator dock's view plus
        the Stage Mode window's, so live MIDI reaches all of them alike."""
        views = [
            view for dock in self._emulator_docks.values()
            if isinstance(view := dock.widget(), ControllerEmulatorView)
        ]
        if self._stage_window is not None:
            views.append(self._stage_window.emulator_view)
        return views
