"""Community submission issue -> library profile (the controller-submission workflow)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from djmidi.catalog import _registry
from djmidi.catalog.community import (
    SubmissionMetadata,
    build_submission_payload,
    submission_issue_body,
)
from djmidi.catalog.community_ingest import (
    SubmissionError,
    definition_from_payload,
    extract_payload,
    pull_request_body,
    write_community_profile,
)
from djmidi.catalog.library import (
    SOURCE_COMMUNITY,
    library_document,
    list_library_profiles,
)

ROOT = Path(__file__).resolve().parents[1]


def _payload(name="Acme Pad 8", entries=None, **metadata):
    definition = _registry.ControllerDefinition(
        name=name,
        static_entries=entries
        or [
            _registry.ControlInfo(name, "DECK", "PLAY", "NOTE", ("1", "2"), "11"),
            _registry.ControlInfo(name, "PADS", "Pad 1", "NOTE", ("8",), "0"),
        ],
    )
    return build_submission_payload(definition, SubmissionMetadata(contributor="dj-someone", **metadata))


def test_the_payload_round_trips_through_the_issue_body_the_app_writes():
    payload = _payload(notes="Captured on firmware 1.2")
    body = submission_issue_body(payload, inline_json=True)
    assert extract_payload(body) == payload


def test_an_empty_paste_placeholder_is_reported():
    body = submission_issue_body(_payload(), inline_json=False)
    with pytest.raises(SubmissionError, match="wasn't pasted"):
        extract_payload(body)
    with pytest.raises(SubmissionError, match="No controller-submission/1"):
        extract_payload("hello\n```json\n{\"schema\": \"other\"}\n```")


def test_a_valid_submission_becomes_a_library_profile(tmp_path):
    profile = write_community_profile(_payload(firmware="1.2"), tmp_path)
    assert profile.path == tmp_path / "acme-pad-8.json" and not profile.replaced
    document = json.loads(profile.path.read_text(encoding="utf-8"))
    assert document["manifest"]["plugin_id"] == "user.acme-pad-8"
    assert document["controller"]["library_source"] == SOURCE_COMMUNITY
    assert [entry["channels"] for entry in document["controller"]["entries"]] == [["1", "2"], ["8"]]
    assert write_community_profile(_payload(), tmp_path).replaced
    body = pull_request_body(profile, 42)
    assert "#42" in body and "| Firmware | 1.2 |" in body and "DECK (1), PADS (1)" in body


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"controller_name": " "}, "'controller_name' is empty"),
        ({"controller_name": "DDJ-XP2"}, "built-in controller"),
        ({"controller_name": "ddj-xp2"}, "built-in controller"),
        ({"controller_name": "x" * 200}, "longer than"),
        ({"controller_name": "bad\nname"}, "control characters"),
        ({"static_entries": []}, "no entries"),
        ({"static_entries": "nope"}, "no entries"),
    ],
)
def test_bad_submissions_are_refused(change, message):
    with pytest.raises(SubmissionError, match=message):
        definition_from_payload({**_payload(), **change})


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"note_or_cc": "PB"}, "NOTE or CC"),
        ({"channels": []}, "1 to 16 channels"),
        ({"channels": ["17"]}, "a channel must be a number from 1 to 16"),
        ({"channels": [True]}, "a channel must be"),
        ({"data1": "128"}, "'data1' must be a number from 0 to 127"),
        ({"data1": "-1"}, "'data1'"),
        ({"name": ""}, "Entry 1: 'name' is empty"),
    ],
)
def test_bad_entries_are_refused(entry, message):
    payload = _payload()
    payload["static_entries"][0] = {**payload["static_entries"][0], **entry}
    with pytest.raises(SubmissionError, match=message):
        definition_from_payload(payload)


def test_two_controls_on_one_message_are_refused():
    name = "Acme Pad 8"
    entries = [
        _registry.ControlInfo(name, "DECK", "PLAY", "NOTE", ("1",), "11"),
        _registry.ControlInfo(name, "DECK", "CUE", "NOTE", ("1",), "11"),
    ]
    with pytest.raises(SubmissionError, match="share one MIDI message"):
        definition_from_payload(_payload(entries=entries))


def test_a_community_profile_wins_over_a_generated_one_of_the_same_name(tmp_path):
    definition = definition_from_payload(_payload())
    generated = library_document(definition, "mixxx")
    (tmp_path / "mixxx").mkdir()
    (tmp_path / "mixxx" / "acme-pad-8.json").write_text(json.dumps(generated), encoding="utf-8")
    write_community_profile(_payload(), tmp_path / "community")
    profiles = list_library_profiles(tmp_path)
    assert [(profile.name, profile.source) for profile in profiles] == [("Acme Pad 8", SOURCE_COMMUNITY)]


def test_the_script_writes_the_profile_or_the_reason(tmp_path):
    body = tmp_path / "body.md"
    body.write_text(submission_issue_body(_payload(), inline_json=True), encoding="utf-8")
    command = [
        sys.executable, str(ROOT / "scripts" / "ingest_controller_submission.py"),
        "--body-file", str(body), "--issue", "7", "--out-dir", str(tmp_path / "out"),
        "--pr-body", str(tmp_path / "pr.md"), "--error-file", str(tmp_path / "error.md"),
    ]  # fmt: skip
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert "name=Acme Pad 8" in done.stdout and "slug=acme-pad-8" in done.stdout
    assert (tmp_path / "out" / "acme-pad-8.json").exists() and "#7" in (tmp_path / "pr.md").read_text()
    body.write_text("no json here", encoding="utf-8")
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    assert done.returncode == 1
    assert "No controller-submission/1" in (tmp_path / "error.md").read_text(encoding="utf-8")
