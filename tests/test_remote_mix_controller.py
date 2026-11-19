"""Your controller on the shared console: pads press buttons, one controller among several, share a mapping."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from test_remote_mix_dialog import FakeBackend

from djmidi.gui.remote_mix_audio import RemoteAudioPanel
from djmidi.midi_io import MidiEvent
from djmidi.remote_mix import controls


def _ev(kind, number, value="127", port="DDJ-XP2", channel="1"):
    return MidiEvent("in", channel, kind, number, value, 0.0, port)


def test_the_same_cc_on_two_controllers_is_two_controls():
    xp2 = controls.trigger_from_event(_ev("Control Change", "19"))
    xz = controls.trigger_from_event(_ev("Control Change", "19", port="XDJ-XZ"))
    assert not xp2.fits(xz) and xp2.fits(controls.MixerTrigger("1", "Control Change", "19"))  # an old file: any port
    mapping = controls.MixerControls()
    mapping.bind("me", xp2)
    mapping.bind("them", xz)
    assert mapping.moves(_ev("Control Change", "19", "0", port="XDJ-XZ")) == [("them", 0.0)]
    again = controls.MixerControls.from_json(mapping.to_json())
    assert again.bindings["them"].port == "XDJ-XZ" and "XDJ-XZ · ch1 CC 19" == again.bindings["them"].label()
    assert controls.button_from_event(_ev("Note On", "60", "0")) is None  # a release binds nothing


def test_pads_press_the_console_buttons(tmp_path):
    panel = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=tmp_path / "c.json", ensure_listening=lambda: True)
    panel.show()
    try:
        panel.midi_button.setChecked(True)
        QTest.mouseClick(panel.cue_buttons["them"], Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        assert panel.learning == "them_cue" and not panel.cue_buttons["them"].isChecked()  # the click only picks it
        assert not panel.feed_midi_event(_ev("Control Change", "7"))  # a fader can't bind a button
        assert panel.feed_midi_event(_ev("Note On", "60"))
        assert panel.controls.bindings["them_cue"].label() == "DDJ-XP2 · ch1 note 60"
        panel.midi_button.setChecked(False)
        assert panel.feed_midi_event(_ev("Note On", "60"))
        assert panel.cue_buttons["them"].isChecked()
        assert not panel.feed_midi_event(_ev("Note On", "60", "0"))  # the release does nothing
        panel.feed_midi_event(_ev("Note On", "60"))
        assert not panel.cue_buttons["them"].isChecked()
        for target, note in (("them_xf", "61"), ("fx_beats", "62"), ("them_mute", "63")):
            panel.controls.bind(target, controls.MixerTrigger("1", "Note On", note, "DDJ-XP2"))
        side = panel.assigns["them"].currentIndex()
        panel.feed_midi_event(_ev("Note On", "61"))
        assert panel.assigns["them"].currentIndex() == (side + 1) % 3
        beats = panel.beats_combo.currentIndex()
        panel.feed_midi_event(_ev("Note On", "62"))
        assert panel.beats_combo.currentIndex() == (beats + 1) % panel.beats_combo.count()
        panel.attach_table(1, lambda m: None)  # a guest: the mute stays the host's
        panel.feed_midi_event(_ev("Note On", "63"))
        assert not panel.mute_buttons["them"].isChecked()
    finally:
        panel.close()


def test_export_then_import_a_mapping(tmp_path):
    first = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=tmp_path / "a.json")
    second = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=tmp_path / "b.json")
    try:
        first.controls.bind("crossfader", controls.MixerTrigger("1", "Control Change", "8", "DDJ-XP2"))
        path = first.export_mapping(tmp_path / "shared.json")
        assert path is not None and "saved" in first.controls_hint.text()
        assert second.import_mapping(path)
        assert second.controls.bindings["crossfader"].control == "8"
        assert controls.MixerControls.load(tmp_path / "b.json").bindings  # kept for next time
        (tmp_path / "bad.json").write_text("{}")
        assert not second.import_mapping(tmp_path / "bad.json")
    finally:
        first.close()
        second.close()


def test_my_mapping_lists_every_assignment_and_forgets_one(tmp_path):
    panel = RemoteAudioPanel(lambda: None, backend=FakeBackend(), controls_path=tmp_path / "c.json")
    try:
        panel.controls.bind("them_cue", controls.MixerTrigger("1", "Note On", "60", "DDJ-XP2"))
        panel.controls.bind("fx_reverb", controls.MixerTrigger("1", "Control Change", "21", "DDJ-XP2"))
        dialog = panel.show_mapping()
        texts = [(dialog.table.item(r, 0).text(), dialog.table.item(r, 1).text()) for r in range(dialog.table.rowCount())]
        assert ("Reverb", "DDJ-XP2 · ch1 CC 21") in texts
        assert any(name.endswith("Cue") for name, _ in texts)
        row = next(r for r, (name, _) in enumerate(texts) if name == "Reverb")
        dialog.table.cellWidget(row, 2).click()
        assert "fx_reverb" not in panel.controls.bindings and dialog.table.rowCount() == 1
        assert "fx_reverb" not in controls.MixerControls.load(tmp_path / "c.json").bindings
        dialog.close()
    finally:
        panel.close()
