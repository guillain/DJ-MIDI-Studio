import json
from urllib.parse import parse_qs, urlsplit

from djmidi.catalog._registry import ControlInfo, ControllerDefinition
from djmidi.catalog.codegen import build_definition
from djmidi.catalog.community import (
    COMMUNITY_REPO,
    SUBMISSION_LABEL,
    SUBMISSION_SCHEMA,
    SubmissionMetadata,
    build_submission_payload,
    payload_json,
    submission_issue_body,
    submission_issue_title,
    submission_issue_url,
    summarise_source,
)


def _definition() -> ControllerDefinition:
    rows = [
        ControlInfo("MiniPad", "PADS", "PAD 1", "NOTE", ("1", "2"), "36"),
        ControlInfo("MiniPad", "DECK", "PLAY", "NOTE", ("1",), "0"),
    ]
    return build_definition("MiniPad", rows)


def test_summarise_source_collapses_tags():
    assert summarise_source([]) == ""
    assert summarise_source(["learned", "learned"]) == "learned"
    assert summarise_source(["learned", "xml-import"]).startswith("mixed (")
    assert "learned" in summarise_source(["learned", "xml-import"])


def test_build_submission_payload_shape_excludes_image_bytes():
    payload = build_submission_payload(
        _definition(),
        SubmissionMetadata(contributor="dj_test", target_hardware="MiniPad v2", source="learned"),
    )
    assert payload["schema"] == SUBMISSION_SCHEMA
    assert payload["controller_name"] == "MiniPad"
    assert payload["contributor"] == "dj_test"
    assert payload["target_hardware"] == "MiniPad v2"
    assert payload["section_order"] == ["PADS", "DECK"]
    assert len(payload["static_entries"]) == 2
    assert payload["static_entries"][0] == {
        "section": "PADS",
        "name": "PAD 1",
        "note_or_cc": "NOTE",
        "channels": ["1", "2"],
        "data1": "36",
    }
    # JSON must round-trip cleanly.
    assert json.loads(payload_json(payload)) == payload


def test_submission_issue_body_has_metadata_and_json_block():
    payload = build_submission_payload(_definition(), SubmissionMetadata(contributor="dj_test"))
    body = submission_issue_body(payload, inline_json=True)
    assert "| Contributor | dj_test |" in body
    assert "```json" in body
    assert '"controller_name": "MiniPad"' in body
    assert "reference images are not part of this submission" in body


def test_submission_issue_body_placeholder_when_not_inlined():
    payload = build_submission_payload(_definition(), SubmissionMetadata())
    body = submission_issue_body(payload, inline_json=False)
    assert "copied to your clipboard" in body
    assert '"static_entries"' not in body  # payload not inlined


def test_submission_issue_url_is_well_formed_and_labelled():
    payload = build_submission_payload(_definition(), SubmissionMetadata(contributor="dj_test"))
    url, inlined = submission_issue_url(payload)
    assert inlined is True
    split = urlsplit(url)
    assert split.netloc == "github.com"
    assert split.path == f"/{COMMUNITY_REPO}/issues/new"
    params = parse_qs(split.query)
    assert params["labels"] == [SUBMISSION_LABEL]
    assert params["title"][0] == submission_issue_title(payload)
    assert "MiniPad" in params["body"][0]
    assert '"schema": "controller-submission/1"' in params["body"][0]


def test_submission_issue_url_falls_back_to_clipboard_for_large_payloads():
    rows = [
        ControlInfo("BigPad", "PADS", f"PAD {i}", "NOTE", ("1", "2", "3", "4"), str(i))
        for i in range(128)
    ]
    payload = build_submission_payload(build_definition("BigPad", rows), SubmissionMetadata())
    url, inlined = submission_issue_url(payload)
    assert inlined is False
    params = parse_qs(urlsplit(url).query)
    assert "copied to your clipboard" in params["body"][0]
    # The huge JSON is not crammed into the URL.
    assert len(url) < 6000
