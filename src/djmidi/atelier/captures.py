"""What a real controller was seen sending, per controller (issue #451).

The guided check (``gui/profile_check``) asks for one control at a time and
judges what the Live Monitor sees. Each verdict is kept here so a check can
be resumed, redone for one category, and read back by the controller
library (`atelier.library`) and its audit.

A record keeps the context the message depends on: which DJ software was
driving the controller during the capture (a Pioneer DDJ-XP2 sends other
notes for 1/2X / 2X, and has pad modes 5-8 at all, only while Serato runs
it). Nothing here edits a profile: a mismatch is a finding for the
maintainer, not a correction.

One JSON file per controller in the workspace's Controllers folder,
``<controller slug>.captures.json``. Qt-free; nothing here talks to MIDI.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from djmidi import user_paths
from djmidi.i18n import QT_TRANSLATE_NOOP

_LOGGER = logging.getLogger(__name__)
FORMAT = "djmidi-captures/1"

OK, MISMATCH, SKIPPED, ODD = "ok", "mismatch", "skipped", "odd"
STATUSES = (OK, MISMATCH, SKIPPED, ODD)

Trigger = tuple[str, str, str]  # (channel, "NOTE"/"CC", data1), as in profile_check

# What was driving the controller during a capture. Stored as these keys,
# shown through the labels.
NO_SOFTWARE = "none"
SOFTWARE_CHOICES: tuple[tuple[str, str], ...] = (
    (NO_SOFTWARE, QT_TRANSLATE_NOOP("ControllerCaptures", "No DJ software running")),
    ("serato", "Serato DJ Pro"),
    ("traktor", "Traktor Pro"),
    ("rekordbox", "rekordbox"),
    ("mixxx", "Mixxx"),
    ("other", QT_TRANSLATE_NOOP("ControllerCaptures", "Other DJ software")),
)
SOFTWARE_KEYS = tuple(key for key, _label in SOFTWARE_CHOICES)


def _trigger(raw: object) -> Trigger | None:
    if raw is None:
        return None
    channel, kind, data1 = (str(part) for part in raw)  # type: ignore[union-attr]
    if kind not in ("NOTE", "CC") or not channel.isdigit() or not data1.isdigit():
        raise ValueError(f"Not a trigger: {raw!r}")
    return channel, kind, data1


@dataclass(frozen=True)
class CaptureRecord:
    """One verdict of the guided check, for one item (a control and layer)."""

    item: str  # profile_check.CheckItem.key
    status: str
    got: Trigger | None = None
    presses: tuple[Trigger, ...] = ()
    software: str = NO_SOFTWARE
    day: str = ""
    note: str = ""
    # The controller state the presses showed (deck, pad bank), when known.
    deck: int | None = None
    bank: str = ""

    @property
    def key(self) -> str:
        """One verdict per control *and* software: the same button may send
        another message while a DJ software drives the controller."""
        return f"{self.item}|{self.software}"

    def to_dict(self) -> dict[str, object]:
        raw: dict[str, object] = {"item": self.item, "status": self.status, "software": self.software}
        if self.got is not None:
            raw["got"] = list(self.got)
        if self.presses:
            raw["presses"] = [list(press) for press in self.presses]
        if self.day:
            raw["date"] = self.day
        if self.note:
            raw["note"] = self.note
        if self.deck is not None:
            raw["deck"] = self.deck
        if self.bank:
            raw["bank"] = self.bank
        return raw

    @classmethod
    def from_dict(cls, raw: object) -> CaptureRecord:
        if not isinstance(raw, dict) or not raw.get("item"):
            raise ValueError("A capture record needs an item")
        status = str(raw.get("status", ""))
        if status not in STATUSES:
            raise ValueError(f"Unknown capture status: {status!r}")
        software = str(raw.get("software", NO_SOFTWARE))
        if software not in SOFTWARE_KEYS:
            software = "other"
        presses = tuple(press for press in (_trigger(item) for item in raw.get("presses") or ()) if press)
        return cls(
            item=str(raw["item"]),
            status=status,
            got=_trigger(raw.get("got")),
            presses=presses,
            software=software,
            day=str(raw.get("date", "")),
            note=str(raw.get("note", "")),
            deck=int(raw["deck"]) if raw.get("deck") is not None else None,
            bank=str(raw.get("bank", "")),
        )


@dataclass
class CaptureStore:
    """Every record of one controller, by :attr:`CaptureRecord.key` (the
    last verdict of a control under one software wins)."""

    controller: str
    records: dict[str, CaptureRecord] = field(default_factory=dict)


def today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _slug(text: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in text.lower()).strip("-") or "controller"


def captures_file(controller: str, folder: Path | None = None) -> Path:
    return (folder or user_paths.controllers_dir()) / f"{_slug(controller)}.captures.json"


def load_captures(controller: str, folder: Path | None = None) -> CaptureStore:
    """Empty when nothing is recorded or the file is unreadable (logged,
    never raised: a check simply starts over)."""
    store = CaptureStore(controller)
    path = captures_file(controller, folder)
    if not path.is_file():
        return store
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = [CaptureRecord.from_dict(item) for item in raw.get("checks", [])]
    except (OSError, ValueError, TypeError, AttributeError):
        _LOGGER.warning("Ignoring an unreadable captures file: %s", path, exc_info=True)
        return store
    store.records = {record.key: record for record in records}
    return store


def save_captures(store: CaptureStore, folder: Path | None = None) -> Path:
    """Writes the whole file through a .part file."""
    path = captures_file(store.controller, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "format": FORMAT,
        "controller": store.controller,
        "checks": [record.to_dict() for record in sorted(store.records.values(), key=lambda item: item.key)],
    }
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    part.replace(path)
    return path


def record_capture(controller: str, record: CaptureRecord, folder: Path | None = None) -> Path:
    store = load_captures(controller, folder)
    store.records[record.key] = record
    return save_captures(store, folder)


def checked_items(store: CaptureStore, software: str | None = None) -> dict[str, str]:
    """item key -> its status (under ``software`` only, when given)."""
    return {
        record.item: record.status
        for record in store.records.values()
        if software is None or record.software == software
    }


def forget_captures(controller: str, items: set[str] | None = None, folder: Path | None = None) -> Path | None:
    """Drops the records of ``items`` under every software (every record
    when None) so they are asked again."""
    store = load_captures(controller, folder)
    if not store.records:
        return None
    if items is None:
        store.records.clear()
    else:
        store.records = {key: record for key, record in store.records.items() if record.item not in items}
    return save_captures(store, folder)


__all__ = [
    "MISMATCH",
    "NO_SOFTWARE",
    "ODD",
    "OK",
    "SKIPPED",
    "SOFTWARE_CHOICES",
    "SOFTWARE_KEYS",
    "CaptureRecord",
    "CaptureStore",
    "captures_file",
    "checked_items",
    "forget_captures",
    "load_captures",
    "record_capture",
    "save_captures",
    "today",
]
