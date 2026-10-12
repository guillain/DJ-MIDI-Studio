"""Help → Report a Problem… (issue #226): an editable preview of the report
built by ``djmidi.problem_report``, then clipboard + a pre-filled GitHub issue.

Nothing is sent by the app itself: the user reads (and can trim) the exact
text before it goes anywhere, and the browser is where it gets submitted.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from djmidi.problem_report import (
    DEFAULT_TITLE,
    ReportContext,
    build_report_text,
    report_issue_url,
)


class ReportProblemDialog(QDialog):
    def __init__(
        self,
        context: ReportContext,
        parent: QWidget | None = None,
        *,
        open_url: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Report a Problem")
        self.resize(720, 600)
        self._open_url = open_url or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.last_url: str | None = None
        self.last_inlined = True

        intro = QLabel(
            "Check the text below before sending: it lists your app version, system, "
            "enabled plugins and the last log lines — no mapping or music-library "
            "content, and paths under your home folder are shortened to <code>~</code>. "
            "Edit or remove anything you'd rather not share.<br><br>"
            "<b>Copy &amp; Open GitHub</b> copies the text to the clipboard and opens a "
            "pre-filled issue in your browser; nothing is sent until you submit it there "
            "(a GitHub account is needed)."
        )
        intro.setWordWrap(True)

        self.title_edit = QLineEdit(DEFAULT_TITLE)
        self.title_edit.setPlaceholderText("Short summary of the problem")
        self.body_edit = QPlainTextEdit(build_report_text(context))
        self.body_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        form = QFormLayout()
        form.addRow("Title", self.title_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.submit_button = buttons.addButton("Copy && Open GitHub", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self._on_submit)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.body_edit, 1)
        layout.addWidget(buttons)
        self.title_edit.setFocus()
        self.title_edit.setCursorPosition(len(DEFAULT_TITLE))

    def report_text(self) -> str:
        return self.body_edit.toPlainText()

    def _on_submit(self) -> None:
        text = self.report_text()
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        url, inlined = report_issue_url(self.title_edit.text(), text)
        self.last_url, self.last_inlined = url, inlined
        self._open_url(url)
        self.accept()


__all__ = ["ReportProblemDialog"]
