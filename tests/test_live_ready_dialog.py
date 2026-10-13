"""Issue #254: the "Ready for live" report window and its main-window wiring."""

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu

from djmidi.gui.live_ready_dialog import LiveReadyDialog
from djmidi.gui.main_window import MainWindow
from djmidi.live_ready import check_live_ready
from djmidi.parser import parse_file, parse_string

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"

_CONFLICT = parse_string(
    "<midi app='1.0'><control channel='1' event_type='Note On' control='9'>"
    "<userio event='click'><codfather_st deck_set='Default' deck_id='1' slot_id='0'>"
    "<translation action_on='press'/></codfather_st>"
    "<codfather_fx deck_set='Default' deck_id='1' slot_id='0'>"
    "<translation action_on='press'/></codfather_fx></userio></control></midi>"
)


def test_dialog_lists_findings_and_filters_by_severity():
    report = check_live_ready(_CONFLICT)
    dialog = LiveReadyDialog(report)
    assert dialog.table.rowCount() == len(report.findings)
    assert "Not ready" in dialog.verdict_label.text()
    # The two codfather functions have no LED feedback mapping either.
    assert [f.severity for f in report.findings] == ["error", "warning", "warning", "warning", "warning", "info", "info"]
    dialog.severity_checkboxes["warning"].setChecked(False)
    dialog.severity_checkboxes["info"].setChecked(False)
    assert [f.severity for f in dialog.visible_findings()] == ["error"]
    assert dialog.table.rowCount() == 1
    dialog.close()


def test_show_control_emits_the_findings_control():
    report = check_live_ready(_CONFLICT)
    dialog = LiveReadyDialog(report)
    emitted = []
    dialog.showControlRequested.connect(emitted.append)
    assert not dialog.show_button.isEnabled()
    dialog.table.selectRow(0)
    assert dialog.show_button.isEnabled()
    dialog.show_button.click()
    assert emitted == [_CONFLICT.controls[0]]
    dialog.close()


def test_copy_report_puts_the_text_on_the_clipboard():
    dialog = LiveReadyDialog(check_live_ready(_CONFLICT))
    dialog.copy_button.click()
    assert QGuiApplication.clipboard().text().startswith("Not ready")
    dialog.close()


def test_main_window_without_mapping_shows_no_report():
    window = MainWindow()
    assert window._on_live_ready_check() is None
    assert "open a mapping" in window.statusBar().currentMessage()
    window.close()


def test_main_window_opens_report_from_the_validation_area():
    window = MainWindow()
    window.show()
    window.config = parse_file(FIXTURE)
    window.current_path = FIXTURE
    window._load_tree()
    QApplication.processEvents()
    window.live_ready_button.click()
    dialog = window._live_ready_dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog.table.rowCount() == 16
    assert "16 warning(s)" in window.statusBar().currentMessage()
    menu_texts = [action.text() for menu in window.menuBar().findChildren(QMenu) for action in menu.actions()]
    assert "Ready for &Live…" in menu_texts
    dialog.close()
    window.close()
