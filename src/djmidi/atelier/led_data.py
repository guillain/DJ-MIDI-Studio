"""Verified LED data per controller (Atelier, issue #413, step 5).

No catalog records LED addresses, so `atelier.features` *assumes* a note's
LED answers on the same channel and note it sends (on 127 / off 0) and marks
it unverified. The LED probe (`gui/led_probe_dialog`) checks that on the
hardware and records what was seen here: the address that lights, its on /
off values, and names for the values that give a colour. Once recorded, the
feature model uses it and marks the LED verified.

One JSON file per controller in the workspace's Controllers folder,
``<controller slug>.leds.json``: {"controller": name, "leds": [record, ...]}.
Qt-free; nothing here talks to MIDI.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from djmidi import user_paths

_LOGGER = logging.getLogger(__name__)
FORMAT = "djmidi-leds/1"


@dataclass(frozen=True)
class LedRecord:
    feature_id: str
    channel: int
    note: int
    on_value: int = 127
    off_value: int = 0
    # value -> colour name as seen on the hardware ("red", "dim blue")
    colours: dict[int, str] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "feature": self.feature_id,
            "channel": self.channel,
            "note": self.note,
            "on": self.on_value,
            "off": self.off_value,
        }
        if self.colours:
            raw["colours"] = {str(value): name for value, name in sorted(self.colours.items())}
        if self.source:
            raw["source"] = self.source
        return raw

    @classmethod
    def from_dict(cls, raw: object) -> LedRecord:
        if not isinstance(raw, dict) or not raw.get("feature"):
            raise ValueError("An LED record needs a feature")
        values = [int(raw["channel"]), int(raw["note"]), int(raw.get("on", 127)), int(raw.get("off", 0))]
        if not 1 <= values[0] <= 16 or not all(0 <= value <= 127 for value in values[1:]):
            raise ValueError(f"LED record out of range: {raw!r}")
        colours = {int(value): str(name) for value, name in (raw.get("colours") or {}).items()}
        if not all(0 <= value <= 127 for value in colours):
            raise ValueError(f"LED colour value out of range: {raw!r}")
        return cls(str(raw["feature"]), *values, colours=colours, source=str(raw.get("source", "")))


def probe_source(day: date | None = None) -> str:
    return f"LED probe {(day or datetime.now().astimezone().date()).isoformat()}"


def _slug(text: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in text.lower()).strip("-") or "controller"


def led_file(controller: str, folder: Path | None = None) -> Path:
    return (folder or user_paths.controllers_dir()) / f"{_slug(controller)}.leds.json"


def load_led_data(controller: str, folder: Path | None = None) -> dict[str, LedRecord]:
    """feature id -> record; empty when nothing is recorded or the file is
    unreadable (logged, never raised: the assumed data still works)."""
    path = led_file(controller, folder)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = [LedRecord.from_dict(item) for item in raw.get("leds", [])]
    except (OSError, ValueError, TypeError, AttributeError):
        _LOGGER.warning("Ignoring an unreadable LED data file: %s", path, exc_info=True)
        return {}
    return {record.feature_id: record for record in records}


def save_led_record(controller: str, record: LedRecord, folder: Path | None = None) -> Path:
    """Adds or replaces one record in the controller's file (written whole,
    through a .part file)."""
    records = load_led_data(controller, folder)
    records[record.feature_id] = record
    path = led_file(controller, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "format": FORMAT,
        "controller": controller,
        "leds": [item.to_dict() for item in sorted(records.values(), key=lambda item: item.feature_id)],
    }
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    part.replace(path)
    return path


__all__ = ["FORMAT", "LedRecord", "led_file", "load_led_data", "probe_source", "save_led_record"]
