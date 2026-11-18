"""What Mix Together remembers between sessions, Qt-free.

A DJ shouldn't type their name, the host's address or pick their sound cards
again every time: the tab keeps its last choices in the workspace
(``mix-together-settings.json``). Only plain values (text, numbers, ticks)
are kept; a device that is gone is simply not chosen.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

FILE_NAME = "mix-together-settings.json"
FORMAT = "djmidi-mix-settings/1"

Value = str | int | bool


def _plain(value: object) -> bool:
    return isinstance(value, (str, int, bool))


def load(path: Path) -> dict[str, Value]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        _LOGGER.warning("Mix Together settings not read from %s: %s", path, exc)
        return {}
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("values"), dict):
        return {}
    return {key: value for key, value in data["values"].items() if isinstance(key, str) and _plain(value)}


def save(path: Path, values: dict[str, Value]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    plain = {key: value for key, value in values.items() if _plain(value)}
    tmp.write_text(json.dumps({"format": FORMAT, "values": plain}, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
