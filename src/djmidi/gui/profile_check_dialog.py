"""File → Controller Profile → Verify Profile with the Controller… (issue #364).

Thin: the check itself is ``gui/profile_check.py``. The dialog opens no MIDI
port; the main window passes ``ensure_listening`` (starts the Live Monitor,
like MIDI Learn) and routes every live event to :meth:`feed_event` while the
dialog is open.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)

from djmidi import catalog
from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import PROFILE_CHECK
from djmidi.gui.profile_check import (
    MISMATCH,
    OK,
    SKIPPED,
    ProfileCheck,
    press_from_event,
    report_issue_url,
    report_text,
    trigger_text,
)
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.update_check import current_version

_translate = translator("ProfileCheck")
_MARKS = {OK: "✓", MISMATCH: "✗", SKIPPED: "–"}


def _port_key(port: str) -> str:
    return "".join(char for char in port.casefold() if char.isalnum())


class ProfileCheckDialog(QDialog):
    def __init__(
        self,
        controllers: Sequence[str],
        ports: Sequence[str] = (),
        parent=None,
        ensure_listening: Callable[[], bool] | None = None,
        initial: str | None = None,
        open_url: Callable[[str], object] | None = None,
        reports_dir: str | Path = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Verify a controller profile"))
        self._ensure_listening = ensure_listening
        self._open_url = open_url or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self._reports_dir = str(reports_dir)
        self.check: ProfileCheck | None = None

        intro = QLabel(
            self.tr(
                "Press each control of your controller when asked: the app checks that it sends what the "
                "profile says. Skip the ones your unit doesn't have. At the end, share the report so the "
                "profile can be marked verified or corrected."
            )
        )
        intro.setWordWrap(True)
        self.controller_combo = QComboBox()
        self.controller_combo.addItems(list(controllers))
        if initial:
            self.controller_combo.setCurrentText(initial)
        self.port_combo = QComboBox()
        self.port_combo.addItem(self.tr("Any input"), "")
        for port in ports:
            self.port_combo.addItem(port, port)
        self.start_button = QPushButton(self.tr("Start"))
        self.start_button.clicked.connect(self.start)
        form = QFormLayout()
        form.addRow(self.tr("Controller"), self.controller_combo)
        form.addRow(self.tr("Listen on"), self.port_combo)

        self.prompt = QLabel(self.tr("Click Start, then press the controls one by one."))
        self.prompt.setWordWrap(True)
        font = self.prompt.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        self.prompt.setFont(font)
        self.progress = QLabel("")
        self.skip_button = QPushButton(self.tr("Skip (not on my unit)"))
        self.skip_button.clicked.connect(self.skip)
        self.back_button = QPushButton(self.tr("Back"))
        self.back_button.clicked.connect(self.back)
        step_row = QHBoxLayout()
        step_row.addWidget(self.start_button)
        step_row.addWidget(self.skip_button)
        step_row.addWidget(self.back_button)
        step_row.addStretch(1)
        step_row.addWidget(self.progress)

        self.results = QListWidget()
        usable_minimum(self.results, 360, 160)

        self.copy_button = QPushButton(self.tr("Copy report"))
        self.copy_button.clicked.connect(self.copy_report)
        self.save_button = QPushButton(self.tr("Save report…"))
        self.save_button.clicked.connect(self.save_report)
        self.submit_button = QPushButton(self.tr("Submit to the project…"))
        self.submit_button.setToolTip(
            self.tr("Opens a pre-filled GitHub issue with the report; nothing is sent until you submit it there")
        )
        self.submit_button.clicked.connect(self.submit_report)
        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *PROFILE_CHECK))
        bottom.addWidget(self.copy_button)
        bottom.addWidget(self.save_button)
        bottom.addWidget(self.submit_button)
        bottom.addStretch(1)
        bottom.addWidget(close_button)
        self.status = QLabel("")
        self.status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.prompt)
        layout.addLayout(step_row)
        layout.addWidget(self.results, 1)
        layout.addWidget(self.status)
        layout.addLayout(bottom)
        self._refresh()
        fit_to_screen(self, 640, 620)
        keep_wrapped_text_visible(self)

    # --- the check ------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.check is not None and not self.check.done

    def start(self) -> bool:
        if self._ensure_listening is not None and not self._ensure_listening():
            self.status.setText(self.tr("No MIDI input is open: connect a controller, or pick one in Live Monitor."))
            return False
        controller = self.controller_combo.currentText()
        if controller not in catalog.CONTROLLER_NAMES:
            return False
        self.check = ProfileCheck.start(controller)
        self.status.setText("")
        self._refresh()
        return True

    def feed_event(self, event) -> bool:
        """Every live event while the dialog is open; True when the check
        consumed it (a press from the chosen input)."""
        if not self.running:
            return False
        wanted = self.port_combo.currentData()
        if wanted and _port_key(wanted) != _port_key(event.port):
            return False
        trigger = press_from_event(event)
        if trigger is None:
            return False
        result = self.check.press(trigger)
        if result is not None and result.status == MISMATCH:
            self.status.setText(result.detail(_translate))
        else:
            self.status.setText(self.tr("OK: {trigger}").format(trigger=trigger_text(trigger)))
        self._refresh()
        return True

    def skip(self) -> None:
        if self.running:
            self.check.skip()
            self._refresh()

    def back(self) -> None:
        if self.check is not None:
            self.check.back()
            self._refresh()

    def _refresh(self) -> None:
        check = self.check
        self.skip_button.setEnabled(self.running)
        self.back_button.setEnabled(check is not None and check.index > 0)
        has_results = check is not None and bool(check.results)
        for button in (self.copy_button, self.save_button, self.submit_button):
            button.setEnabled(has_results)
        self.start_button.setText(self.tr("Restart") if check is not None else self.tr("Start"))
        self.results.clear()
        if check is None:
            self.progress.setText("")
            return
        for index, result in sorted(check.results.items()):
            item = check.items[index]
            detail = result.detail(_translate)
            self.results.addItem(f"{_MARKS[result.status]} {item.title}" + (f" — {detail}" if detail else ""))
        self.results.scrollToBottom()
        counts = check.counts()
        self.progress.setText(
            self.tr("{done}/{total} · {ok} ok · {bad} mismatch").format(
                done=len(check.results), total=len(check.items), ok=counts[OK], bad=counts[MISMATCH]
            )
        )
        current = check.current
        if current is not None:
            self.prompt.setText(current.prompt(_translate) + f"  ({current.section})")
        else:
            self.prompt.setText(self.tr("Done — share the report below."))

    # --- the report -------------------------------------------------------------

    def report(self) -> str:
        if self.check is None:
            return ""
        return report_text(self.check, current_version(), self.port_combo.currentData() or "")

    def copy_report(self) -> None:
        QGuiApplication.clipboard().setText(self.report())
        self.status.setText(self.tr("Report copied to the clipboard."))

    def save_report(self, path: str | None = None) -> None:
        if path is None:
            name = f"profile-check-{self.check.controller if self.check else 'controller'}.md"
            path, _ = QFileDialog.getSaveFileName(
                self, self.tr("Save report"), str(Path(self._reports_dir) / name), self.tr("Markdown (*.md)")
            )
        if path:
            Path(path).write_text(self.report() + "\n", encoding="utf-8")
            self.status.setText(self.tr("Report saved to {path}").format(path=path))

    def submit_report(self) -> str:
        if self.check is None:
            return ""
        body = self.report()
        QGuiApplication.clipboard().setText(body)
        url, inlined = report_issue_url(self.check, body)
        self._open_url(url)
        self.status.setText(
            self.tr("Issue opened in your browser.")
            if inlined
            else self.tr("Issue opened in your browser: paste the report (already copied) into it.")
        )
        return url
