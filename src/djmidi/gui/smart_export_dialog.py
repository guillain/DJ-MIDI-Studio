"""Music Library → Playlists → Export all smart playlists…: one folder, the
formats to write, remembered for the next export."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.window_size import fit_to_screen, keep_wrapped_text_visible
from djmidi.library.smart_playlist import SmartExportOptions


class SmartExportDialog(QDialog):
    def __init__(
        self,
        options: SmartExportOptions,
        playlists: int,
        parent: QWidget | None = None,
        choose_folder: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Export all smart playlists"))
        self._choose_folder = choose_folder or self._ask_folder
        intro = QLabel(
            self.tr(
                "Re-evaluates your {count} smart playlist(s), then writes each one into this folder, named "
                "after the playlist. Files a previous export wrote there are replaced; nothing else is touched."
            ).format(count=playlists)
        )
        intro.setWordWrap(True)
        self.folder_edit = QLineEdit(options.folder)
        self.folder_edit.setPlaceholderText(self.tr("Folder"))
        self.folder_edit.textChanged.connect(self._update_ok)
        browse = QPushButton(self.tr("Choose…"))
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        self.serato_box = QCheckBox(self.tr("Serato crates (.crate): copy them into _Serato_/Subcrates"))
        self.serato_box.setChecked(options.serato)
        self.traktor_box = QCheckBox(self.tr("Traktor playlists (.nml): Import Playlist in Traktor"))
        self.traktor_box.setChecked(options.traktor)
        for box in (self.serato_box, self.traktor_box):
            box.toggled.connect(self._update_ok)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Export"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(folder_row)
        layout.addWidget(self.serato_box)
        layout.addWidget(self.traktor_box)
        layout.addWidget(self.buttons)
        self._update_ok()
        fit_to_screen(self, 560, 240)
        keep_wrapped_text_visible(self)

    def _ask_folder(self, start: str) -> str:
        return QFileDialog.getExistingDirectory(self, self.tr("Export folder"), start)

    def _browse(self) -> None:
        chosen = self._choose_folder(self.folder_edit.text())
        if chosen:
            self.folder_edit.setText(chosen)

    def _update_ok(self, *_args: object) -> None:
        ok = bool(self.folder_edit.text().strip()) and (self.serato_box.isChecked() or self.traktor_box.isChecked())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def options(self) -> SmartExportOptions:
        return SmartExportOptions(
            self.folder_edit.text().strip(), self.serato_box.isChecked(), self.traktor_box.isChecked()
        )


__all__ = ["SmartExportDialog"]
