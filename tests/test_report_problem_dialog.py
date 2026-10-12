"""Help → Report a Problem dialog and its Help-menu wiring (issue #226)."""

from PySide6.QtWidgets import QApplication, QDialog

from djmidi.gui import main_window as main_window_module
from djmidi.gui.main_window import MainWindow
from djmidi.gui.report_problem_dialog import ReportProblemDialog
from djmidi.problem_report import ReportContext


def test_submit_copies_the_edited_text_and_opens_the_issue():
    opened = []
    dialog = ReportProblemDialog(ReportContext(app_version="1.2.3"), open_url=opened.append)
    assert "| App version | 1.2.3 |" in dialog.report_text()
    dialog.title_edit.setText("Crash on save")
    dialog.body_edit.setPlainText("edited by the user")
    dialog.submit_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert QApplication.clipboard().text() == "edited by the user"
    assert len(opened) == 1
    assert "title=Crash%20on%20save" in opened[0]
    assert "edited%20by%20the%20user" in opened[0]
    assert dialog.last_inlined


def test_cancel_sends_nothing():
    opened = []
    dialog = ReportProblemDialog(ReportContext(), open_url=opened.append)
    dialog.reject()
    assert opened == []
    assert dialog.last_url is None


def test_help_menu_report_collects_enabled_plugins(monkeypatch):
    window = MainWindow()
    context = window._problem_report_context()
    assert context.controller_plugins
    assert context.software_plugins
    assert context.qt_version.startswith(main_window_module.qVersion())

    seen = []

    class _FakeDialog:
        def __init__(self, ctx, parent):
            seen.append(ctx)
            self.last_inlined = False

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "ReportProblemDialog", _FakeDialog)
    window._report_problem_action.trigger()
    assert len(seen) == 1
    assert "clipboard" in window.statusBar().currentMessage()
