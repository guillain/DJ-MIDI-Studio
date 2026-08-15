from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from djmidi import catalog
from djmidi.gui.controller_image_view import ASSETS_DIR, image_for_controller
from djmidi.gui.layout import CellKey


class IntroductionView(QWidget):
    """Home tab presenting known controllers, app context, and quick navigation."""

    drillDownRequested = Signal(str, str)  # target tab key, controller name

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

        self._cards_layout = QGridLayout()
        self._cards_layout.setHorizontalSpacing(10)
        self._cards_layout.setVerticalSpacing(10)
        cards_host = QWidget()
        cards_host.setLayout(self._cards_layout)
        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setWidget(cards_host)

        cards_box = QGroupBox("Controller overview")
        cards_box_layout = QVBoxLayout(cards_box)
        cards_box_layout.addWidget(cards_scroll)

        help_box = QGroupBox("Helpful notes")
        help_layout = QVBoxLayout(help_box)
        help_text = QLabel(
            "- By Channel: most granular editing (raw Control/UserIO/Mapping).\n"
            "- By Deck: grouped editing of Serato duplicate trigger sets (x10) via MappingGroup.\n"
            "- By Controller: physical mapping view by controller section.\n"
            "- Live Monitor: real-time MIDI display with catalog + Serato function resolution.\n"
            "- Metronome: loop the current Controller Setup session rows at a chosen frequency.\n"
            "- Controller Setup: create a new catalog module from learned MIDI or imported XML."
        )
        help_text.setTextFormat(Qt.TextFormat.PlainText)
        help_text.setWordWrap(True)
        help_layout.addWidget(help_text)

        info = QLabel(
            "Tip: after applying a controller from Controller Setup, "
            "it appears immediately across this session's views."
        )
        info.setWordWrap(True)
        info.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addWidget(self._loaded_file_label)
        layout.addWidget(catalog_box)
        layout.addWidget(cards_box)
        layout.addWidget(help_box)
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
        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._card_stats = {}
        self._availability_labels = {}

        for index, name in enumerate(names):
            card = self._build_controller_card(name)
            self._cards_layout.addWidget(card, index // 2, index % 2)

        self._refresh_card_stats()
        self.refresh_midi_availability(self._midi_port_names)

    def _build_controller_card(self, controller: str) -> QWidget:
        card = QGroupBox(controller)
        layout = QVBoxLayout(card)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setMinimumHeight(90)
        image_name = image_for_controller(controller)
        path = ASSETS_DIR / image_name if image_name else None
        pixmap = QPixmap(str(path)) if path is not None and path.exists() else QPixmap()
        if pixmap.isNull():
            image.setText("Image unavailable")
            image.setFrameShape(QFrame.Shape.Box)
        else:
            image.setPixmap(
                pixmap.scaledToHeight(90, Qt.TransformationMode.SmoothTransformation)
            )
        layout.addWidget(image)

        definition = catalog.get_definition(controller)
        catalog_info = QLabel(
            f"Catalog: {len(definition.static_entries)} static entry(ies), {definition.pad_count} pad(s)"
        )
        catalog_info.setWordWrap(True)
        layout.addWidget(catalog_info)

        availability = QLabel("MIDI: not checked")
        availability.setStyleSheet("color: #777; font-weight: 600;")
        self._availability_labels[controller] = availability
        layout.addWidget(availability)

        stats = QLabel("In loaded file: 0 cell(s), 0 deck(s), 0 function(s)")
        stats.setWordWrap(True)
        self._card_stats[controller] = stats
        layout.addWidget(stats)

        buttons = QHBoxLayout()
        for target, label in (("channel", "By Channel"), ("controller", "By Controller"), ("images", "Images")):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _checked=False, t=target, c=controller: self._drilldown_controller(t, c))
            buttons.addWidget(btn)
        layout.addLayout(buttons)
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
