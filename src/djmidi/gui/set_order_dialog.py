"""Music Library → Set → Propose an order…: the mix-path engine's order for
the draft beside the current one, with the clash counts of each. Nothing
changes until the user clicks Use this order."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.library import set_prep

_translate = translator("SetPreparation")
DIRECTIONS = (
    (QT_TRANSLATE_NOOP("SetOrderDialog", "Smallest BPM moves, either way"), "flat"),
    (QT_TRANSLATE_NOOP("SetOrderDialog", "Rising BPM"), "up"),
    (QT_TRANSLATE_NOOP("SetOrderDialog", "Falling BPM"), "down"),
)


class SetOrderDialog(QDialog):
    def __init__(
        self, tracks: Sequence[set_prep.SetTrack], tolerance: float, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Propose an order"))
        self._tracks = list(tracks)
        self._tolerance = tolerance
        self.proposal: set_prep.OrderProposal | None = None

        intro = QLabel(
            self.tr(
                "Chains the tracks so each mix keeps the BPM within ±{tolerance} % and the keys compatible. "
                "Tracks it can't chain (no BPM or key, or too far) go last, in their current order."
            ).format(tolerance=f"{tolerance:g}")
        )
        intro.setWordWrap(True)
        self.direction_combo = QComboBox()
        for label, key in DIRECTIONS:
            self.direction_combo.addItem(self.tr(label), key)
        self.keep_opener = QCheckBox(self.tr("Keep the current first track"))
        self.keep_opener.setChecked(True)
        options = QHBoxLayout()
        options.addWidget(self.direction_combo, 1)
        options.addWidget(self.keep_opener)

        self.current_list = QListWidget()
        self.proposed_list = QListWidget()
        for widget in (self.current_list, self.proposed_list):
            usable_minimum(widget, 220, 160)
        self.current_summary = QLabel()
        self.proposed_summary = QLabel()
        for label in (self.current_summary, self.proposed_summary):
            label.setWordWrap(True)
        grid = QGridLayout()
        grid.addWidget(QLabel(self.tr("Current order")), 0, 0)
        grid.addWidget(QLabel(self.tr("Proposed order")), 0, 1)
        grid.addWidget(self.current_list, 1, 0)
        grid.addWidget(self.proposed_list, 1, 1)
        grid.addWidget(self.current_summary, 2, 0)
        grid.addWidget(self.proposed_summary, 2, 1)

        self.verdict = QLabel()
        self.verdict.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Use this order"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(options)
        layout.addLayout(grid, 1)
        layout.addWidget(self.verdict)
        layout.addWidget(self.buttons)

        for index, track in enumerate(self._tracks, start=1):
            self.current_list.addItem(f"{index}. {track.label}")
        self.direction_combo.currentIndexChanged.connect(self.update_proposal)
        self.keep_opener.toggled.connect(self.update_proposal)
        self.update_proposal()
        fit_to_screen(self, 760, 560)
        keep_wrapped_text_visible(self)

    def update_proposal(self) -> None:
        self.proposal = set_prep.propose_order(
            self._tracks, self._tolerance, self.direction_combo.currentData(), self.keep_opener.isChecked()
        )
        by_path = {track.path: track for track in self._tracks}
        self.proposed_list.clear()
        for index, path in enumerate(self.proposal.order, start=1):
            self.proposed_list.addItem(f"{index}. {by_path[path].label}")
        self.current_summary.setText(self.proposal.before.describe(_translate))
        self.proposed_summary.setText(self.proposal.after.describe(_translate))
        same = list(self.proposal.order) == [track.path for track in self._tracks]
        if same:
            text = self.tr("The current order is already what the engine proposes.")
        elif self.proposal.improves():
            text = self.tr("The proposed order has fewer clashing or unchecked mixes.")
        else:
            text = self.tr("The proposed order isn't better than yours: keep yours unless you prefer its flow.")
        self.verdict.setText(text)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not same)

    def order(self) -> list[str]:
        return list(self.proposal.order) if self.proposal else []


__all__ = ["SetOrderDialog"]
