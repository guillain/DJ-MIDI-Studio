"""The Controller Emulator's "Pad colours" row (issue #232): pick a
documented colour, switch *Paint* on, click pads, then save the colours
into the controller's sync set. Every rule lives in the Qt-free
``djmidi.pad_colours``; this widget only holds the in-progress choices.

Shown only for a controller with a documented palette
(``pad_colours.palette_for``) -- hidden otherwise, so no colour is ever
offered for a controller whose velocity table isn't known.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from djmidi import pad_colours
from djmidi.pad_colours import PadColour, PadColourPalette, PadSlot


def _swatch_icon(colour: PadColour) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(colour.swatch))
    return QIcon(pixmap)


class PadColourPanel(QWidget):
    """Deck / pad mode / SHIFT layer / colour pickers, a *Paint* toggle and a
    *Save to sync set* button. ``coloursChanged`` fires whenever the pads of
    the shown deck/mode/layer change colour (a paint, a reload, a switch)."""

    coloursChanged = Signal()
    saveRequested = Signal(str, object)  # controller, dict[PadSlot, PadColour]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette: PadColourPalette | None = None
        self._colours: dict[PadSlot, PadColour] = {}

        self._deck_combo = QComboBox()
        self._mode_combo = QComboBox()
        self._shift_box = QCheckBox("SHIFT")
        self._colour_combo = QComboBox()
        self._paint_button = QPushButton(self.tr("Paint"))
        self._paint_button.setCheckable(True)
        self._paint_button.setToolTip(self.tr("While on, clicking a pad gives it the chosen colour"))
        self._save_button = QPushButton(self.tr("Save to sync set"))
        self._save_button.setToolTip(self.tr("Store these pad colours in this controller's sync set (active scene)"))
        self._deck_combo.currentIndexChanged.connect(self.coloursChanged)
        self._mode_combo.currentIndexChanged.connect(self.coloursChanged)
        self._shift_box.toggled.connect(self.coloursChanged)
        self._save_button.clicked.connect(self._on_save)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(self.tr("Pad colours:")))
        for widget in (
            self._deck_combo, self._mode_combo, self._shift_box, self._colour_combo,
            self._paint_button, self._save_button,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)
        self.setVisible(False)

    @property
    def palette(self) -> PadColourPalette | None:
        return self._palette

    def set_controller(self, controller: str, colours: dict[PadSlot, PadColour] | None = None) -> None:
        """Shows the panel for ``controller`` if it has a documented palette
        (hidden otherwise), starting from ``colours`` (e.g. its sync set's)."""
        self._palette = pad_colours.palette_for(controller)
        self._colours = dict(colours or {})
        self._paint_button.setChecked(False)
        self.setVisible(self._palette is not None)
        for combo in (self._deck_combo, self._mode_combo, self._colour_combo):
            combo.blockSignals(True)
            combo.clear()
        if self._palette is not None:
            self._deck_combo.addItems([self.tr("Deck {deck}").format(deck=deck) for deck in range(1, self._palette.decks + 1)])
            self._mode_combo.addItems([self.tr("Mode {mode}").format(mode=mode) for mode in range(1, self._palette.modes + 1)])
            for colour in self._palette.colours:
                self._colour_combo.addItem(_swatch_icon(colour), colour.name)
            # A visible, lit default rather than "No light".
            self._colour_combo.setCurrentIndex(max(self._colour_combo.findText("Red"), 0))
        for combo in (self._deck_combo, self._mode_combo, self._colour_combo):
            combo.blockSignals(False)
        self.coloursChanged.emit()

    def is_painting(self) -> bool:
        return self._palette is not None and self._paint_button.isChecked()

    def current_colour(self) -> PadColour | None:
        return self._palette.colour_named(self._colour_combo.currentText()) if self._palette else None

    def slot_for_pad(self, pad: int) -> PadSlot:
        return PadSlot(
            self._deck_combo.currentIndex() + 1, pad, self._mode_combo.currentIndex() + 1, self._shift_box.isChecked()
        )

    def paint(self, pad: int) -> tuple[PadSlot, PadColour] | None:
        """Gives ``pad`` (of the shown deck/mode/layer) the chosen colour;
        ``None`` if there is no palette or the pad doesn't exist."""
        colour = self.current_colour()
        if self._palette is None or colour is None:
            return None
        slot = self.slot_for_pad(pad)
        try:
            self._palette.check_slot(slot)
        except ValueError:
            return None
        self._colours[slot] = colour
        self.coloursChanged.emit()
        return slot, colour

    def shown_colours(self) -> dict[int, PadColour]:
        """Pad number -> colour for the deck/mode/layer currently picked."""
        probe = self.slot_for_pad(1)
        return {
            slot.pad: colour
            for slot, colour in self._colours.items()
            if (slot.deck, slot.mode, slot.shift) == (probe.deck, probe.mode, probe.shift)
        }

    def colours(self) -> dict[PadSlot, PadColour]:
        return dict(self._colours)

    def _on_save(self) -> None:
        if self._palette is not None and self._colours:
            self.saveRequested.emit(self._palette.controller, dict(self._colours))


__all__ = ["PadColourPanel"]
