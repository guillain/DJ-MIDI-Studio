"""Adding commands to a Traktor .tsi the way Controller Manager does (#233),
checked byte for byte against the maintainer's exports (an extract of the
edited Generic MIDI device: data/traktor/traktor-add-command-steps.json)."""

import json
from pathlib import Path

import pytest

from djmidi.software._tsi import NewCommand, TsiError, add_commands, parse_tsi

STEPS = json.loads((Path(__file__).parents[1] / "data/traktor/traktor-add-command-steps.json").read_text())


def _tsi(blob: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n<NIXML><TraktorSettings>'
        f'<Entry Name="DeviceIO.Config.Controller" Type="3" Value="{blob}"></Entry>'
        "</TraktorSettings></NIXML>\n"
    )


EMPTY = parse_tsi(_tsi(STEPS["vide"]))


@pytest.mark.parametrize(
    ("commands", "expected"),
    [
        ([NewCommand(0, 100)], "play"),
        ([NewCommand(0, 100, "Ch01.CC.079")], "play-learn"),
        ([NewCommand(0, 100, "Ch01.CC.079"), NewCommand(0, 102)], "fader"),
    ],
)
def test_adding_commands_matches_traktors_own_exports(commands, expected):
    assert add_commands(EMPTY, commands) == _tsi(STEPS[expected])


def test_the_added_commands_read_back():
    document = parse_tsi(add_commands(EMPTY, [NewCommand(0, 100, "Ch01.Note.C-1"), NewCommand(0, 102)]))
    play, fader = document.devices[0].mappings
    assert (play.command_name, play.label, play.direction, play.controller_type) == (
        "Play/Pause", "Ch01.Note.C-1", "in", 0)
    assert (fader.command_name, fader.label, fader.controller_type) == ("Volume Adjust", "", 1)
    assert play.binding_id < fader.binding_id
    assert EMPTY.devices[0].mappings == []  # the source document is untouched


def test_a_new_binding_id_never_reuses_one_in_use():
    # A device with history has ids far above its edit counter.
    document = parse_tsi(add_commands(EMPTY, [NewCommand(0, 100)] * 3))
    ids = [mapping.binding_id for mapping in document.devices[0].mappings]
    assert len(set(ids)) == 3


def test_only_commands_with_captured_defaults_and_valid_labels_are_added():
    with pytest.raises(TsiError, match="no captured Traktor defaults"):
        add_commands(EMPTY, [NewCommand(0, 125)])
    with pytest.raises(TsiError):
        add_commands(EMPTY, [NewCommand(0, 100, "Ch99.CC.001")])
    with pytest.raises(TsiError, match="no device"):
        add_commands(EMPTY, [NewCommand(3, 100)])
