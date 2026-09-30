"""Traktor .tsi support (issue #122), exercised against the maintainer's
real exports committed in data/traktor/*.tsi.zip -- not synthetic XML."""

from __future__ import annotations

import base64
import re
import struct
import zipfile
from functools import cache
from pathlib import Path

import pytest

from djmidi import software
from djmidi.binary_chunks import ChunkError, ChunkNode, decode, encode
from djmidi.software import _tsi
from djmidi.software.traktor import parse_string, to_xml_string

DATA = Path(__file__).parent.parent / "data" / "traktor"


@cache
def _real(name: str) -> str:
    with zipfile.ZipFile(DATA / f"{name}.tsi.zip") as archive:
        member = next(n for n in archive.namelist() if n.endswith(".tsi"))
        return archive.read(member).decode("utf-8")


def _value(text: str) -> str:
    return re.search(r'Name="DeviceIO\.Config\.Controller" Type="3" Value="([^"]*)"', text).group(1)


# --- generic chunk codec ------------------------------------------------


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload


def test_chunk_tree_roundtrip_and_size_propagation():
    data = _chunk(b"ROOT", struct.pack(">i", 1) + _chunk(b"LEAF", b"abc")) + _chunk(b"TAIL", b"")
    tree = decode(data, {(None, "ROOT"): 4})
    assert [node.tag for node in tree] == ["ROOT", "TAIL"]
    assert tree[0].prefix == struct.pack(">i", 1)
    assert encode(tree) == data
    tree[0].find("LEAF").payload = b"longer payload"
    reencoded = encode(tree)
    assert decode(reencoded, {(None, "ROOT"): 4})[0].find("LEAF").payload == b"longer payload"
    assert struct.unpack(">I", reencoded[4:8])[0] == 4 + 8 + len(b"longer payload")


def test_chunk_codec_rejects_truncation_and_bad_tags():
    with pytest.raises(ChunkError):
        decode(b"ROOT\x00\x00\x00\x10abc", {})
    with pytest.raises(ChunkError):
        decode(b"ROO", {})
    with pytest.raises(ChunkError):
        encode([ChunkNode(tag="TOOLONG")])


def test_unknown_chunks_stay_opaque_leaves():
    data = _chunk(b"ABCD", _chunk(b"EFGH", b"x"))
    [node] = decode(data, {})
    assert not node.is_container
    assert encode([node]) == data


# --- label notation -------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "trigger"),
    [
        ("Ch01.Note.C-1", _tsi.MidiTrigger(1, "Note", 0)),
        ("Ch01.Note.C#-1", _tsi.MidiTrigger(1, "Note", 1)),
        ("Ch01.Note.G1", _tsi.MidiTrigger(1, "Note", 31)),
        ("Ch16.Note.G9", _tsi.MidiTrigger(16, "Note", 127)),
        ("Ch02.CC.017", _tsi.MidiTrigger(2, "CC", 17)),
        ("Ch03.PitchBend", _tsi.MidiTrigger(3, "PitchBend", None)),
    ],
)
def test_label_roundtrip(label, trigger):
    assert _tsi.parse_label(label) == trigger
    assert _tsi.format_label(trigger) == label


def test_compound_label_reports_its_first_part():
    assert _tsi.is_compound_label("Ch01.CC.032+Ch01.CC.000")
    assert _tsi.parse_label("Ch01.CC.032+Ch01.CC.000") == _tsi.MidiTrigger(1, "CC", 32)


@pytest.mark.parametrize("label", ["", "Ch1.Note.C0", "Ch01.Note", "Ch01.Note.H2", "Ch01.Sysex.1"])
def test_bad_labels_are_rejected(label):
    with pytest.raises(_tsi.TsiError):
        _tsi.parse_label(label)


def test_format_label_validates_ranges():
    with pytest.raises(_tsi.TsiError):
        _tsi.format_label(_tsi.MidiTrigger(17, "CC", 1))
    with pytest.raises(_tsi.TsiError):
        _tsi.format_label(_tsi.MidiTrigger(1, "Note", 128))


# --- real exports -----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "devices", "mappings"),
    [("xdj-xz-settings", 5, 8963), ("cmd-studio-4a", 4, 381), ("nanopad2-remixer", 1, 16), ("keyboard-mapping", 0, 0)],
)
def test_real_exports_decode_fully(name, devices, mappings):
    document = _tsi.parse_tsi(_real(name))
    assert len(document.devices) == devices
    assert len(document.mappings) == mappings
    if document.tree:
        # Unmodified tree + Base64 re-encode byte-identically.
        assert base64.b64encode(encode(document.tree)).decode() == _value(_real(name))


def test_real_xdj_xz_matches_official_pioneer_notes():
    """Traktor's own XDJ-XZ mapping puts Play/Cue/Sync on the notes the
    official Pioneer MIDI list (catalog/xdj_xz.py) gives: 0, 1 and 31."""
    document = _tsi.parse_tsi(_real("xdj-xz-settings"))
    page1 = document.devices[0]
    assert page1.comment.startswith("XDJ-XZ Page1")
    by_command = {
        mapping.command_id: mapping.trigger
        for mapping in page1.mappings
        if mapping.direction == "in" and mapping.trigger.channel == 1
    }
    assert by_command[100] == _tsi.MidiTrigger(1, "Note", 0)
    assert by_command[206] == _tsi.MidiTrigger(1, "Note", 1)
    assert by_command[125] == _tsi.MidiTrigger(1, "Note", 31)


def test_real_comments_and_directions_decode():
    document = _tsi.parse_tsi(_real("cmd-studio-4a"))
    comments = {mapping.comment for mapping in document.mappings}
    assert "Scratch A Light" in comments
    assert {mapping.direction for mapping in document.mappings} == {"in", "out"}


def test_plugin_import_of_real_export():
    config = parse_string(_real("cmd-studio-4a"))
    # One CMD Studio command was never MIDI-learned: kept in the file, not shown.
    assert len(config.controls) == 380
    assert config.extra_attrs["format"] == "tsi"
    play = next(c for c in config.controls if c.userios[0].mappings[0].tag == "Play/Pause")
    assert play.userios[0].event == "click"
    assert play.userios[0].mappings[0].extra_attrs["interaction_mode"] == "Toggle"
    outputs = [c for c in config.controls if c.userios[0].event == "output"]
    assert outputs and all(c.userios[0].mappings[0].extra_attrs["controller_type"] == "LED" for c in outputs)


def test_unedited_export_is_byte_identical():
    text = _real("nanopad2-remixer")
    assert to_xml_string(parse_string(text)) == text


def test_edited_binding_is_the_only_change():
    text = _real("nanopad2-remixer")
    config = parse_string(text)
    target = config.controls[0]
    original = _tsi.parse_tsi(text).mappings
    target.control = "100"
    exported = to_xml_string(config)

    # Everything outside the controller blob is untouched.
    assert exported.replace(_value(exported), "") == text.replace(_value(text), "")
    after = _tsi.parse_tsi(exported).mappings
    changed = [(a, b) for a, b in zip(original, after, strict=True) if a != b]
    assert len(changed) == 1
    before, now = changed[0]
    assert now.trigger == _tsi.MidiTrigger(before.trigger.channel, "Note", 100)
    assert (now.command_id, now.target_deck, now.interaction_mode) == (
        before.command_id,
        before.target_deck,
        before.interaction_mode,
    )
    # The source document stays pristine: reverting the edit re-exports the original.
    target.control = str(before.trigger.number)
    assert to_xml_string(config) == text


def test_export_refuses_what_it_cannot_express():
    config = parse_string(_real("nanopad2-remixer"))
    removed = config.controls.pop()
    with pytest.raises(_tsi.TsiError, match="removing"):
        to_xml_string(config)
    config.controls.append(removed)

    from djmidi.model import Control

    config.controls.append(Control(channel="1", event_type="Note On", control="5"))
    with pytest.raises(_tsi.TsiError, match="adding"):
        to_xml_string(config)
    config.controls.pop()

    config.controls[0].event_type = "Sysex"
    with pytest.raises(_tsi.TsiError):
        to_xml_string(config)


def test_compound_binding_cannot_be_reassigned():
    config = parse_string(_real("xdj-xz-settings"))
    compound = next(c for c in config.controls if "+" in c.extra_attrs["tsi_label"])
    compound.control = str(int(compound.control) + 1)
    with pytest.raises(_tsi.TsiError, match="two-message"):
        to_xml_string(config)


def test_real_tsi_is_detected_as_traktor():
    assert [d.plugin_id for d in software.detect_from_text(_real("nanopad2-remixer"), ".tsi")] == ["traktor"]


def test_corrupt_blob_is_a_clear_error():
    text = _real("nanopad2-remixer")
    broken = text.replace(_value(text), base64.b64encode(b"DIOM\x00\x00\x00\xffxx").decode())
    with pytest.raises(_tsi.TsiError, match="unreadable"):
        parse_string(broken)


def test_change_summary_names_each_rebound_command():
    text = _real("nanopad2-remixer")
    config = parse_string(text)
    config.controls[0].control = "100"
    summary = software.get_definition("traktor").change_summary(text, to_xml_string(config))
    assert summary.startswith("1 Traktor binding change(s):")
    assert "-> Ch01.Note.E7" in summary
    assert _tsi.describe_changes(text, text) == "No Traktor binding changes."
    corrupt = text.replace(_value(text), base64.b64encode(b"DIOM\x00\x00\x00\xffxx").decode())
    assert _tsi.describe_changes(corrupt, text) == ""
    assert _tsi.describe_changes("<NIXML></NIXML>", text) == "Traktor bindings: 0 -> 16"


def test_safe_save_diff_is_readable_for_a_tsi(tmp_path):
    from djmidi.safe_update import prepare_update

    text = _real("nanopad2-remixer")
    target = tmp_path / "mapping.tsi"
    target.write_text(text, encoding="utf-8")
    config = parse_string(text)
    config.controls[0].control = "100"
    definition = software.get_definition("traktor")
    plan = prepare_update(target, definition.exporter(config), definition.parser, summarize=definition.change_summary)
    assert plan.diff.startswith("1 Traktor binding change(s):")
    assert "more characters]" in plan.diff
    assert len(plan.diff) < 5000
    plan.apply()
    assert parse_string(target.read_text(encoding="utf-8")).controls[0].control == "100"
