"""Edit → Copy Deck Mappings…: pick a source and a target deck, check the
channel each source channel goes to, read the preview, copy.

The dialog only plans (``deck_copy.plan_deck_copy``); the window applies the
accepted plan as one undo step."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from djmidi.deck_copy import (
    DeckCopyError,
    DeckCopyPlan,
    deck_ids,
    default_channel_map,
    plan_deck_copy,
)
from djmidi.gui import help_texts
from djmidi.gui.help_button import help_button
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.model import MidiConfig

_translate = translator("DeckCopy")
_LISTED = 8


class DeckCopyDialog(QDialog):
    def __init__(self, config: MidiConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Copy Deck Mappings"))
        self._config = config
        self.plan: DeckCopyPlan | None = None

        intro = QLabel(
            self.tr(
                "Copies every mapping of one deck onto another deck, on the MIDI channel you choose for it. "
                "The repeated copies of each control are kept as they are."
            )
        )
        intro.setWordWrap(True)
        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        for deck in deck_ids(config):
            label = self.tr("Deck {deck}").format(deck=deck)
            self.source_combo.addItem(label, deck)
            self.target_combo.addItem(label, deck)
        if self.target_combo.count() > 1:
            self.target_combo.setCurrentIndex(1)
        form = QFormLayout()
        form.addRow(self.tr("From:"), self.source_combo)
        form.addRow(self.tr("To:"), self.target_combo)

        self.channel_table = QTableWidget(0, 2)
        self.channel_table.setHorizontalHeaderLabels([self.tr("Source channel"), self.tr("Target channel")])
        self.channel_table.verticalHeader().setVisible(False)
        self.channel_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        usable_minimum(self.channel_table, 260, 90)

        self.replace_box = QCheckBox(self.tr("Replace the target deck's mappings on the same controls"))
        self.preview = QLabel("")
        self.preview.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Copy"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *help_texts.DECK_COPY))
        bottom.addStretch(1)
        bottom.addWidget(self.buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.channel_table, 1)
        layout.addWidget(self.replace_box)
        layout.addWidget(self.preview)
        layout.addLayout(bottom)

        self.source_combo.currentIndexChanged.connect(self._reset_channels)
        self.target_combo.currentIndexChanged.connect(self._reset_channels)
        self.replace_box.toggled.connect(self.update_preview)
        self._reset_channels()
        fit_to_screen(self, 560, 480)
        keep_wrapped_text_visible(self)

    def _reset_channels(self) -> None:
        source, target = self.source_combo.currentData(), self.target_combo.currentData()
        self.channel_table.setRowCount(0)
        if source is None or target is None:
            self.update_preview()
            return
        for row, (from_channel, to_channel) in enumerate(default_channel_map(self._config, source, target).items()):
            self.channel_table.insertRow(row)
            item = QTableWidgetItem(from_channel)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.channel_table.setItem(row, 0, item)
            spin = QSpinBox()
            spin.setRange(1, 16)
            spin.setValue(int(to_channel) if to_channel.isdigit() else 1)
            spin.valueChanged.connect(self.update_preview)
            self.channel_table.setCellWidget(row, 1, spin)
        self.update_preview()

    def channel_map(self) -> dict[str, str]:
        return {
            self.channel_table.item(row, 0).text(): str(self.channel_table.cellWidget(row, 1).value())
            for row in range(self.channel_table.rowCount())
        }

    def _triggers(self, triggers) -> str:
        shown = [self.tr("ch {channel} {kind} {number}").format(
            channel=channel, kind=self.tr("note") if event_type.startswith("Note") else "CC", number=number
        ) for channel, event_type, number in triggers[:_LISTED]]
        if len(triggers) > _LISTED:
            shown.append(self.tr("… and {count} more").format(count=len(triggers) - _LISTED))
        return ", ".join(shown)

    def update_preview(self) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        source, target = self.source_combo.currentData(), self.target_combo.currentData()
        try:
            if source is None or target is None:
                raise DeckCopyError(self.tr("This mapping has no decks."))
            self.plan = plan_deck_copy(
                self._config, source, target, self.channel_map(),
                replace=self.replace_box.isChecked(), translate=_translate,
            )  # fmt: skip
        except DeckCopyError as exc:
            self.plan = None
            self.preview.setText(str(exc))
            ok.setEnabled(False)
            return
        plan = self.plan
        lines = [
            self.tr("{controls} control(s) get a copy ({elements} mapping element(s) written).").format(
                controls=len(plan.copied), elements=plan.elements
            )
        ]
        if plan.conflicts and plan.replaced:
            lines.append(
                self.tr("Deck {deck}'s current mappings are replaced on: {triggers}.").format(
                    deck=target, triggers=self._triggers(plan.conflicts)
                )
            )
        elif plan.conflicts:
            lines.append(
                self.tr("Skipped, deck {deck} already uses them: {triggers}.").format(
                    deck=target, triggers=self._triggers(plan.conflicts)
                )
            )
        self.preview.setText("\n".join(lines))
        ok.setEnabled(bool(plan.copied))


__all__ = ["DeckCopyDialog"]
