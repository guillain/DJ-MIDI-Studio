from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout


class SafeUpdateDialog(QDialog):
    """Read-only preview shown before a mapping file is overwritten."""

    def __init__(self, path: str, diff: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Review mapping changes")
        self.resize(800, 500)

        label = QLabel(f"Review changes for {path}. The existing file will be backed up before saving.")
        label.setWordWrap(True)
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(diff or "(No textual changes)")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(preview)
        layout.addWidget(buttons)


__all__ = ["SafeUpdateDialog"]
