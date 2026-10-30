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
from dataclasses import dataclass, replace
from pathlib import Path

from djmidi.catalog._registry import (
    _REGISTRY,
    ControlInfo,
    ControllerDefinition,
    detect_controller,
)
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
SOURCE_MIXXX = "mixxx"
SOURCE_COMMUNITY = "community"
# The manifest licence of a generated profile: it names where the data came from.
REKORDBOX_LICENSE = "derived from rekordbox's bundled MIDI mapping"
MIXXX_LICENSE = "derived from the Mixxx project's controller mapping (GPL)"
COMMUNITY_LICENSE = "contributed through a community submission"
_LICENSES = {SOURCE_REKORDBOX: REKORDBOX_LICENSE, SOURCE_MIXXX: MIXXX_LICENSE, SOURCE_COMMUNITY: COMMUNITY_LICENSE}
# When two library files name the same device, the first source here wins:
# a contributed profile was captured on the unit, the others are derived.
_SOURCE_PRIORITY = (SOURCE_COMMUNITY, SOURCE_REKORDBOX, SOURCE_MIXXX)
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
    # One dash per run of other characters: a plugin id refuses "--".
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "controller"


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


# --- profiles from Mixxx's mappings ----------------------------------------------

# Vendors whose name is two words in Mixxx's mapping names.
_TWO_WORD_VENDORS = ("american audio", "dj techtools", "native instruments", "stanton scs")
_SECTION_OF_GROUP = (
    (re.compile(r"^\[Channel\d+\]$"), "DECK"),
    (re.compile(r"^\[(Sampler|PreviewDeck)\d*\]$"), "SAMPLER"),
    (re.compile(r"^\[(Master|Mixer|Microphone|Auxiliary)\d*\]$"), "MIXER"),
    (re.compile(r"^\[(EffectRack|QuickEffectRack)"), "EFFECT"),
    (re.compile(r"^\[(Library|Playlist)\]$"), "BROWSE"),
)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _mixxx_section(group: str) -> str:
    return next((section for pattern, section in _SECTION_OF_GROUP if pattern.match(group)), "OTHER")


def mixxx_control_name(key: str) -> str:
    """A readable name for a Mixxx binding's key: ``hotcue_1_activate`` ->
    ``HOTCUE 1 ACTIVATE``; a script function's last meaningful part,
    ``MyCtrl.deck[0].playButton.input`` -> ``PLAY BUTTON``."""
    name = key.strip()
    if "." in name:
        parts = [part for part in name.split(".") if part not in ("input", "output")]
        name = re.sub(r"\[\d+\]$", "", parts[-1] if parts else name)
    name = _CAMEL.sub(" ", name).replace("_", " ")
    return " ".join(name.split()).upper() or key


def _mixxx_vendor(name: str) -> str:
    for vendor in _TWO_WORD_VENDORS:
        if name.casefold().startswith(vendor + " "):
            return name[: len(vendor)]
    return name.split()[0] if name.split() else ""


def build_mixxx_profiles(texts: Iterable[str], skip_names: Iterable[str] = ()) -> list[ControllerDefinition]:
    """One controller definition per Mixxx mapping text: its buttons (the
    Note On bindings) named after the Mixxx function they drive and grouped
    by Mixxx group. Mixxx names functions, not physical controls, so these
    are the coarsest profiles of the library. Devices named in `skip_names`
    (built-ins, rekordbox-derived profiles -- compared with and without the
    vendor) and mappings with fewer than :data:`MIN_ENTRIES` buttons are
    left out; several mappings of one device keep the first."""
    from djmidi.software.mixxx import parse_string

    skipped = {name.casefold() for name in skip_names}
    definitions: dict[str, ControllerDefinition] = {}
    for text in texts:
        config = parse_string(text)
        name = config.extra_attrs.get("device", "").strip()
        vendor = _mixxx_vendor(name)
        model = name[len(vendor) :].strip() if vendor else name
        if not name or name in definitions or name.casefold() in skipped or model.casefold() in skipped:
            continue
        if "unfinished" in name.casefold():
            continue  # its own authors say it isn't done
        rows: list[ControlInfo] = []
        for control in config.controls:
            if control.event_type != "Note On":
                continue
            mapping = next((m for u in control.userios if u.event == "click" for m in u.mappings), None)
            if mapping is None:
                continue
            section = _mixxx_section(mapping.extra_attrs.get("group", ""))
            rows.append(ControlInfo(name, section, mixxx_control_name(mapping.tag), "NOTE", (control.channel,), control.control))
        entries = _numbered(merge_by_channel(rows))
        if len(entries) < MIN_ENTRIES:
            continue
        definitions[name] = ControllerDefinition(
            name=name,
            plugin_id=USER_PLUGIN_PREFIX + _profile_slug(name),
            manufacturer=vendor or None,
            supported_software=("mixxx",),
            port_names=(model,) if model and model != name and len(model) >= 3 else (),
            static_entries=entries,
            section_order=infer_section_order(entries),
        )
    return [definitions[name] for name in sorted(definitions, key=str.casefold)]


def _numbered(entries: list[ControlInfo]) -> list[ControlInfo]:
    """Keeps (section, name) unique: a name used for several notes (a
    function bound to two buttons, or to a button and its SHIFT layer)
    gets " #2", " #3"... in order."""
    seen: dict[tuple[str, str], int] = {}
    unique = []
    for entry in entries:
        key = (entry.section, entry.name)
        seen[key] = seen.get(key, 0) + 1
        unique.append(entry if seen[key] == 1 else replace(entry, name=f"{entry.name} #{seen[key]}"))
    return unique


def library_document(definition: ControllerDefinition, source: str = SOURCE_REKORDBOX) -> dict:
    """The JSON a library profile file holds: an ordinary installed-profile
    document (so installing it is a copy), whose licence names its source."""
    document = profile_document(definition)
    document["manifest"]["license"] = _LICENSES[source]
    document["controller"]["library_source"] = source
    return document


def write_library(
    definitions: Iterable[ControllerDefinition], directory: str | Path, source: str = SOURCE_REKORDBOX
) -> list[Path]:
    """Writes one ``<slug>.json`` per definition into `directory`, removing
    the JSON files of devices no longer generated."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for definition in definitions:
        path = folder / f"{_profile_slug(definition.name)}.json"
        path.write_text(json.dumps(library_document(definition, source), indent=1) + "\n", encoding="utf-8")
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
    return sorted(_one_per_name(profiles), key=lambda profile: profile.name.casefold())


def _priority(profile: LibraryProfile) -> int:
    try:
        return _SOURCE_PRIORITY.index(profile.source)
    except ValueError:
        return len(_SOURCE_PRIORITY)


def _one_per_name(profiles: list[LibraryProfile]) -> list[LibraryProfile]:
    best: dict[str, LibraryProfile] = {}
    for profile in profiles:
        key = profile.name.casefold()
        if key not in best or _priority(profile) < _priority(best[key]):
            best[key] = profile
    return list(best.values())


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


def _mentions(port: str, name: str) -> bool:
    """Whether `name` appears in `port` as a whole word (``DDJ-SB`` is in
    ``PIONEER DDJ-SB`` and ``DDJ-SB 1``, not in ``DDJ-SB2``)."""
    if not name.strip():
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(name.casefold())}(?![a-z0-9])", port.casefold()) is not None


def connected_library_profiles(
    port_names: Iterable[str], profiles: Iterable[LibraryProfile]
) -> list[tuple[LibraryProfile, str]]:
    """The library profiles worth offering for the connected MIDI ports:
    one whose name or a port name of it appears in a port, isn't installed
    yet, and isn't already covered -- a port some registered controller
    names exactly (a built-in, or an installed profile) is skipped. Each
    profile once, with the first port it matched, in port order."""
    candidates = [profile for profile in profiles if not profile.is_installed and not profile.is_built_in]
    found: list[tuple[LibraryProfile, str]] = []
    for port in port_names:
        if any(match.score == 100 for match in detect_controller(port, include_disabled=True)):
            continue
        for profile in candidates:
            if any(found_profile.name == profile.name for found_profile, _port in found):
                continue
            if any(_mentions(port, name) for name in (profile.name, *profile.port_names)):
                found.append((profile, port))
    return found


__all__ = [
    "COMMUNITY_LICENSE",
    "LIBRARY_DIR",
    "MIN_ENTRIES",
    "MIXXX_LICENSE",
    "REKORDBOX_LICENSE",
    "SOURCE_COMMUNITY",
    "SOURCE_MIXXX",
    "SOURCE_REKORDBOX",
    "LibraryProfile",
    "build_mixxx_profiles",
    "build_rekordbox_profiles",
    "connected_library_profiles",
    "device_name",
    "install_library_profile",
    "library_document",
    "list_library_profiles",
    "mixxx_control_name",
    "write_library",
]
