import pytest

from djmidi.generic_profile import GenericMidiProfile


def test_generic_profile_preserves_unknown_learned_controls():
    profile = GenericMidiProfile(name="Unknown Controller")
    profile.learn("1", "Note On", "60", "127", "Launch button")
    profile.learn("1", "Note On", "60", "127", "Launch button")
    definition = profile.to_definition()
    assert len(profile.controls) == 1
    assert definition.name == "Unknown Controller"
    assert definition.static_entries[0].name == "Launch button"
    assert definition.static_entries[0].note_or_cc == "NOTE"


def test_generic_profile_rejects_unsupported_event_type():
    profile = GenericMidiProfile()
    profile.learn("1", "Pitch Wheel", "1")
    with pytest.raises(ValueError, match="Unsupported generic MIDI"):
        profile.to_definition()
