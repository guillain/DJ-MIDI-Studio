"""Readable Serato function names (issue #209)."""

import zipfile
from pathlib import Path

import pytest

from djmidi.function_names import (
    FUNCTION_NAMES,
    function_label,
    function_name,
    is_known,
    label_with_raw,
)
from djmidi.parser import parse_file, parse_string

DATA = Path(__file__).resolve().parents[1] / "data"


def _real_tags() -> set[str]:
    configs = [parse_file(DATA / "xdj_xz-ddj_xp2-4decks.xml")]
    for archive in sorted((DATA / "serato").glob("*.xml.zip")):
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if name.endswith(".xml"):
                    configs.append(parse_string(zf.read(name).decode("utf-8")))
    return {m.tag for c in configs for ctl in c.controls for u in ctl.userios for m in u.mappings}


def test_every_tag_in_the_real_serato_exports_has_a_readable_name():
    tags = _real_tags()
    assert tags  # the fixtures parsed
    assert tags <= FUNCTION_NAMES.keys()


def test_the_table_only_names_tags_seen_in_real_files():
    # Nothing invented for a tag no real export carries.
    assert FUNCTION_NAMES.keys() <= _real_tags()


@pytest.mark.parametrize(
    ("tag", "name"),
    [
        ("auto_loop_specific_length", "Auto loop"),
        ("auto_loop_roll_specific_length", "Loop roll"),
        ("codfather_st", "Codfather ST"),
        ("codfather_fx", "Codfather FX"),
    ],
)
def test_known_names(tag, name):
    assert is_known(tag)
    assert function_name(tag) == name


def test_unknown_tags_fall_back_to_the_raw_tag():
    assert not is_known("play")
    assert function_name("play") == "play"
    assert function_name("Play/Pause") == "Play/Pause"  # a Traktor command name
    assert label_with_raw("play", "1") == "play · slot 1"


def test_slot_is_shown_as_a_slot_number_never_a_length():
    assert function_label("auto_loop_roll_specific_length", "3") == "Loop roll · slot 3"
    assert function_label("auto_loop_specific_length", None) == "Auto loop"
    assert function_label("auto_loop_specific_length", "") == "Auto loop"
    assert function_label("auto_loop_specific_length", "(none)") == "Auto loop"


def test_label_with_raw_keeps_the_tag_visible():
    assert label_with_raw("codfather_fx", "2") == "Codfather FX · slot 2 (codfather_fx)"
