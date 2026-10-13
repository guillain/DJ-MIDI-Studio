"""First-run setup wizard decisions (issue #251).

Qt-free so it can be tested without a QApplication: the GUI wizard
(``gui/first_run_wizard.py``) asks this module whether to show itself, which
connected MIDI ports match a controller profile, and which Serato mappings
exist in Serato's standard folder. Everything here only *reads*: the Serato
folder is listed, never written to, and detection only looks at port names
(no MIDI is sent, no controller data is invented).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from djmidi import catalog
from djmidi.file_locations import software_mapping_dirs

_LOGGER = logging.getLogger(__name__)

# QSettings key recording that the wizard was finished or skipped once.
WIZARD_DONE_SETTINGS_KEY = "ui/first_run_wizard_done"
# A real Serato MIDI folder holds a handful of files; cap the list anyway.
MAPPING_LIMIT = 20


def should_show_wizard(preferences_existed: bool, wizard_done: bool) -> bool:
    """Only on a genuine first launch: no preferences file yet, and the
    wizard was never finished or skipped (Help reopens it on demand)."""
    return not preferences_existed and not wizard_done


@dataclass(frozen=True)
class DetectedController:
    """One controller profile matched by one or more connected MIDI ports."""

    controller: str
    ports: tuple[str, ...]
    score: int
    reason: str


@dataclass(frozen=True)
class ControllerDetection:
    controllers: tuple[DetectedController, ...] = ()
    # Ports no registered profile recognized (Controller Setup can build one).
    unmatched_ports: tuple[str, ...] = ()


def detect_connected_controllers(port_names: Iterable[str]) -> ControllerDetection:
    """Best profile per connected port (``catalog.detect_controller``), merged
    per controller so a device exposing several ports is proposed once."""
    best: dict[str, DetectedController] = {}
    order: list[str] = []
    unmatched: list[str] = []
    for port in dict.fromkeys(port_names):  # dedupe, keep order
        matches = catalog.detect_controller(port)
        if not matches:
            unmatched.append(port)
            continue
        match = matches[0]
        name = match.controller.name
        previous = best.get(name)
        if previous is None:
            order.append(name)
            best[name] = DetectedController(name, (port,), match.score, match.reason)
        else:
            best[name] = DetectedController(
                name,
                (*previous.ports, port),
                max(previous.score, match.score),
                previous.reason if previous.score >= match.score else match.reason,
            )
    _LOGGER.info("First-run detection: %s; unmatched ports: %s", order or "no controller", unmatched or "none")
    return ControllerDetection(tuple(best[name] for name in order), tuple(unmatched))


@dataclass(frozen=True)
class MappingCandidate:
    path: Path
    modified: float = field(compare=False)


def find_serato_mappings(home: Path | None = None, limit: int = MAPPING_LIMIT) -> list[MappingCandidate]:
    """Serato MIDI mappings (``*.xml``) in Serato's standard MIDI folder
    (``~/Music/_Serato_/MIDI/Xml``), newest first. Read-only: the folder is
    only listed, and a missing or unreadable folder simply yields nothing."""
    folder = software_mapping_dirs("serato", home)[0]
    found: list[MappingCandidate] = []
    try:
        entries = list(folder.iterdir()) if folder.is_dir() else []
    except OSError as exc:
        _LOGGER.warning("Cannot list Serato MIDI folder %s: %s", folder, exc)
        return []
    for entry in entries:
        if entry.name.startswith(".") or entry.suffix.lower() != ".xml":
            continue
        try:
            if not entry.is_file():
                continue
            found.append(MappingCandidate(entry, entry.stat().st_mtime))
        except OSError:
            continue
    found.sort(key=lambda candidate: (-candidate.modified, candidate.path.name.casefold()))
    return found[:limit]


@dataclass(frozen=True)
class FirstRunChoices:
    """What the user picked in the wizard; the window applies it afterwards."""

    # The detected profile to show on the Dashboard (None = leave it as is).
    controller: str | None = None
    mapping: Path | None = None
    record_sync_set: bool = False


__all__ = [
    "MAPPING_LIMIT",
    "WIZARD_DONE_SETTINGS_KEY",
    "ControllerDetection",
    "DetectedController",
    "FirstRunChoices",
    "MappingCandidate",
    "detect_connected_controllers",
    "find_serato_mappings",
    "should_show_wizard",
]
