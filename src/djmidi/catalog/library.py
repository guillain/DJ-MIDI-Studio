"""The bundled controller profile library: ready-made JSON profiles the user
installs on demand, rather than built-in controllers registered at startup.

The library's profiles come from the MIDI mappings rekordbox 7 ships for
each Pioneer DJ / AlphaTheta device (`software/rekordbox/README.md`):
:func:`build_rekordbox_profiles` turns a folder of those ``.midi.csv`` files
into one profile per device -- its buttons and pads, named and grouped as in
rekordbox (:func:`djmidi.software.rekordbox.profile_rows`) -- and
``scripts/generate_rekordbox_profiles.py`` writes them under
``controllers/library/rekordbox/``. A device rekordbox lists several times
(``DDJ-SB MIDI``, ``DDJ-RX 2IN2OUT``: the same messages under another port
name) becomes one profile that recognizes every name. Devices that already
are built-in controllers are left out.

They aren't registered until installed: registering ~60 controllers at
startup would crowd every controller list and make most lookups ambiguous
(note 11 on channel 1 is PLAY on dozens of Pioneer devices).
:func:`install_library_profile` copies one into the user's Controllers
folder and registers it, exactly like a profile Controller Setup installs;
from then on it loads at every launch.

Qt-free, so the generator script and tests share it.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from djmidi.catalog._registry import _REGISTRY, ControlInfo, ControllerDefinition
from djmidi.catalog.codegen import infer_section_order, merge_by_channel
from djmidi.catalog.profile import (
    USER_PLUGIN_PREFIX,
    load_controller_profile,
    profile_document,
)

if getattr(sys, "frozen", False):
    _RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
else:
    _RESOURCE_ROOT = Path(__file__).resolve().parents[3]
LIBRARY_DIR = _RESOURCE_ROOT / "controllers" / "library"

SOURCE_REKORDBOX = "rekordbox"
# The manifest licence of a generated profile: it names where the data came from.
REKORDBOX_LICENSE = "derived from rekordbox's bundled MIDI mapping"
_VENDOR_PREFIX = re.compile(r"^(?:pioneer dj|pioneer)\s+", re.IGNORECASE)
# Another port name for the same device: identical messages (checked on
# every pair rekordbox 7 ships), so it only adds a port name.
_PORT_VARIANT = re.compile(r"\s+(?:MIDI|2IN2OUT|\(\d+\))$", re.IGNORECASE)
# AlphaTheta-branded devices; every other one in the files is Pioneer DJ.
_ALPHATHETA = frozenset({"EUPHONIA", "OMNIS-DUO"})
# A file with fewer named buttons/pads than this isn't worth a profile.
MIN_ENTRIES = 5


@dataclass(frozen=True)
class LibraryProfile:
    """One profile file of the library, read from its manifest."""

    name: str
    path: Path
    vendor: str
    entries: int
    port_names: tuple[str, ...]
    source: str

    @property
    def is_built_in(self) -> bool:
        definition = _REGISTRY.get(self.name)
        return definition is not None and not (definition.plugin_id or "").startswith(USER_PLUGIN_PREFIX)

    @property
    def is_installed(self) -> bool:
        definition = _REGISTRY.get(self.name)
        return definition is not None and (definition.plugin_id or "").startswith(USER_PLUGIN_PREFIX)


def device_name(header_name: str) -> str:
    """The name a rekordbox file's device gets in the library: without the
    vendor prefix and the port-variant suffix (``PIONEER DDJ-SX 2IN2OUT``
    -> ``DDJ-SX``)."""
    name = _VENDOR_PREFIX.sub("", header_name.strip())
    return _PORT_VARIANT.sub("", name).strip()


def _profile_slug(name: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in name.lower()).strip("-") or "controller"


def build_rekordbox_profiles(
    texts: Iterable[str], skip_names: Iterable[str] = ()
) -> list[ControllerDefinition]:
    """One controller definition per device in rekordbox mapping CSV texts,
    sorted by name. Devices named in `skip_names` (the built-ins) and files
    with fewer than :data:`MIN_ENTRIES` buttons/pads are left out."""
    from djmidi.software.rekordbox import parse_string, profile_rows

    skipped = {name.casefold() for name in skip_names}
    rows_by_device: dict[str, list[ControlInfo]] = {}
    ports_by_device: dict[str, list[str]] = {}
    for text in texts:
        config = parse_string(text)
        header = config.extra_attrs.get("device", "").strip()
        name = device_name(header)
        if not name or name.casefold() in skipped:
            continue
        ports_by_device.setdefault(name, [])
        if header not in ports_by_device[name]:
            ports_by_device[name].append(header)
        if name in rows_by_device:
            continue  # a port variant: same messages as the file already read
        rows_by_device[name] = [
            ControlInfo(name, row.section, row.name, row.kind, (row.channel,), row.data1)  # type: ignore[arg-type]
            for row in profile_rows(config)
        ]
    definitions = []
    for name in sorted(rows_by_device, key=str.casefold):
        entries = merge_by_channel(rows_by_device[name])
        if len(entries) < MIN_ENTRIES:
            continue
        definitions.append(
            ControllerDefinition(
                name=name,
                plugin_id=USER_PLUGIN_PREFIX + _profile_slug(name),
                manufacturer="AlphaTheta" if name.upper() in _ALPHATHETA else "Pioneer DJ",
                supported_software=("rekordbox",),
                port_names=tuple(ports_by_device[name]),
                static_entries=entries,
                section_order=infer_section_order(entries),
            )
        )
    return definitions


def library_document(definition: ControllerDefinition) -> dict:
    """The JSON a library profile file holds: an ordinary installed-profile
    document (so installing it is a copy), whose licence names its source."""
    document = profile_document(definition)
    document["manifest"]["license"] = REKORDBOX_LICENSE
    document["controller"]["library_source"] = SOURCE_REKORDBOX
    return document


def write_library(definitions: Iterable[ControllerDefinition], directory: str | Path) -> list[Path]:
    """Writes one ``<slug>.json`` per definition into `directory`, removing
    the JSON files of devices no longer generated."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for definition in definitions:
        path = folder / f"{_profile_slug(definition.name)}.json"
        path.write_text(json.dumps(library_document(definition), indent=1) + "\n", encoding="utf-8")
        written.append(path)
    for stale in set(folder.glob("*.json")) - set(written):
        stale.unlink()
    return written


def list_library_profiles(directory: str | Path = LIBRARY_DIR) -> list[LibraryProfile]:
    """Every readable profile under `directory` (searched recursively),
    sorted by name; an unreadable file is skipped."""
    folder = Path(directory)
    if not folder.is_dir():
        return []
    profiles = []
    for path in sorted(folder.rglob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            controller = raw["controller"]
            profiles.append(
                LibraryProfile(
                    name=str(raw["manifest"]["name"]),
                    path=path,
                    vendor=str(raw["manifest"].get("vendor", "")),
                    entries=len(controller.get("entries", [])),
                    port_names=tuple(controller.get("port_names", ())),
                    source=str(controller.get("library_source", "")),
                )
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(profiles, key=lambda profile: profile.name.casefold())


def install_library_profile(profile: LibraryProfile, controllers_dir: str | Path) -> ControllerDefinition:
    """Copies `profile` into the user's Controllers folder and registers it
    (replacing an earlier install of it). Raises ``ValueError`` for a name a
    built-in controller already uses."""
    if profile.is_built_in:
        raise ValueError(f"'{profile.name}' is already a built-in controller")
    target = Path(controllers_dir) / f"{_profile_slug(profile.name)}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(profile.path, target)
    return load_controller_profile(target, replace=True)


__all__ = [
    "LIBRARY_DIR",
    "MIN_ENTRIES",
    "REKORDBOX_LICENSE",
    "SOURCE_REKORDBOX",
    "LibraryProfile",
    "build_rekordbox_profiles",
    "device_name",
    "install_library_profile",
    "library_document",
    "list_library_profiles",
    "write_library",
]
