from PySide6.QtWidgets import QDialog, QTextEdit

from djmidi.gui.safe_update_dialog import SafeUpdateDialog


def test_safe_update_dialog_shows_diff_and_can_accept():
    dialog = SafeUpdateDialog("mapping.xml", "-old\n+new\n")
    preview = dialog.findChild(QTextEdit)
    assert preview is not None
    assert "-old" in preview.toPlainText()
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
