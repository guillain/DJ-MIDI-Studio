"""Merge a duplicate group onto the kept copy (issue #458): the tags field by
field, then this app's playlists. Shows and collects the DJ's choices only;
the Music Library writes them (undoable, logged)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.window_size import fit_to_screen, keep_wrapped_text_visible
from djmidi.library.tag_merge import FieldProposal, RepointPreview


def _text(field: str, value: object) -> str:
    from djmidi.gui.music_library_view import _field_text

    return _field_text(field, value)


def _label(field: str) -> str:
    from djmidi.gui.music_library_view import _field_label

    return _field_label(field)


class MergeCopiesDialog(QDialog):
    def __init__(
        self,
        kept: str,
        dropped: Sequence[str],
        proposals: Sequence[FieldProposal],
        preview: RepointPreview,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Merge onto the kept copy"))
        self.kept = kept
        self.dropped = tuple(dropped)
        self.proposals = list(proposals)
        box = QVBoxLayout(self)
        intro = QLabel(
            self.tr(
                "Keep {kept} and merge the other {count} copy(ies) onto it. Ticked tags are written to the kept "
                "copy (Undo and the change history can restore them); Serato and Traktor data in the file are "
                "never touched. No file is discarded here."
            ).format(kept=Path(kept).name, count=len(self.dropped))
        )
        intro.setWordWrap(True)
        box.addWidget(intro)

        self.field_checks: dict[str, QCheckBox] = {}
        self.field_combos: dict[str, QComboBox] = {}
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.addWidget(QLabel(self.tr("<b>Tag</b>")), 0, 0)
        grid.addWidget(QLabel(self.tr("<b>Kept copy now</b>")), 0, 1)
        grid.addWidget(QLabel(self.tr("<b>Write</b>")), 0, 2)
        for row, proposal in enumerate(self.proposals, start=1):
            check = QCheckBox(_label(proposal.field))
            check.setChecked(proposal.chosen)
            combo = QComboBox()
            for value in proposal.alternatives:
                combo.addItem(_text(proposal.field, value), value)
            combo.setCurrentIndex(max(0, proposal.alternatives.index(proposal.proposed)))
            current = QLabel(_text(proposal.field, proposal.current) or self.tr("(empty)"))
            current.setWordWrap(True)
            grid.addWidget(check, row, 0)
            grid.addWidget(current, row, 1)
            grid.addWidget(combo, row, 2)
            self.field_checks[proposal.field] = check
            self.field_combos[proposal.field] = combo
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(len(self.proposals) + 2, 1)  # rows at the top
        if not self.proposals:
            grid.addWidget(QLabel(self.tr("The other copies have no tag the kept copy lacks.")), 1, 0, 1, 3)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_widget)
        scroll.setMinimumHeight(80)
        box.addWidget(scroll, 1)

        count = sum(preview.playlists.values()) + preview.set_draft
        self.playlists_check = QCheckBox(self.tr("Point this app's playlists at the kept copy"))
        self.playlists_check.setChecked(count > 0)
        self.playlists_check.setEnabled(count > 0)
        lines = [
            self.tr("{name}: {count} entry(ies)").format(name=name, count=entries)
            for name, entries in sorted(preview.playlists.items())
        ]
        if preview.set_draft:
            lines.append(self.tr("Set preparation: {count} entry(ies)").format(count=preview.set_draft))
        self.playlists_label = QLabel(
            "\n".join(lines)
            if lines
            else self.tr("No playlist of this app lists the other copies.")
        )
        self.playlists_label.setWordWrap(True)
        note = QLabel(self.tr("Serato, Traktor and rekordbox playlists are not changed."))
        note.setWordWrap(True)
        box.addWidget(self.playlists_check)
        box.addWidget(self.playlists_label)
        box.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Merge"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        fit_to_screen(self, 640, 460)
        keep_wrapped_text_visible(self)

    def choices(self) -> dict[str, object]:
        """field -> value for every ticked tag."""
        return {
            field: self.field_combos[field].currentData()
            for field, check in self.field_checks.items()
            if check.isChecked()
        }

    @property
    def repoint(self) -> bool:
        return self.playlists_check.isChecked()


__all__ = ["MergeCopiesDialog"]
