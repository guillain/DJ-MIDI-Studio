"""The software plugin contract and the example plugin (phase 6 item 7)."""

from __future__ import annotations

import importlib
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from djmidi import software
from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.software import SoftwareDefinition, _registry, check_software_plugin

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "xdj_xz-ddj_xp2-4decks.xml"
EXAMPLE = ROOT / "examples" / "software-plugin"
SAMPLE = EXAMPLE / "samples" / "example.djmap"


@pytest.fixture
def example(monkeypatch):
    """The example plugin, registered for this test only."""
    monkeypatch.setattr(_registry, "_REGISTRY", dict(_registry._REGISTRY))
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    sys.modules.pop("djmidi_example_plugin", None)
    module = importlib.import_module("djmidi_example_plugin")
    yield software.get_definition("example.djmap"), module
    sys.modules.pop("djmidi_example_plugin", None)


def _severities(issues):
    return [(issue.severity, issue.message.split(":")[0]) for issue in issues]


def test_the_builtin_serato_and_traktor_plugins_keep_the_contract(tmp_path):
    software.discover_plugins()
    assert check_software_plugin(software.get_definition("serato"), [FIXTURE]) == []
    archive = min((ROOT / "data" / "traktor").glob("*.tsi.zip"))
    with zipfile.ZipFile(archive) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".tsi"))
        (tmp_path / "mapping.tsi").write_bytes(zf.read(name))
    assert check_software_plugin(software.get_definition("traktor"), [tmp_path / "mapping.tsi"]) == []


def test_the_example_plugin_keeps_the_contract_and_round_trips(example):
    definition, module = example
    assert check_software_plugin(definition, [SAMPLE]) == []
    config = definition.parse_file(SAMPLE)
    assert len(config.controls) == 5 and definition.exporter(config) == SAMPLE.read_text(encoding="utf-8")
    assert definition.signature(SAMPLE.read_text(encoding="utf-8"))
    with pytest.raises(module.DjmapError):
        definition.parser("# channel;message;number;event;function;deck\n1;Note On\n")


def _definition(parser, exporter, **extra):
    return SoftwareDefinition("broken", "Broken", (".brk",), parser, exporter, **extra)


def _config(channel="1", event_type="Note On", control="11", event="click", tag="play"):
    return MidiConfig(controls=[Control(channel, event_type, control, [UserIO(event, [MappingElement(tag=tag)])])])


def test_errors_are_reported(tmp_path):
    sample = tmp_path / "a.brk"
    sample.write_text("x", encoding="utf-8")

    def boom(_text):
        raise RuntimeError("nope")

    assert _severities(check_software_plugin(_definition(boom, str), [sample])) == [("error", "parser raised RuntimeError('nope')")]
    bad = check_software_plugin(_definition(lambda t: _config(channel="17", event_type="NoteOn", event="led"), str), [sample])
    assert [issue.severity for issue in bad] == ["error", "error", "error"]
    lossy = check_software_plugin(_definition(lambda t: _config() if t == "x" else MidiConfig(), lambda c: "y"), [sample])
    assert ("error", "export then parse doesn't give back the same bindings") in _severities(lossy)

    def crash(_config):
        raise KeyError("x")

    assert any("raise ValueError" in i.message for i in check_software_plugin(_definition(lambda t: _config(), crash), [sample]))
    assert _severities(check_software_plugin(_definition(lambda t: _config(), str), [])) == [
        ("error", "give at least one real sample mapping file")
    ]
    bad_id = replace(_definition(lambda t: _config(), str), plugin_id="Bad Id", extensions=("brk",))
    assert [i.severity for i in check_software_plugin(bad_id, [sample])] == ["error", "error"]


def test_read_only_plugins_and_detection_are_notes_not_errors(tmp_path, example):
    definition, _module = example
    sample = tmp_path / "copy.txt"  # wrong suffix: the signature still recognizes it
    sample.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    assert check_software_plugin(definition, [sample]) == []

    def refuse(_config):
        raise ValueError("read-only")

    read_only = replace(definition, exporter=refuse, signature=None)
    issues = check_software_plugin(read_only, [sample])
    assert [i.severity for i in issues] == ["warning", "info"]  # unknown suffix, saving refused


def test_the_command_line_checker(tmp_path):
    script = ROOT / "scripts" / "check_software_plugin.py"
    ok = subprocess.run(
        [sys.executable, str(script), "--import", "djmidi_example_plugin", "example.djmap", str(SAMPLE)],
        capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(EXAMPLE / "src")},
        check=False,
    )  # fmt: skip
    assert ok.returncode == 0 and "0 error(s)" in ok.stdout, ok.stderr
    bad = tmp_path / "bad.xml"
    bad.write_text("<midi><control channel='99' event_type='Note On' control='1'/></midi>", encoding="utf-8")
    failed = subprocess.run([sys.executable, str(script), "serato", str(bad)], capture_output=True, text=True, check=False)
    assert failed.returncode == 1 and "ERROR" in failed.stdout
    unknown = subprocess.run([sys.executable, str(script), "nope", str(bad)], capture_output=True, text=True, check=False)
    assert unknown.returncode == 2
