"""The startup help popup containing the main workflow reminders."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

HELPFUL_NOTES_TEXT = (
    "- By Channel: most granular editing (raw Control/UserIO/Mapping).\n"
    "- By Deck: grouped editing of Serato duplicate trigger sets (x10) via MappingGroup.\n"
    "- By Controller: physical mapping view by controller section.\n"
    "- Live Monitor: real-time MIDI display with catalog + Serato function resolution.\n"
    "- MIDI Routing: route MIDI and loop Controller Setup session rows.\n"
    "- MIDI Clock: configure Clock sources, destinations, and Link following.\n"
    "- Controller Setup: create a new catalog module from learned MIDI or imported XML."
)


class HelpfulNotesDialog(QDialog):
    """Non-modal notes popup that asks whether closing should persist."""

    closedPersistently = Signal()
    closedForSession = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Helpful Notes")
        self.setMinimumSize(520, 260)
        self.setModal(False)

        title = QLabel("Quick workflow reminders")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #8fe8ff;")
        notes = QLabel(HELPFUL_NOTES_TEXT)
        notes.setTextFormat(Qt.TextFormat.PlainText)
        notes.setWordWrap(True)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(notes, 1)
        layout.addWidget(close_button)

    def closeEvent(self, event: QCloseEvent) -> None:
        choice = QMessageBox.question(
            self,
            "Close Helpful Notes",
            "Should Helpful Notes remain closed on the next startup?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return
        if choice == QMessageBox.StandardButton.Yes:
            self.closedPersistently.emit()
        else:
            self.closedForSession.emit()
        event.accept()


__all__ = ["HELPFUL_NOTES_TEXT", "HelpfulNotesDialog"]
