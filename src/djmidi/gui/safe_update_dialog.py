from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from djmidi.gui.window_size import fit_to_screen, keep_wrapped_text_visible


class SafeUpdateDialog(QDialog):
    """Read-only preview shown before a mapping file is overwritten."""

    def __init__(self, path: str, diff: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Review mapping changes"))
        fit_to_screen(self, 800, 500)

        label = QLabel(
            self.tr("Review changes for {path}. The existing file will be backed up before saving.").format(path=path)
        )
        label.setWordWrap(True)
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(diff or self.tr("(No textual changes)"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(preview)
        layout.addWidget(buttons)
        keep_wrapped_text_visible(self)


__all__ = ["SafeUpdateDialog"]
