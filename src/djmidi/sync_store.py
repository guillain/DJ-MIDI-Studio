"""Controller sync sets as visible files (issue #175 phase 3): one JSON file
per controller and scene in the user's ``Sync`` folder, instead of a list
buried in preferences.json. Qt-free.

File names stay readable: ``ddj-xp2.json`` holds the controller's
``Default`` scene (the only name used before scenes existed, issue #188, so
those files keep loading unchanged) and ``ddj-xp2.tek.json`` its ``Tek``
scene. Slugs only contain ``[a-z0-9-]``, so the ``.`` separator can't be
confused with either part. The name is only a label: loading reads the
controller and scene from each file's content, never from its name.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from djmidi.controller_sync import DEFAULT_SCENE, ControllerSyncSet

_LOGGER = logging.getLogger(__name__)


def _slug(text: str, fallback: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in text.lower()).strip("-")
    return slug or fallback


def sync_file_name(controller: str, scene: str = DEFAULT_SCENE) -> str:
    stem = _slug(controller, "controller")
    if scene != DEFAULT_SCENE:
        stem = f"{stem}.{_slug(scene, 'scene')}"
    return f"{stem}.json"


def load_sync_sets(directory: str | Path) -> list[ControllerSyncSet]:
    """Every readable sync set in `directory`, one per controller and scene
    (the last file wins on a duplicate). A file without a ``scene`` key is
    the controller's ``Default`` scene. A broken file is logged and skipped
    rather than losing the others."""
    folder = Path(directory)
    sets: dict[tuple[str, str], ControllerSyncSet] = {}
    if not folder.is_dir():
        return []
    for path in sorted(folder.glob("*.json")):
        try:
            sync_set = ControllerSyncSet.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            _LOGGER.warning("Skipped sync set file %s: %s", path, exc)
            continue
        sets[sync_set.key] = sync_set
    return list(sets.values())


def save_sync_sets(directory: str | Path, sync_sets: Iterable[ControllerSyncSet]) -> None:
    """Write one file per set and remove the files of sets that are gone, so
    the folder always mirrors the app's list. Two sets whose names slug to
    the same file (``"DDJ XP2"`` / ``"DDJ-XP2"``) get a numbered suffix
    rather than overwriting each other."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    keep: set[str] = set()
    for sync_set in sync_sets:
        name = sync_file_name(sync_set.controller, sync_set.scene)
        stem, number = name.removesuffix(".json"), 2
        while name in keep:
            name, number = f"{stem}-{number}.json", number + 1
        keep.add(name)
        (folder / name).write_text(json.dumps(sync_set.to_dict(), indent=2) + "\n", encoding="utf-8")
    for path in folder.glob("*.json"):
        if path.name not in keep:
            path.unlink()


def adopt_sync_sets(directory: str | Path, from_preferences: list[ControllerSyncSet]) -> list[ControllerSyncSet]:
    """The sync sets the app should use at launch: the folder's when it has
    any; otherwise the ones still stored in preferences.json, moved into the
    folder (the one-time migration)."""
    stored = load_sync_sets(directory)
    if stored:
        return stored
    if from_preferences:
        save_sync_sets(directory, from_preferences)
        _LOGGER.info("Moved %d sync set(s) from preferences.json to %s", len(from_preferences), directory)
    return list(from_preferences)


__all__ = ["adopt_sync_sets", "load_sync_sets", "save_sync_sets", "sync_file_name"]
