"""Named snapshots of a mapping (Qt-free).

`File → Save Snapshot…` keeps the mapping as it is in the app (unsaved
edits included) under a name -- "before the club gig", "club version" -- so
it can be compared with the mapping diff later or brought back. Unlike the
single ``.bak`` a save leaves, any number of snapshots are kept.

Each mapping gets its own folder under the workspace's ``Snapshots``:
``<stem>-<hash of its full path>`` (two ``mapping.xml`` in different folders
don't mix), holding one file per snapshot -- the mapping exactly as its
software plugin exports it, same suffix -- and an ``index.json`` with the
names and dates. A file missing from the index, or an index entry whose
file is gone, is ignored rather than raised on.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from djmidi import user_paths

_LOGGER = logging.getLogger(__name__)
INDEX = "index.json"
MAX_NAME = 80
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Snapshot:
    name: str
    created: str  # ISO 8601, local time
    file: str  # file name inside the mapping's snapshot folder
    software: str
    path: Path


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.casefold()).strip("-") or "mapping"


def snapshot_dir(mapping_path: str | Path, root: str | Path | None = None) -> Path:
    mapping = Path(mapping_path).expanduser().resolve()
    digest = hashlib.sha1(str(mapping).encode("utf-8")).hexdigest()[:8]
    stem = mapping.name.split(".")[0]
    base = Path(root) if root is not None else user_paths.subfolder(user_paths.SNAPSHOTS)
    return base / f"{_slug(stem)}-{digest}"


def _read_index(folder: Path) -> list[dict]:
    try:
        raw = json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        _LOGGER.warning("Unreadable snapshot index in %s", folder)
        return []
    return [entry for entry in raw if isinstance(entry, dict)] if isinstance(raw, list) else []


def _write_index(folder: Path, entries: list[dict]) -> None:
    temp = folder / (INDEX + ".part")
    temp.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(folder / INDEX)


def list_snapshots(mapping_path: str | Path, root: str | Path | None = None) -> list[Snapshot]:
    """The mapping's snapshots, newest first."""
    folder = snapshot_dir(mapping_path, root)
    found = []
    for entry in _read_index(folder):
        try:
            snapshot = Snapshot(str(entry["name"]), str(entry["created"]), str(entry["file"]),
                                str(entry.get("software", "")), folder / str(entry["file"]))  # fmt: skip
        except KeyError:
            continue
        if snapshot.path.is_file() and snapshot.path.parent == folder:
            found.append(snapshot)
    return sorted(found, key=lambda snapshot: snapshot.created, reverse=True)


def save_snapshot(
    mapping_path: str | Path,
    name: str,
    text: str,
    software: str,
    *,
    now: datetime | None = None,
    root: str | Path | None = None,
) -> Snapshot:
    """Stores `text` (the exported mapping) as a snapshot called `name`."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("A snapshot needs a name")
    if len(name) > MAX_NAME:
        raise ValueError(f"A snapshot name is at most {MAX_NAME} characters")
    stamp = (now or datetime.now().astimezone()).replace(microsecond=0)
    folder = snapshot_dir(mapping_path, root)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = "".join(Path(mapping_path).suffixes) or ".txt"
    base = f"{stamp.strftime('%Y%m%d-%H%M%S')}-{_slug(name)[:40]}"
    file = base + suffix
    counter = 2
    while (folder / file).exists():
        file = f"{base}-{counter}{suffix}"
        counter += 1
    (folder / file).write_text(text, encoding="utf-8")
    entries = _read_index(folder)
    entry = {"name": name, "created": stamp.isoformat(), "file": file, "software": software}
    entries.append(entry)
    _write_index(folder, entries)
    return Snapshot(name, entry["created"], file, software, folder / file)


def delete_snapshot(snapshot: Snapshot) -> None:
    folder = snapshot.path.parent
    _write_index(folder, [entry for entry in _read_index(folder) if entry.get("file") != snapshot.file])
    snapshot.path.unlink(missing_ok=True)


__all__ = ["Snapshot", "delete_snapshot", "list_snapshots", "save_snapshot", "snapshot_dir"]
