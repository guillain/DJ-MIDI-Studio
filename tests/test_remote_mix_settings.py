"""Mix Together remembers its choices between sessions."""

from datetime import datetime

from test_remote_mix_dialog import FakeBackend

from djmidi.gui.remote_mix_dialog import RemoteMixDialog
from djmidi.remote_mix import settings


def _dialog(tmp_path):
    return RemoteMixDialog(
        link_factory=lambda: None, addresses=list, report_dir=lambda: tmp_path,
        now=lambda: datetime(2026, 11, 21, 21, 0),  # noqa: DTZ001
        audio_backend=FakeBackend(), controls_path=tmp_path / "c.json", history_dirs=dict,
        exports_dir=tmp_path, settings_path=tmp_path / settings.FILE_NAME,
    )


def test_the_tab_comes_back_as_the_dj_left_it(tmp_path):
    first = _dialog(tmp_path)
    try:
        first.join_radio.setChecked(True)
        first.name_edit.setText("Alex")
        first.name_edit.editingFinished.emit()
        first.address_edit.setText("10.147.17.5")
        first.address_edit.editingFinished.emit()
        first.port_spin.setValue(47900)
        first.sound_panel.monitor_combo.setCurrentIndex(0)  # Nowhere
        first.sound_panel.stems_checkbox.setChecked(True)
        first.signals_panel.over_apps.setChecked(False)
    finally:
        first.close()
    again = _dialog(tmp_path)
    try:
        assert again.join_radio.isChecked()
        assert (again.name_edit.text(), again.address_edit.text(), again.port_spin.value()) == ("Alex", "10.147.17.5", 47900)
        assert again.sound_panel.monitor_combo.currentIndex() == 0
        assert again.sound_panel.stems_checkbox.isChecked() and not again.signals_panel.over_apps.isChecked()
    finally:
        again.close()


def test_a_broken_or_foreign_file_is_ignored(tmp_path):
    path = tmp_path / settings.FILE_NAME
    path.write_text("{not json")
    assert settings.load(path) == {}
    path.write_text('{"format": "other", "values": {"name": "x"}}')
    assert settings.load(path) == {}
    settings.save(path, {"name": "Sam", "port": 47800, "bad": [1]})
    assert settings.load(path) == {"name": "Sam", "port": 47800}
    dialog = _dialog(tmp_path)
    try:
        assert dialog.name_edit.text() == "Sam"
    finally:
        dialog.close()
