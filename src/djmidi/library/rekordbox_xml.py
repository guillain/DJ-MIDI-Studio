"""A playlist as a rekordbox XML file (issue #441).

Written from Pioneer's own "XML file format for playlists sharing" list
(cdn.rekordbox.com/files/20200410160904/xml_format_list.pdf), linked from
rekordbox.com's "rekordbox for Developers" page: rekordbox shows such a file
in its Bridge / "Imported Library" view, from which playlists are imported.

What the list says and this module follows:

- root ``DJ_PLAYLISTS Version="1.0.0"`` holding ``PRODUCT Name Version Company``;
- ``COLLECTION Entries=N`` holds only the tracks the playlists use, one
  ``TRACK`` each; ``Location`` is the only essential attribute, a URI with
  media "expected in file://localhost/";
- ``PLAYLISTS`` holds a ``NODE Type="0" Name="ROOT" Count=N`` folder, and each
  playlist is a ``NODE Type="1" Name Entries KeyType`` (0 = Track ID) with one
  ``TRACK Key=<TrackID>`` per entry;
- strings are UTF-8 with XML entities, numbers locale-independent
  (``TotalTime`` in whole seconds, ``AverageBpm`` with a dot).

A separate file at a path the user chooses: rekordbox's own library is never
written. Nothing rekordbox computes (beat grid, cues) is written. Qt-free.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from urllib.parse import quote
from xml.etree import ElementTree as ET

FORMAT_VERSION = "1.0.0"
PRODUCT_NAME = "DJ MIDI Studio"
PRODUCT_COMPANY = "DJ MIDI Studio"
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class RekordboxXmlTrack:
    """One track to write: its path, plus whatever tags are known."""

    path: str
    name: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    bpm: float | None = None
    tonality: str = ""
    total_time: float | None = None


def location_uri(path: str) -> str:
    """``file://localhost/...`` with the path percent-encoded (a Windows
    drive path becomes ``file://localhost/C:/...``)."""
    if _WINDOWS_DRIVE.match(path):
        posix = "/" + PureWindowsPath(path).as_posix()
    else:
        posix = Path(path).as_posix()
        if not posix.startswith("/"):
            posix = "/" + posix
    return "file://localhost" + quote(posix, safe="/:")


def _number(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def build_playlist_xml(
    playlist_name: str, tracks: Iterable[RekordboxXmlTrack], product_version: str = ""
) -> str:
    """The XML text for one playlist (entries in order; a track listed twice
    is one COLLECTION entry used twice)."""
    tracks = list(tracks)
    ids: dict[str, int] = {}
    unique: list[RekordboxXmlTrack] = []
    for track in tracks:
        if track.path not in ids:
            ids[track.path] = len(ids) + 1
            unique.append(track)

    root = ET.Element("DJ_PLAYLISTS", {"Version": FORMAT_VERSION})
    ET.SubElement(
        root, "PRODUCT", {"Name": PRODUCT_NAME, "Version": product_version or "", "Company": PRODUCT_COMPANY}
    )
    collection = ET.SubElement(root, "COLLECTION", {"Entries": str(len(unique))})
    for track in unique:
        attrs = {"TrackID": str(ids[track.path])}
        for key, value in (
            ("Name", track.name),
            ("Artist", track.artist),
            ("Album", track.album),
            ("Genre", track.genre),
            ("Tonality", track.tonality),
        ):
            if value:
                attrs[key] = value
        if track.bpm:
            attrs["AverageBpm"] = _number(track.bpm)
        if track.total_time:
            attrs["TotalTime"] = str(round(track.total_time))
        attrs["Location"] = location_uri(track.path)
        ET.SubElement(collection, "TRACK", attrs)

    playlists = ET.SubElement(root, "PLAYLISTS")
    folder = ET.SubElement(playlists, "NODE", {"Type": "0", "Name": "ROOT", "Count": "1"})
    playlist = ET.SubElement(
        folder, "NODE", {"Name": playlist_name, "Type": "1", "KeyType": "0", "Entries": str(len(tracks))}
    )
    for track in tracks:
        ET.SubElement(playlist, "TRACK", {"Key": str(ids[track.path])})
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write_playlist_xml(
    path: str | os.PathLike[str],
    playlist_name: str,
    tracks: Iterable[RekordboxXmlTrack],
    product_version: str = "",
) -> None:
    """Writes the file at exactly `path` (through a ``.part`` file)."""
    path = Path(path)
    part = path.with_name(path.name + ".part")
    part.write_text(build_playlist_xml(playlist_name, tracks, product_version), encoding="utf-8")
    os.replace(part, path)


def path_from_location(location: str) -> str:
    """The inverse of `location_uri`: a ``file://localhost/...`` (or
    ``file:///...``) URI back to a filesystem path; a Windows drive
    (``/C:/...``) loses its leading slash."""
    from urllib.parse import unquote, urlparse

    parsed = urlparse(location)
    if parsed.scheme != "file":
        return unquote(location)
    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:/", path):
        return path[1:]
    return path


def read_playlists(path: str | os.PathLike[str]) -> dict[str, list[str]]:
    """Every playlist of a rekordbox XML file (issue #446), read-only:
    ``{name: [track paths in order]}``, a playlist inside folders named
    ``"Folder / Sub / Playlist"``. Tracks are resolved through the
    COLLECTION's ``TrackID`` (``KeyType="0"``) or taken as ``Location``s
    (``KeyType="1"``); an entry that resolves to nothing is skipped. The
    COLLECTION is streamed (``iterparse``) and cleared as it goes, since a
    full rekordbox collection export can be large."""
    locations: dict[str, str] = {}
    playlists: dict[str, list[str]] = {}
    stack: list[str] = []  # element tags from the root
    folders: list[str] = []  # folder names under PLAYLISTS (the top ROOT excluded)
    pushed: list[bool] = []  # per open NODE: whether it added a folder name
    current: tuple[str, str, list[str]] | None = None  # (name, key type, keys)
    for event, element in ET.iterparse(os.fspath(path), events=("start", "end")):
        tag = element.tag
        if event == "start":
            stack.append(tag)
            if tag == "NODE" and "PLAYLISTS" in stack:
                name = element.get("Name", "")
                is_top = len(pushed) == 0
                if element.get("Type") == "1":
                    current = (" / ".join([*folders, name]), element.get("KeyType", "0"), [])
                    pushed.append(False)
                elif is_top:  # the ROOT folder itself
                    pushed.append(False)
                else:
                    folders.append(name)
                    pushed.append(True)
            elif tag == "TRACK" and current is not None and stack[-2] == "NODE":
                current[2].append(element.get("Key", ""))
            continue
        stack.pop()
        if tag == "TRACK" and stack and stack[-1] == "COLLECTION":
            track_id, location = element.get("TrackID"), element.get("Location")
            if track_id is not None and location:
                locations[track_id] = path_from_location(location)
            element.clear()
        elif tag == "NODE" and "PLAYLISTS" in stack:
            if current is not None and element.get("Type") == "1":
                name, key_type, keys = current
                resolved = [
                    path_from_location(key) if key_type == "1" else locations.get(key, "") for key in keys
                ]
                playlists[name] = [entry for entry in resolved if entry]
                current = None
            if pushed.pop():
                folders.pop()
    return playlists


__all__ = [
    "FORMAT_VERSION",
    "RekordboxXmlTrack",
    "build_playlist_xml",
    "location_uri",
    "path_from_location",
    "read_playlists",
    "write_playlist_xml",
]
