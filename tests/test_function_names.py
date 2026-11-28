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
from djmidi.serato_public_tags import PUBLIC_TAGS, SOURCES

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
    # Nothing invented for a tag no real export carries (ours or the public
    # Serato-saved files of serato_public_tags, each with its sources).
    assert FUNCTION_NAMES.keys() <= _real_tags() | PUBLIC_TAGS.keys()


def test_public_tags_are_confirmed_twice_and_keep_their_sources():
    for tag, keys in PUBLIC_TAGS.items():
        assert keys and all(key in SOURCES for key in keys), tag
    for repository, _file, version, _licence in SOURCES.values():
        assert repository.startswith("https://github.com/") and version  # saved by a Serato version
    # Play / Cue / Sync, unknown until now (#194), each seen in two authors' files.
    for tag in ("play", "cue", "sync"):
        assert len({key.split(":")[0] for key in PUBLIC_TAGS[tag]}) >= 2
    assert function_name("load_track") == "Load track"
    assert function_name("sync_off") == "Sync off"
    assert function_name("cue_point") == "Hot cue"  # the learned label wins


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
    assert not is_known("zoom_level_adjust")  # one public file only: not confirmed
    assert function_name("zoom_level_adjust") == "zoom_level_adjust"
    assert function_name("Play/Pause") == "Play/Pause"  # a Traktor command name
    assert label_with_raw("zoom_level_adjust", "1") == "zoom_level_adjust · slot 1"


def test_slot_is_shown_as_a_slot_number_never_a_length():
    assert function_label("auto_loop_roll_specific_length", "3") == "Loop roll · slot 3"
    assert function_label("auto_loop_specific_length", None) == "Auto loop"
    assert function_label("auto_loop_specific_length", "") == "Auto loop"
    assert function_label("auto_loop_specific_length", "(none)") == "Auto loop"


def test_label_with_raw_keeps_the_tag_visible():
    assert label_with_raw("codfather_fx", "2") == "Codfather FX · slot 2 (codfather_fx)"


def test_play_sync_and_hot_cues_learned_in_serato():
    """MIDI Learn over the IAC bus in Serato DJ Pro 5.1 (2026-11-22): PLAY,
    SYNC and HOT CUE n are `play`, `sync`, `cue_point` slot n-1."""
    with zipfile.ZipFile(DATA / "serato" / "serato-5.1-iac-learn.xml.zip") as zf:
        config = parse_string(zf.read("serato-5.1-iac-learn.xml").decode("utf-8"))
    learned = {
        (ctl.channel, ctl.control): (m.tag, m.deck_id, m.slot_id)
        for ctl in config.controls for u in ctl.userios if u.event == "click" for m in u.mappings
    }
    assert learned[("1", "0")] == ("play", "0", "0")  # deck 1 PLAY: note 0, channel 1
    assert learned[("2", "2")] == ("sync", "1", "0")  # deck 2 SYNC: note 2, channel 2
    assert learned[("1", "10")] == ("cue_point", "0", "0")  # HOT CUE 1: note 10
    assert learned[("1", "17")] == ("cue_point", "0", "7")  # HOT CUE 8: note 17
    assert function_label("cue_point", "0") == "Hot cue 1"
    assert function_label("cue_point", "7") == "Hot cue 8"
    assert function_label("play") == "Play" and function_label("sync") == "Sync"
