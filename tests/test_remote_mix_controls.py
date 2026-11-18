from djmidi.midi_io import PITCH_BEND, MidiEvent
from djmidi.remote_mix import controls


def _cc(control, value, channel="1", direction="in"):
    return MidiEvent(direction, channel, "Control Change", str(control), str(value), 0.0)


def test_only_faders_and_knobs_are_learned():
    assert controls.trigger_from_event(_cc(19, 64)) == controls.MixerTrigger("1", "Control Change", "19")
    assert controls.trigger_from_event(MidiEvent("in", "1", "Note On", "11", "127", 0.0)) is None
    assert controls.trigger_from_event(_cc(19, 64, direction="out")) is None
    bend = MidiEvent("in", "2", PITCH_BEND, "0", "16383", 0.0)
    assert controls.trigger_from_event(bend).label() == "ch2 pitch bend"
    assert controls.value_of(bend) == 1.0
    assert controls.value_of(_cc(19, 0)) == 0.0


def test_a_control_moves_its_mixer_control_and_learning_it_elsewhere_moves_it():
    mixer = controls.MixerControls()
    trigger = controls.trigger_from_event(_cc(31, 0))
    mixer.bind(controls.CROSSFADER, trigger)
    assert mixer.moves(_cc(31, 127)) == [(controls.CROSSFADER, 1.0)]
    assert mixer.moves(_cc(32, 127)) == []
    mixer.bind(controls.ME, trigger)
    assert mixer.bindings == {controls.ME: trigger}


def test_assignments_survive_a_restart(tmp_path):
    path = tmp_path / controls.FILE_NAME
    mixer = controls.MixerControls()
    mixer.bind(controls.THEM, controls.MixerTrigger("3", "Control Change", "7"))
    mixer.save(path)
    assert controls.MixerControls.load(path).bindings == mixer.bindings
    path.write_text("not json", encoding="utf-8")
    assert controls.MixerControls.load(path).bindings == {}
    assert controls.MixerControls.load(tmp_path / "missing.json").bindings == {}
