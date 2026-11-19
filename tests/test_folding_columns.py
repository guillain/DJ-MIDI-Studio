"""Three columns fold (two columns) before they stack (one)."""

from PySide6.QtWidgets import QLabel

from djmidi.gui.window_size import FoldingColumns


def _box(width):
    label = QLabel("x")
    label.setMinimumWidth(width)
    return label


def test_three_then_two_then_one_column():
    left, centre, right = _box(300), _box(450), _box(380)
    columns = FoldingColumns(left, centre, right)
    columns.show()
    try:
        assert columns.width_for(FoldingColumns.THREE) == 300 + 450 + 380 + 32
        assert columns.width_for(FoldingColumns.TWO) == 380 + 450 + 16
        columns.resize(1400, 600)
        assert columns.mode == FoldingColumns.THREE
        columns.resize(1000, 600)
        assert columns.mode == FoldingColumns.TWO
        assert right.geometry().top() > left.geometry().top() and right.geometry().left() == left.geometry().left()
        assert centre.geometry().left() > left.geometry().right()
        columns.resize(600, 1200)
        assert columns.mode == FoldingColumns.ONE
        assert columns.minimumSizeHint().width() == 450
        columns.resize(1400, 600)
        assert columns.mode == FoldingColumns.THREE
    finally:
        columns.close()


def test_the_mix_together_tab_folds_on_a_laptop(tmp_path):
    from djmidi.gui.remote_mix_dialog import RemoteMixDialog

    dialog = RemoteMixDialog(link_factory=lambda: None, addresses=list, controls_path=tmp_path / "c.json",
                             history_dirs=dict, exports_dir=tmp_path, settings_path=tmp_path / "s.json")
    dialog.show()
    dialog.sound_panel.show()
    try:
        dialog.resize(1100, 800)
        for _ in range(3):
            dialog.repaint()
        assert dialog.columns.mode in (FoldingColumns.TWO, FoldingColumns.THREE)
    finally:
        dialog.close()
