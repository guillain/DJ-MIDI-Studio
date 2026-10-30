"""Turn a community controller submission into a library profile file.

Controller Setup's *Submit to community catalog…* opens a GitHub issue whose
body carries a ``controller-submission/1`` JSON payload (see
``catalog/community.py``). When a maintainer labels such an issue
``controller-submission``, ``.github/workflows/controller-submission.yml``
runs ``scripts/ingest_controller_submission.py``, which uses this module to:

1. find the payload in the issue body (:func:`extract_payload`);
2. validate every field strictly (:func:`definition_from_payload`) -- the
   body is untrusted text from anyone, so nothing in it is executed, sizes are
   capped, and only the documented fields are read;
3. write it as a library profile under ``controllers/library/community/``
   (:func:`write_community_profile`), the folder the Profile Library window
   already lists, so the reviewer only reads a JSON diff in the PR.

Qt-free so the whole path is unit-tested without a QApplication.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from djmidi import catalog
from djmidi.catalog._registry import ControlInfo, ControllerDefinition
from djmidi.catalog.codegen import (
    find_trigger_conflicts,
    infer_section_order,
    merge_by_channel,
)
from djmidi.catalog.community import SUBMISSION_SCHEMA
from djmidi.catalog.library import (
    LIBRARY_DIR,
    SOURCE_COMMUNITY,
    _profile_slug,
    library_document,
)
from djmidi.catalog.profile import USER_PLUGIN_PREFIX

COMMUNITY_DIR = LIBRARY_DIR / SOURCE_COMMUNITY
MAX_ENTRIES = 2000
MAX_TEXT = 120
MAX_NOTES = 2000
_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class SubmissionError(ValueError):
    """The issue doesn't hold a usable submission; the message says why."""


@dataclass(frozen=True)
class IngestedProfile:
    definition: ControllerDefinition
    path: Path
    replaced: bool  # a community profile of that name already existed
    contributor: str
    target_hardware: str
    firmware: str
    source: str
    notes: str


def extract_payload(body: str) -> dict:
    """The submission JSON of an issue body: the last fenced block that
    parses to an object with the submission schema."""
    found_empty = False
    for block in reversed(_FENCE.findall(body or "")):
        if not block.strip():
            found_empty = True
            continue
        try:
            payload = json.loads(block)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("schema") == SUBMISSION_SCHEMA:
            return payload
    if found_empty:
        raise SubmissionError("The profile JSON wasn't pasted into the issue (the ```json block is empty).")
    raise SubmissionError(f"No {SUBMISSION_SCHEMA} JSON block found in the issue.")


def _text(raw: dict, key: str, *, required: bool = False, limit: int = MAX_TEXT) -> str:
    value = raw.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise SubmissionError(f"'{key}' must be text.")
    value = value.strip()
    if required and not value:
        raise SubmissionError(f"'{key}' is empty.")
    if len(value) > limit:
        raise SubmissionError(f"'{key}' is longer than {limit} characters.")
    if limit == MAX_TEXT and _CONTROL_CHARS.search(value):
        raise SubmissionError(f"'{key}' contains control characters.")
    return value


def _number(value: object, what: str, low: int, high: int) -> str:
    text = str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    if not text.isdigit() or not low <= int(text) <= high:
        raise SubmissionError(f"{what} must be a number from {low} to {high} (got {value!r}).")
    return str(int(text))


def _entry(controller: str, raw: object, row: int) -> ControlInfo:
    if not isinstance(raw, dict):
        raise SubmissionError(f"Entry {row} isn't an object.")
    try:
        section = _text(raw, "section", required=True)
        name = _text(raw, "name", required=True)
    except SubmissionError as exc:
        raise SubmissionError(f"Entry {row}: {exc}") from None
    kind = raw.get("note_or_cc")
    if kind not in ("NOTE", "CC"):
        raise SubmissionError(f"Entry {row}: 'note_or_cc' must be NOTE or CC.")
    channels = raw.get("channels")
    if not isinstance(channels, list) or not channels or len(channels) > 16:
        raise SubmissionError(f"Entry {row}: 'channels' must list 1 to 16 channels.")
    channel_texts = tuple(dict.fromkeys(_number(c, f"Entry {row}: a channel", 1, 16) for c in channels))
    data1 = _number(raw.get("data1"), f"Entry {row}: 'data1'", 0, 127)
    return ControlInfo(controller, section, name, kind, channel_texts, data1)


def definition_from_payload(payload: dict) -> ControllerDefinition:
    """A validated library definition; raises :class:`SubmissionError`."""
    name = _text(payload, "controller_name", required=True)
    built_in = {
        definition.name.casefold()
        for definition in catalog.all_controller_definitions()
        if not (definition.plugin_id or "").startswith(USER_PLUGIN_PREFIX)
    }
    if name.casefold() in built_in:
        raise SubmissionError(f"'{name}' is a built-in controller: send a correction as an issue instead.")
    raw_entries = payload.get("static_entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise SubmissionError("The submission has no entries.")
    if len(raw_entries) > MAX_ENTRIES:
        raise SubmissionError(f"More than {MAX_ENTRIES} entries.")
    entries = [_entry(name, raw, row) for row, raw in enumerate(raw_entries, start=1)]
    conflicts = find_trigger_conflicts(entries)
    if conflicts:
        raise SubmissionError("Two controls share one MIDI message: " + "; ".join(conflicts[:5]))
    merged = merge_by_channel(entries)
    return ControllerDefinition(
        name=name,
        plugin_id=USER_PLUGIN_PREFIX + _profile_slug(name),
        manufacturer="Community",
        static_entries=merged,
        section_order=infer_section_order(merged),
    )


def write_community_profile(payload: dict, directory: str | Path = COMMUNITY_DIR) -> IngestedProfile:
    definition = definition_from_payload(payload)
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_profile_slug(definition.name)}.json"
    replaced = path.exists()
    document = library_document(definition, SOURCE_COMMUNITY)
    path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return IngestedProfile(
        definition=definition,
        path=path,
        replaced=replaced,
        contributor=_text(payload, "contributor"),
        target_hardware=_text(payload, "target_hardware"),
        firmware=_text(payload, "firmware"),
        source=_text(payload, "source"),
        notes=_text(payload, "notes", limit=MAX_NOTES),
    )


def _cell(text: str) -> str:
    return text.replace("|", "\\|") or "_(not given)_"


def pull_request_body(profile: IngestedProfile, issue: int) -> str:
    """The PR description: what was added, from which issue, what to check."""
    definition = profile.definition
    sections: dict[str, int] = {}
    for entry in definition.static_entries:
        sections[entry.section] = sections.get(entry.section, 0) + 1
    lines = [
        f"Community controller profile from #{issue}, built by the `controller-submission` workflow.",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Controller | {_cell(definition.name)} |",
        f"| File | `{profile.path.as_posix()}` ({'updated' if profile.replaced else 'new'}) |",
        f"| Entries | {len(definition.static_entries)} |",
        f"| Contributor | {_cell(profile.contributor)} |",
        f"| Target hardware | {_cell(profile.target_hardware)} |",
        f"| Firmware | {_cell(profile.firmware)} |",
        f"| Capture source | {_cell(profile.source)} |",
        "",
        "**Sections:** " + ", ".join(f"{section} ({count})" for section, count in sections.items()),
        "",
        (
            "Before merging: check the names read like the controller's own labels, that nothing here "
            "was copied from a document that can't be redistributed, and run the checks (a PR opened by "
            "the workflow doesn't start CI on its own: close and reopen it)."
        ),
    ]
    if profile.notes:
        lines += ["", "**Contributor notes**", "", "> " + profile.notes.replace("\n", "\n> ")]
    return "\n".join(lines)


__all__ = [
    "COMMUNITY_DIR",
    "IngestedProfile",
    "SubmissionError",
    "definition_from_payload",
    "extract_payload",
    "pull_request_body",
    "write_community_profile",
]
