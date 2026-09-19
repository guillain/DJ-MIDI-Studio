from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui.controller_image_view import CONTROLLERS_DIR, image_for_controller
from djmidi.gui.layout import CellKey
from djmidi.gui.theme import colors as theme_colors
from djmidi.gui.theme import current_mode as theme_current_mode
from djmidi.gui.theme import signals as theme_signals

# Fixed per-software accent, one pair per theme mode (light/dark) so each
# stays legible against both backgrounds -- same convention as theme.py's
# own "clock_accent" token, kept local here since only the Dashboard's
# loaded-file badge needs it (issue #121). Any other/unknown software plugin
# falls back to the theme's own neutral "hint_text" shade rather than
# guessing a color for a controller-agnostic future plugin.
_SOFTWARE_BADGE_COLORS: dict[str, dict[str, str]] = {
    "serato": {"dark": "#e8792a", "light": "#b8560f"},
    "traktor": {"dark": "#29c1d1", "light": "#0a7fa0"},
}


class IntroductionView(QWidget):
    """Home tab presenting known controllers, app context, and quick navigation."""

    drillDownRequested = Signal(str, str)  # target tab key, controller name
    toolRequested = Signal(str)  # independent tool dock key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._usage_summary: dict[str, tuple[int, int, int]] = {}
        self._card_stats: dict[str, QLabel] = {}
        self._availability_labels: dict[str, QLabel] = {}
        self._midi_port_names: list[str] = []
        self._loaded_software_id: str | None = None

        title = QLabel("DJ MIDI Studio")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")

        self._description_label = QLabel()
        self._description_label.setWordWrap(True)

        self._loaded_file_label = QLabel("Loaded file: none")
        self._loaded_file_label.setWordWrap(True)
        self._loaded_file_label.setFrameShape(QFrame.Shape.StyledPanel)
        # Bold, per-software-colored name (issue #121) -- a small always-
        # visible marker next to the loaded-file line, since the one-time
        # "which software?" dialog at File -> Open is otherwise the only
        # place this ever showed. Empty/hidden until a file with a known
        # software plugin is loaded.
        self._software_badge_label = QLabel()
        self._software_badge_label.setStyleSheet("font-weight: 600;")
        self._software_badge_label.hide()
        loaded_file_row = QHBoxLayout()
        loaded_file_row.addWidget(self._loaded_file_label, 1)
        loaded_file_row.addWidget(self._software_badge_label, 0)

        self._update_description(None)

        self._controller_combo = QComboBox()
        self._controller_combo.addItems(catalog.CONTROLLER_NAMES)

        catalog_box = QGroupBox("Known controllers")
        catalog_layout = QVBoxLayout(catalog_box)
        catalog_layout.addWidget(QLabel("Active controller for drill-down:"))
        catalog_layout.addWidget(self._controller_combo)
        self._known_count_label = QLabel()
        self._known_list_label = QLabel()
        self._known_list_label.setWordWrap(True)
        catalog_layout.addWidget(self._known_count_label)
        catalog_layout.addWidget(self._known_list_label)

        self._controller_tabs = QTabWidget()
        self._controller_tabs.setDocumentMode(True)
        self._controller_tabs.setTabPosition(QTabWidget.TabPosition.North)

        cards_box = QGroupBox("Controller overview")
        cards_box_layout = QVBoxLayout(cards_box)
        cards_box_layout.addWidget(self._controller_tabs)

        tools_box = QGroupBox("MIDI tools")
        tools_layout = QVBoxLayout(tools_box)
        monitor_button = QPushButton("Open Live Monitor")
        monitor_button.clicked.connect(lambda: self.toolRequested.emit("monitor"))
        routing_button = QPushButton("Open MIDI Routing")
        routing_button.clicked.connect(lambda: self.toolRequested.emit("routing"))
        clock_button = QPushButton("Open MIDI Clock")
        clock_button.clicked.connect(lambda: self.toolRequested.emit("clock"))
        metronome_button = QPushButton("Open Metronome")
        metronome_button.clicked.connect(lambda: self.toolRequested.emit("metronome"))
        tools_layout.addWidget(monitor_button)
        tools_layout.addWidget(routing_button)
        tools_layout.addWidget(clock_button)
        tools_layout.addWidget(metronome_button)

        info = QLabel(
            "Tip: after applying a controller from Controller Setup, "
            "it appears immediately across this session's views."
        )
        info.setWordWrap(True)
        info.setFrameShape(QFrame.Shape.StyledPanel)

        overview_header = QHBoxLayout()
        overview_header.setSpacing(10)
        overview_header.addWidget(catalog_box, 3)
        overview_header.addWidget(tools_box, 1)

        # The Controller overview card (a controller photo + stats + drill-down
        # buttons) is tall enough that below ~750px window height the bottom
        # of this tab -- the drill-down buttons especially -- fell off the
        # visible area with no way to reach it (issue #19). Wrap the whole
        # tab in a scroll area, same fix as Controller Setup's io_row.
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(title)
        layout.addWidget(self._description_label)
        layout.addLayout(loaded_file_row)
        layout.addLayout(overview_header)
        layout.addWidget(cards_box)
        layout.addWidget(info)
        # No trailing addStretch: the QScrollArea (widgetResizable) already
        # stretches `content` to fill the viewport when it's taller than the
        # content, and a stretch here would only inflate the scrolled height.

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.refresh_controllers()
        # refresh_midi_availability only reruns on live_monitor_view
        # .portNamesChanged (MainWindow.__init__), a relatively rare event
        # (plugging/unplugging a device) -- reconnected here too so its two
        # "not checked"/"not detected" labels (previously a literal
        # hardcoded "#777") don't sit stale until the next port change. A
        # persistent singleton for the app's session, so a plain
        # bound-method connection is enough -- no stale-QObject risk.
        theme_signals.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, *_args: object) -> None:
        self.refresh_midi_availability(self._midi_port_names)
        if self._loaded_software_id is not None:
            self._restyle_software_badge()

    def refresh_controllers(self) -> None:
        current = self._controller_combo.currentText()
        self._controller_combo.blockSignals(True)
        self._controller_combo.clear()
        self._controller_combo.addItems(catalog.CONTROLLER_NAMES)
        restored = self._controller_combo.findText(current)
        self._controller_combo.setCurrentIndex(max(restored, 0))
        self._controller_combo.blockSignals(False)

        names = list(catalog.CONTROLLER_NAMES)
        self._known_count_label.setText(f"{len(names)} registered controller(s)")
        self._known_list_label.setText(", ".join(names) if names else "(no registered controllers)")
        self._rebuild_controller_cards(names)

    def refresh_midi_availability(self, port_names: list[str]) -> None:
        """Update the presence indicator for each registered controller."""
        self._midi_port_names = list(port_names)
        detected = {
            match.controller.name
            for port_name in port_names
            for match in catalog.detect_controller(port_name)
        }
        for controller, label in self._availability_labels.items():
            if not port_names:
                label.setText("MIDI: not checked")
                label.setStyleSheet(f"color: {theme_colors()['disabled_text']}; font-weight: 600;")
            elif controller in detected:
                label.setText("MIDI: available")
                label.setStyleSheet("color: #16803c; font-weight: 600;")
            else:
                label.setText("MIDI: not detected")
                label.setStyleSheet(f"color: {theme_colors()['disabled_text']}; font-weight: 600;")

    def set_controller(self, controller: str) -> bool:
        """Select a controller in the Dashboard without opening a drill-down."""
        if self._controller_combo.findText(controller) < 0:
            return False
        self._controller_combo.setCurrentText(controller)
        return True

    def _update_description(self, software_name: str | None) -> None:
        """Software-neutral by default; names the currently loaded software
        once one is loaded (issue #121) -- the previous hardcoded "Serato"
        wording was actively wrong once a Traktor mapping was open."""
        if software_name:
            self._description_label.setText(
                f"Visualize, edit, and validate your {software_name} MIDI mappings. "
                "Start here, then use the shortcuts below to drill down into "
                "the detailed views."
            )
        else:
            self._description_label.setText(
                "Visualize, edit, and validate your Serato DJ or Traktor MIDI "
                "mappings. Start here, then use the shortcuts below to drill "
                "down into the detailed views."
            )

    def set_loaded_config_info(
        self,
        path: str | Path | None,
        control_count: int = 0,
        software_id: str | None = None,
        software_name: str | None = None,
    ) -> None:
        if path is None:
            self._loaded_file_label.setText("Loaded file: none")
            self._loaded_software_id = None
            self._software_badge_label.hide()
            self._update_description(None)
            return
        name = Path(path).name
        self._loaded_file_label.setText(f"Loaded file: {name} ({control_count} control(s))")
        self._update_description(software_name)
        self._loaded_software_id = software_id
        if software_name:
            self._software_badge_label.setText(software_name)
            self._restyle_software_badge()
            self._software_badge_label.show()
        else:
            self._software_badge_label.hide()

    def _restyle_software_badge(self) -> None:
        """Re-picks the badge's light/dark color for the current theme mode
        -- called on load and again on every theme change, since the two
        modes use different hex values (see _SOFTWARE_BADGE_COLORS)."""
        palette = _SOFTWARE_BADGE_COLORS.get(self._loaded_software_id or "")
        color = (palette or {}).get(theme_current_mode(), theme_colors()["hint_text"])
        self._software_badge_label.setStyleSheet(f"font-weight: 600; color: {color};")

    def set_usage_summary(self, usage: dict[CellKey, dict[str, set[str]]]) -> None:
        summary: dict[str, tuple[int, int, int]] = {}
        for controller in catalog.CONTROLLER_NAMES:
            controller_cells = [
                per_deck for key, per_deck in usage.items() if key[0] == controller
            ]
            used_cells = len(controller_cells)
            decks: set[str] = set()
            tags: set[str] = set()
            for per_deck in controller_cells:
                decks.update(per_deck.keys())
                for deck_tags in per_deck.values():
                    tags.update(deck_tags)
            summary[controller] = (used_cells, len(decks), len(tags))
        self._usage_summary = summary
        self._refresh_card_stats()

    def _rebuild_controller_cards(self, names: list[str]) -> None:
        self._controller_tabs.clear()
        self._card_stats = {}
        self._availability_labels = {}

        for name in names:
            self._controller_tabs.addTab(self._build_controller_card(name), name)

        self._refresh_card_stats()
        self.refresh_midi_availability(self._midi_port_names)

    def _build_controller_card(self, controller: str) -> QWidget:
        card = QGroupBox(controller)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(18)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Keep a floor so the card stays readable, but low enough that the
        # whole Dashboard still fits without a scrollbar at the default
        # window height (the scroll area added for issue #19 takes over
        # below that).
        image.setMinimumSize(320, 170)
        image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        image_name = image_for_controller(controller)
        path = CONTROLLERS_DIR / image_name if image_name else None
        pixmap = QPixmap(str(path)) if path is not None and path.exists() else QPixmap()
        if pixmap.isNull():
            image.setText("Image unavailable")
            image.setFrameShape(QFrame.Shape.Box)
        else:
            image.setPixmap(pixmap.scaled(520, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))
        image.setStyleSheet("background: #0a1019; border: 1px solid #30445f; border-radius: 8px;")
        layout.addWidget(image)

        details = QVBoxLayout()
        details.setSpacing(8)
        definition = catalog.get_definition(controller)
        catalog_info = QLabel(
            f"Catalog: {len(definition.static_entries)} static entry(ies), {definition.pad_count} pad(s)"
        )
        catalog_info.setWordWrap(True)
        details.addWidget(catalog_info)

        availability = QLabel("MIDI: not checked")
        availability.setStyleSheet(f"color: {theme_colors()['disabled_text']}; font-weight: 600;")
        self._availability_labels[controller] = availability
        details.addWidget(availability)

        stats = QLabel("In loaded file: 0 cell(s), 0 deck(s), 0 function(s)")
        stats.setWordWrap(True)
        self._card_stats[controller] = stats
        details.addWidget(stats)

        details.addStretch(1)
        buttons = QVBoxLayout()
        for target, label in (("channel", "Channel"), ("controller", "Controller"), ("images", "Images")):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _checked=False, t=target, c=controller: self._drilldown_controller(t, c))
            buttons.addWidget(btn)
        details.addLayout(buttons)
        layout.addLayout(details, 0)
        return card

    def _refresh_card_stats(self) -> None:
        for controller, label in self._card_stats.items():
            used_cells, deck_count, function_count = self._usage_summary.get(controller, (0, 0, 0))
            label.setText(
                f"In loaded file: {used_cells} cell(s), {deck_count} deck(s), {function_count} function(s)"
            )

    def _drilldown_controller(self, target: str, controller: str) -> None:
        self._controller_combo.setCurrentText(controller)
        self.drillDownRequested.emit(target, controller)

    def _emit_drilldown(self, target: str) -> None:
        self.drillDownRequested.emit(target, self._controller_combo.currentText())


__all__ = ["IntroductionView"]
