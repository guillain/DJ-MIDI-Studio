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
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui.controller_image_view import ASSETS_DIR, image_for_controller
from djmidi.gui.layout import CellKey


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

        title = QLabel("DJ MIDI Studio")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")

        description = QLabel(
            "Visualize, edit, and validate your Serato MIDI mappings. "
            "Start here, then use the shortcuts below to drill down into "
            "the detailed views."
        )
        description.setWordWrap(True)

        self._loaded_file_label = QLabel("Loaded file: none")
        self._loaded_file_label.setWordWrap(True)
        self._loaded_file_label.setFrameShape(QFrame.Shape.StyledPanel)

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
        tools_layout.addWidget(monitor_button)
        tools_layout.addWidget(routing_button)
        tools_layout.addWidget(clock_button)

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

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self._loaded_file_label)
        layout.addLayout(overview_header)
        layout.addWidget(cards_box)
        layout.addWidget(info)
        layout.addStretch(1)

        self.refresh_controllers()

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
                label.setStyleSheet("color: #777; font-weight: 600;")
            elif controller in detected:
                label.setText("MIDI: available")
                label.setStyleSheet("color: #16803c; font-weight: 600;")
            else:
                label.setText("MIDI: not detected")
                label.setStyleSheet("color: #777; font-weight: 600;")

    def set_controller(self, controller: str) -> bool:
        """Select a controller in the Dashboard without opening a drill-down."""
        if self._controller_combo.findText(controller) < 0:
            return False
        self._controller_combo.setCurrentText(controller)
        return True

    def set_loaded_config_info(self, path: str | Path | None, control_count: int = 0) -> None:
        if path is None:
            self._loaded_file_label.setText("Loaded file: none")
            return
        name = Path(path).name
        self._loaded_file_label.setText(f"Loaded file: {name} ({control_count} control(s))")

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
        image.setMinimumSize(360, 220)
        image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        image_name = image_for_controller(controller)
        path = ASSETS_DIR / image_name if image_name else None
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
        availability.setStyleSheet("color: #777; font-weight: 600;")
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
