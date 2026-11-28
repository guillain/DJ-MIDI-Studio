"""The reader of rekordbox's embedded command table, on a made-up executable:
the names below are placeholders, not rekordbox's (its table is never shipped)."""

import pytest

from djmidi.function_names import function_name, is_known
from djmidi.software import _rekordbox_commands as rc

_TABLE = b"""<MIDI_COMMAND_DATA>
    <DECK>
        <COMMAND displayname = "Example Start"		csvname = "ExampleStart"	type = "1" 	category = ""	 deck = "1"/>
        <COMMAND displayname = "Example Pad 1"		csvname = "PAD1_Example"	type = "6" 	category = "Example"	 deck = "1"/>
    </DECK>
</MIDI_COMMAND_DATA>    <MIDI_COMMAND_DATA>
    <OTHER>
        <COMMAND displayname = "Example Global"	csvname = "ExampleGlobal"	type = "2" 	category = ""	 deck = "0"/>
    </OTHER>
</MIDI_COMMAND_DATA>"""


@pytest.fixture
def executable(tmp_path):
    path = tmp_path / "rekordbox"
    # binary noise, the table, then a second architecture's copy of it
    path.write_bytes(b"\x00\xff" * 500 + _TABLE + b"\x00" * 300 + _TABLE + b"\x01" * 50)
    yield path
    rc.clear()


def test_the_table_is_read_once_per_tab(executable):
    commands = rc.read_commands(executable)
    assert [(c.tab, c.csv_name, c.display_name, c.deck) for c in commands] == [
        ("DECK", "ExampleStart", "Example Start", "1"),
        ("DECK", "PAD1_Example", "Example Pad 1", "1"),
        ("OTHER", "ExampleGlobal", "Example Global", "0"),
    ]


def test_loaded_labels_name_midi_csv_commands(executable):
    assert function_name("ExampleStart") == "ExampleStart"  # nothing loaded yet
    assert rc.load(executable) == 3
    assert rc.loaded_from() == executable
    assert function_name("ExampleStart") == "Example Start" and is_known("PAD1_Example")
    assert rc.display_name("ExampleStart+Shift") == "Example Start +Shift"
    assert function_name("Unknown") == "Unknown"


def test_no_table_or_no_file_gives_nothing(tmp_path):
    empty = tmp_path / "other"
    empty.write_bytes(b"nothing here")
    assert rc.read_commands(empty) == []
    assert rc.load(tmp_path / "missing") == 0
