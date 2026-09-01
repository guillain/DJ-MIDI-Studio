"""Collects the optional contributor metadata for a community catalog
submission (issue #17). Kept tiny: every field is optional, and the caller
still submits if the user leaves everything blank."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from djmidi.catalog.community import SubmissionMetadata


class ControllerSubmissionDialog(QDialog):
    def __init__(self, default_source: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Submit controller to community catalog")

        self._contributor = QLineEdit()
        self._contributor.setPlaceholderText("Name or GitHub handle (optional)")
        self._hardware = QLineEdit()
        self._hardware.setPlaceholderText("e.g. Behringer CMD LC-1 (optional)")
        self._firmware = QLineEdit()
        self._firmware.setPlaceholderText("Firmware / revision tested (optional)")
        self._source = QLineEdit(default_source)
        self._source.setPlaceholderText("learned / xml-import / mixed")
        self._notes = QPlainTextEdit()
        self._notes.setPlaceholderText("Anything a reviewer should know (optional)")
        self._notes.setFixedHeight(80)

        intro = QLabel(
            "A pre-filled GitHub issue opens in your browser and the full profile "
            "JSON is copied to your clipboard. Trigger data and control names may be "
            "redistributed in the built-in catalog; reference images are not submitted."
        )
        intro.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Contributor", self._contributor)
        form.addRow("Target hardware", self._hardware)
        form.addRow("Firmware", self._firmware)
        form.addRow("Capture source", self._source)
        form.addRow("Notes", self._notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Open submission")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def metadata(self) -> SubmissionMetadata:
        return SubmissionMetadata(
            contributor=self._contributor.text().strip(),
            target_hardware=self._hardware.text().strip(),
            firmware=self._firmware.text().strip(),
            source=self._source.text().strip(),
            notes=self._notes.toPlainText().strip(),
        )


__all__ = ["ControllerSubmissionDialog"]
