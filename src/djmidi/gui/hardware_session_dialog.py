"""Help → Hardware Session… (issue #426): the guided checklist of
``djmidi.hardware_session`` in one non-modal window.

Live events arrive through :meth:`HardwareSessionDialog.feed_event` (called by
``MainWindow._on_live_midi_event``); while a capture runs, the dialog consumes
them. Every change is saved at once to the session file.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from djmidi.gui.help_button import help_button
from djmidi.gui.help_texts import HARDWARE_SESSION
from djmidi.gui.translation import translator
from djmidi.gui.window_size import (
    fit_to_screen,
    keep_wrapped_text_visible,
    usable_minimum,
)
from djmidi.hardware_session import (
    CHECKS,
    FAIL,
    PASS,
    SKIP,
    STATUS_LABELS,
    TODO,
    HardwareSession,
    captured_from_event,
    load_session,
    report_text,
    save_session,
    verdict,
)
from djmidi.update_check import current_version

_translate = translator("HardwareSession")
_MARKS = {TODO: "○", PASS: "✓", FAIL: "✗", SKIP: "–"}


class HardwareSessionDialog(QDialog):
    def __init__(
        self,
        session_path: str | Path,
        parent=None,
        ensure_listening: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Hardware session"))
        self._path = Path(session_path)
        self._ensure_listening = ensure_listening
        self.session: HardwareSession = load_session(self._path)
        self.capturing = False

        intro = QLabel(
            self.tr(
                "What the project still needs checked on real controllers and DJ software. Pick a check, "
                "follow its steps, then mark it. Everything is saved as you go; share the report in the "
                "issue each check names."
            )
        )
        intro.setWordWrap(True)

        self.check_list = QListWidget()
        usable_minimum(self.check_list, 240, 200)
        self.check_list.setWordWrap(True)
        self.check_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.check_list.currentRowChanged.connect(self._on_check_changed)

        self.title = QLabel("")
        font = self.title.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setWordWrap(True)
        self.steps = QLabel("")
        self.steps.setWordWrap(True)

        self.capture_button = QPushButton(self.tr("Start capture"))
        self.capture_button.clicked.connect(self.toggle_capture)
        self.clear_button = QPushButton(self.tr("Clear capture"))
        self.clear_button.clicked.connect(self.clear_capture)
        capture_row = QHBoxLayout()
        capture_row.addWidget(self.capture_button)
        capture_row.addWidget(self.clear_button)
        capture_row.addStretch(1)
        self.captured = QListWidget()
        usable_minimum(self.captured, 280, 100)
        self.verdict = QLabel("")
        self.verdict.setWordWrap(True)
        self._capture_widgets = (
            self.capture_button,
            self.clear_button,
            self.captured,
            self.verdict,
        )

        self.pass_button = QPushButton(self.tr("Pass"))
        self.fail_button = QPushButton(self.tr("Fail"))
        self.skip_button = QPushButton(self.tr("Skip"))
        self.reset_button = QPushButton(self.tr("Reset"))
        status_row = QHBoxLayout()
        for button, status in (
            (self.pass_button, PASS),
            (self.fail_button, FAIL),
            (self.skip_button, SKIP),
            (self.reset_button, TODO),
        ):
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, s=status: self.mark(s))
            status_row.addWidget(button)
        status_row.addStretch(1)
        self.result_label = QLabel("")
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText(
            self.tr("Note: what you saw, values, anything odd")
        )
        usable_minimum(self.note, 280, 70)
        self.note.textChanged.connect(self._on_note_changed)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(self.title)
        detail_layout.addWidget(self.steps)
        detail_layout.addLayout(capture_row)
        detail_layout.addWidget(self.captured, 1)
        detail_layout.addWidget(self.verdict)
        detail_layout.addWidget(self.result_label)
        detail_layout.addLayout(status_row)
        detail_layout.addWidget(self.note)
        body = QHBoxLayout()
        body.addWidget(self.check_list)
        body.addWidget(detail, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.copy_button = QPushButton(self.tr("Copy report"))
        self.copy_button.clicked.connect(self.copy_report)
        self.save_button = QPushButton(self.tr("Save report…"))
        self.save_button.clicked.connect(self.save_report)
        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(help_button(self, *HARDWARE_SESSION))
        bottom.addWidget(self.copy_button)
        bottom.addWidget(self.save_button)
        bottom.addStretch(1)
        bottom.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(body, 1)
        layout.addWidget(self.status)
        layout.addLayout(bottom)

        self._loading = False
        self._refresh_list()
        self.check_list.setCurrentRow(0)
        fit_to_screen(self, 860, 640)
        keep_wrapped_text_visible(self)

    # --- current check ----------------------------------------------------------

    @property
    def current_check(self):
        row = self.check_list.currentRow()
        return CHECKS[row] if 0 <= row < len(CHECKS) else None

    def select_check(self, check_id: str) -> None:
        for row, check in enumerate(CHECKS):
            if check.id == check_id:
                self.check_list.setCurrentRow(row)
                return
        raise KeyError(check_id)

    def _on_check_changed(self, _row: int) -> None:
        self._stop_capture()
        check = self.current_check
        if check is None:
            return
        result = self.session.result(check.id)
        self.title.setText(f"{_translate(check.title)} ({check.issue})")
        self.steps.setText(_translate(check.steps))
        for widget in self._capture_widgets:
            widget.setVisible(check.capture)
        self._loading = True
        self.note.setPlainText(result.note)
        self._loading = False
        self._refresh_detail()

    def _refresh_list(self) -> None:
        current = self.check_list.currentRow()
        self.check_list.blockSignals(True)
        self.check_list.clear()
        for check in CHECKS:
            status = self.session.results.get(check.id)
            status = status.status if status is not None else TODO
            self.check_list.addItem(f"{_MARKS[status]} {_translate(check.title)}")
        self.check_list.setCurrentRow(current)
        self.check_list.blockSignals(False)
        counts = self.session.counts()
        self.status.setText(
            self.tr(
                "{done}/{total} checked · {passed} pass · {failed} fail · {skipped} skipped"
            ).format(
                done=len(CHECKS) - counts[TODO],
                total=len(CHECKS),
                passed=counts[PASS],
                failed=counts[FAIL],
                skipped=counts[SKIP],
            )
        )

    def _refresh_detail(self) -> None:
        check = self.current_check
        if check is None:
            return
        result = self.session.result(check.id)
        self.captured.clear()
        for message in result.captured:
            self.captured.addItem(message.text())
        self.captured.scrollToBottom()
        self.verdict.setText(verdict(check, result, _translate))
        self.capture_button.setText(
            self.tr("Stop capture") if self.capturing else self.tr("Start capture")
        )
        self.clear_button.setEnabled(bool(result.captured))
        self.result_label.setText(
            self.tr("Result: {status}").format(status=_translate(STATUS_LABELS[result.status]))
        )
        self.reset_button.setEnabled(result.status != TODO)

    # --- capture ----------------------------------------------------------------

    def toggle_capture(self) -> bool:
        if self.capturing:
            self._stop_capture()
            return False
        check = self.current_check
        if check is None or not check.capture:
            return False
        if self._ensure_listening is not None and not self._ensure_listening():
            self.status.setText(
                self.tr(
                    "No MIDI input is open: connect a controller, or pick one in Live Monitor."
                )
            )
            return False
        self.capturing = True
        self._refresh_detail()
        return True

    def _stop_capture(self) -> None:
        if self.capturing:
            self.capturing = False
            self._refresh_detail()

    def clear_capture(self) -> None:
        check = self.current_check
        if check is not None:
            self.session.clear_capture(check.id)
            self._save()
            self._refresh_detail()

    def feed_event(self, event) -> bool:
        """Every live event while the dialog is open; True when a capture
        consumed it (an input-direction note or CC)."""
        check = self.current_check
        if not self.capturing or check is None:
            return False
        message = captured_from_event(event)
        if message is None:
            return False
        if not self.session.capture(check.id, message):
            self.status.setText(
                self.tr("Capture full: stop it, or clear it to start again.")
            )
            return True
        self._save()
        self.captured.addItem(message.text())
        self.captured.scrollToBottom()
        self.verdict.setText(verdict(check, self.session.result(check.id), _translate))
        self.clear_button.setEnabled(True)
        return True

    # --- results ----------------------------------------------------------------

    def mark(self, status: str) -> None:
        check = self.current_check
        if check is None:
            return
        self._stop_capture()
        self.session.set_status(check.id, status)
        self._save()
        self._refresh_list()
        self._refresh_detail()

    def _on_note_changed(self) -> None:
        check = self.current_check
        if self._loading or check is None:
            return
        self.session.set_note(check.id, self.note.toPlainText())
        self._save()

    def _save(self) -> None:
        try:
            save_session(self.session, self._path)
        except OSError as exc:
            self.status.setText(
                self.tr("Couldn't save the session: {error}").format(error=exc)
            )

    def report(self) -> str:
        return report_text(self.session, current_version())

    def copy_report(self) -> None:
        QGuiApplication.clipboard().setText(self.report())
        self.status.setText(self.tr("Report copied to the clipboard."))

    def save_report(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self,
                self.tr("Save report"),
                str(self._path.with_name("hardware-session.md")),
                self.tr("Markdown (*.md)"),
            )
        if path:
            Path(path).write_text(self.report() + "\n", encoding="utf-8")
            self.status.setText(self.tr("Report saved to {path}").format(path=path))

    def done(self, result: int) -> None:
        self._stop_capture()
        super().done(result)
