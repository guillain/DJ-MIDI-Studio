"""Help → Check for Updates / a silent background check: "What's new" shows
a newly detected GitHub release's own notes (issue #409), instead of just
the status-bar link `MainWindow` already shows. Read-only, never downloads
or installs anything -- `Open Release Page` just opens the browser.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.update_check import ReleaseInfo


class WhatsNewDialog(QDialog):
    def __init__(self, release: ReleaseInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        version = ".".join(map(str, release.version))
        self.setWindowTitle(self.tr("What's new in v{version}").format(version=version))

        heading = QLabel(release.name or self.tr("DJ MIDI Studio v{version}").format(version=version))
        heading.setWordWrap(True)
        bold = heading.font()
        bold.setBold(True)
        bold.setPointSize(bold.pointSize() + 2)
        heading.setFont(bold)

        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        if release.body.strip():
            self.notes.setMarkdown(release.body)
        else:
            self.notes.setPlainText(self.tr("No release notes were provided for this version."))
        usable_minimum(self.notes, 420, 260)

        self.open_button = QPushButton(self.tr("Open Release Page"))
        self.open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.url)))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.addButton(self.open_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.notes, 1)
        layout.addWidget(self.buttons)
        fit_to_screen(self, 560, 420)
        keep_wrapped_text_visible(self)


__all__ = ["WhatsNewDialog"]
