"""The Controller / MIDI / Layout display layers shared by every controller
view: one photo at a time, Layout greyed out over the MIDI picture (it was
measured on the Controller photo), and each view drawing exactly the
effective layers."""

from PySide6.QtWidgets import QGraphicsPixmapItem

from djmidi.gui.layer_toggles import LayerState, LayerToggles
from djmidi.gui.layout_view import ControllerLayoutView, midi_pixmap, reference_pixmap


def test_controller_and_midi_exclude_each_other_and_midi_greys_out_the_layout():
    toggles = LayerToggles(controller=True, midi=False, layout=True)
    assert toggles.state() == LayerState(photo=True, midi=False, layout=True)
    toggles.midi_box.setChecked(True)
    assert toggles.controller_box.isChecked() is False
    assert toggles.layout_box.isEnabled() is False
    assert toggles.state() == LayerState(photo=False, midi=True, layout=False)
    toggles.controller_box.setChecked(True)
    assert toggles.midi_box.isChecked() is False and toggles.layout_box.isEnabled() is True


def test_layout_only_and_nothing_at_all_are_allowed():
    toggles = LayerToggles(controller=True, midi=False, layout=True)
    toggles.controller_box.setChecked(False)
    assert toggles.state() == LayerState(photo=False, midi=False, layout=True)
    toggles.layout_box.setChecked(False)
    assert toggles.state() == LayerState(photo=False, midi=False, layout=False)


def test_unavailable_layers_are_disabled_and_midi_falls_back_to_the_photo():
    toggles = LayerToggles(controller=False, midi=True, layout=True)
    toggles.set_available(photo=True, midi=False, layout=True)
    assert toggles.midi_box.isEnabled() is False
    assert toggles.state() == LayerState(photo=True, midi=False, layout=True)
    toggles.set_available(photo=False, midi=False, layout=False)
    assert toggles.state() == LayerState(photo=False, midi=False, layout=False)


def _pixmaps(view):
    return [item.pixmap() for item in view._scene.items() if isinstance(item, QGraphicsPixmapItem)]


def test_mapping_layout_draws_the_midi_picture_alone():
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    markers_before = len(view._scene.items())
    view._layers.midi_box.setChecked(True)
    pixmaps = _pixmaps(view)
    assert len(pixmaps) == 1 and pixmaps[0].size() == midi_pixmap("DDJ-XP2").size()
    assert len(view._scene.items()) == 1 < markers_before
    view._layers.controller_box.setChecked(True)
    assert _pixmaps(view)[0].size() == reference_pixmap("DDJ-XP2").size()


def test_mapping_layout_can_hide_the_layout():
    view = ControllerLayoutView()
    view.set_controller("DDJ-XP2")
    view._layers.layout_box.setChecked(False)
    assert len(view._scene.items()) == 1  # the photo only


def test_photo_layers_are_unavailable_without_a_measured_layout():
    view = ControllerLayoutView()
    view.set_controller("Hercules DJControl Inpulse 500")
    assert view._layers.controller_box.isEnabled() is False
    assert view._layers.midi_box.isEnabled() is False
    assert view._layers.layout_box.isEnabled() is True


def test_emulator_follows_its_layers():
    from djmidi.gui.controller_emulator import ControllerEmulatorView

    view = ControllerEmulatorView("DDJ-XP2")
    emulator = view._emulator
    view._layers.midi_box.setChecked(True)
    assert (emulator._show_reference_photo, emulator._show_midi, emulator._show_layout) == (False, True, False)
    assert len(emulator._scene.items()) == 1
    view._layers.controller_box.setChecked(True)
    view._layers.layout_box.setChecked(False)
    assert (emulator._show_reference_photo, emulator._show_midi, emulator._show_layout) == (True, False, False)
