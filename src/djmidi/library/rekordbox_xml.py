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


__all__ = [
    "FORMAT_VERSION",
    "RekordboxXmlTrack",
    "build_playlist_xml",
    "location_uri",
    "write_playlist_xml",
]
