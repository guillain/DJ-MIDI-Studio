"""Music Library → Set → Build a set from the library…: generates a brand
new set from every indexed track (not just the current draft) via the
mix-path engine, previewed before it replaces the draft (issue #404)."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.set_order_dialog import DIRECTIONS
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.library import set_prep


class GenerateSetDialog(QDialog):
    def __init__(
        self,
        candidates: Sequence[set_prep.SetTrack],
        exclude: Collection[str],
        tolerance: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Build a set from the library"))
        self._candidates = list(candidates)
        self._exclude = set(exclude)
        self._tolerance = tolerance
        self.generated: set_prep.GeneratedSet | None = None

        intro = QLabel(
            self.tr(
                "Chains compatible tracks from your whole library -- not just the current draft -- until the "
                "target duration is reached. Replaces the draft, but nothing changes until you accept."
            )
        )
        intro.setWordWrap(True)

        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.0, 600.0)
        self.duration_spin.setSingleStep(5.0)
        self.duration_spin.setValue(60.0)
        self.duration_spin.setSuffix(self.tr(" min"))
        self.duration_spin.setSpecialValueText(self.tr("No limit"))
        self.direction_combo = QComboBox()
        for label, key in DIRECTIONS:
            self.direction_combo.addItem(self.tr(label), key)
        options = QHBoxLayout()
        options.addWidget(QLabel(self.tr("Target duration")))
        options.addWidget(self.duration_spin)
        options.addWidget(self.direction_combo, 1)

        self.generate_button = QPushButton(self.tr("Generate"))
        self.generate_button.clicked.connect(self.generate)

        self.preview_list = QListWidget()
        usable_minimum(self.preview_list, 320, 220)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Use this set"))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(options)
        layout.addWidget(self.generate_button)
        layout.addWidget(self.preview_list, 1)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.buttons)

        fit_to_screen(self, 640, 520)
        keep_wrapped_text_visible(self)

    def generate(self) -> None:
        minutes = self.duration_spin.value()
        target = minutes * 60.0 if minutes > 0 else None
        self.generated = set_prep.generate_set_from_library(
            self._candidates, target, self._tolerance, self.direction_combo.currentData(), exclude=self._exclude
        )
        by_path = {track.path: track for track in self._candidates}
        self.preview_list.clear()
        for index, path in enumerate(self.generated.tracks, start=1):
            self.preview_list.addItem(f"{index}. {by_path[path].label}")
        count = len(self.generated.tracks)
        if count == 0:
            text = self.tr("No compatible tracks found -- every candidate needs a BPM and a key tag.")
        else:
            duration_text = set_prep.format_duration(self.generated.duration_seconds)
            if not self.generated.duration_known:
                duration_text += "+"
            text = self.tr("{count} track(s), {duration}.").format(count=count, duration=duration_text)
        self.summary_label.setText(text)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(count > 0)

    def tracks(self) -> list[str]:
        return list(self.generated.tracks) if self.generated else []


__all__ = ["GenerateSetDialog"]
