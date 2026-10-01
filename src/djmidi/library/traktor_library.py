from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path


@dataclass
class NmlTrack:
    title: str
    artist: str
    location: str
    key: str
    bpm: float | None = None
    musical_key: str | None = None
    musical_key_value: int | None = None
    album: str | None = None
    volume: str | None = None


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _track_from_entry(entry: ET.Element) -> NmlTrack:
    location_el = entry.find("LOCATION")
    volume = location_el.get("VOLUME") if location_el is not None else None
    directory = location_el.get("DIR", "") if location_el is not None else ""
    filename = location_el.get("FILE", "") if location_el is not None else ""
    # Traktor's own path encoding: DIR/FILE use "/:" as the component
    # separator (a leftover of classic Mac OS ":"-separated paths), and
    # PLAYLISTS/ENTRY/PRIMARYKEY's KEY is exactly VOLUME + DIR + FILE
    # concatenated verbatim -- confirmed against the real collection.nml.
    # `location` swaps in "/" for readability but drops VOLUME, since this
    # project has no reliable way to know how a given volume is mounted.
    key = f"{volume or ''}{directory}{filename}"
    location = f"{directory}{filename}".replace("/:", "/")

    tempo_el = entry.find("TEMPO")
    bpm = _float_or_none(tempo_el.get("BPM")) if tempo_el is not None else None

    info_el = entry.find("INFO")
    musical_key = info_el.get("KEY") if info_el is not None else None

    musical_key_el = entry.find("MUSICAL_KEY")
    musical_key_value = _int_or_none(musical_key_el.get("VALUE")) if musical_key_el is not None else None

    album_el = entry.find("ALBUM")
    album = album_el.get("TITLE") if album_el is not None else None

    return NmlTrack(
        title=entry.get("TITLE", ""),
        artist=entry.get("ARTIST", ""),
        location=location,
        key=key,
        bpm=bpm,
        musical_key=musical_key,
        musical_key_value=musical_key_value,
        album=album,
        volume=volume,
    )


def _is_collection_entry(elem: ET.Element) -> bool:
    # A COLLECTION/ENTRY carries LOCATION/TITLE/ARTIST; a PLAYLISTS/ENTRY
    # only ever carries a PRIMARYKEY child. Checking for LOCATION avoids
    # needing parent-tracking, which stdlib ElementTree doesn't provide.
    return elem.tag == "ENTRY" and elem.find("LOCATION") is not None


def parse_collection(path: str | PathLike[str]) -> list[NmlTrack]:
    tracks: list[NmlTrack] = []
    for _event, elem in ET.iterparse(path, events=("end",)):
        if _is_collection_entry(elem):
            tracks.append(_track_from_entry(elem))
            elem.clear()
    return tracks


def _collect_playlists(playlists_elem: ET.Element, out: dict[str, list[str]]) -> None:
    for node in playlists_elem.iter("NODE"):
        if node.get("TYPE") != "PLAYLIST":
            continue
        name = node.get("NAME", "")
        playlist_el = node.find("PLAYLIST")
        if playlist_el is None:
            continue
        keys: list[str] = []
        for entry in playlist_el.findall("ENTRY"):
            primary_key = entry.find("PRIMARYKEY")
            if primary_key is None:
                continue
            key = primary_key.get("KEY")
            if key is not None:
                keys.append(key)
        out[name] = keys


def parse_playlists(path: str | PathLike[str]) -> dict[str, list[str]]:
    playlists: dict[str, list[str]] = {}
    for _event, elem in ET.iterparse(path, events=("end",)):
        if _is_collection_entry(elem):
            # Not needed here, but pass over the (potentially huge)
            # COLLECTION section without retaining every entry's content.
            elem.clear()
        elif elem.tag == "PLAYLISTS":
            _collect_playlists(elem, playlists)
            elem.clear()
    return playlists


# -- writing a standalone playlist .nml --------------------------------------
#
# Shape copied from the .nml files Traktor Pro 4 itself writes for a single
# playlist (its History/*.nml files, checked read-only on the maintainer's
# machine): a COLLECTION holding one ENTRY per distinct track (TITLE/ARTIST
# attributes + a LOCATION), an empty SETS, and PLAYLISTS/$ROOT folder with one
# PLAYLIST node whose ENTRY/PRIMARYKEY KEYs are VOLUME+DIR+FILE. A user list
# is TYPE="LIST" with a 32-hex UUID, as in the real collection.nml. Nothing
# Traktor computes itself (AUDIO_ID, analysis, cue points) is fabricated:
# Traktor reads tags and analyses tracks on import.

_NML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n'


@dataclass(frozen=True)
class NmlExportTrack:
    volume: str
    directory: str  # Traktor-encoded, e.g. "/:Users/:me/:Music/:"
    filename: str
    title: str = ""
    artist: str = ""

    @property
    def key(self) -> str:
        """The PRIMARYKEY a playlist entry uses to point at this track."""
        return f"{self.volume}{self.directory}{self.filename}"


def encode_nml_dir(components: Sequence[str]) -> str:
    """``["Users", "me"]`` -> ``"/:Users/:me/:"`` (Traktor's DIR encoding)."""
    return "".join(f"/:{component}" for component in components) + "/:"


def build_playlist_nml(playlist_name: str, tracks: Iterable[NmlExportTrack]) -> bytes:
    tracks = list(tracks)
    unique: dict[str, NmlExportTrack] = {}
    for track in tracks:
        unique.setdefault(track.key, track)

    root = ET.Element("NML", VERSION="20")
    ET.SubElement(root, "HEAD", COMPANY="www.native-instruments.com", PROGRAM="Traktor Pro 4")
    collection = ET.SubElement(root, "COLLECTION", ENTRIES=str(len(unique)))
    for track in unique.values():
        attributes = {name: value for name, value in (("TITLE", track.title), ("ARTIST", track.artist)) if value}
        entry = ET.SubElement(collection, "ENTRY", attributes)
        ET.SubElement(
            entry,
            "LOCATION",
            DIR=track.directory,
            FILE=track.filename,
            VOLUME=track.volume,
            VOLUMEID=track.volume,
        )
    ET.SubElement(root, "SETS", ENTRIES="0")
    playlists = ET.SubElement(root, "PLAYLISTS")
    folder = ET.SubElement(playlists, "NODE", TYPE="FOLDER", NAME="$ROOT")
    subnodes = ET.SubElement(folder, "SUBNODES", COUNT="1")
    node = ET.SubElement(subnodes, "NODE", TYPE="PLAYLIST", NAME=playlist_name)
    playlist = ET.SubElement(node, "PLAYLIST", ENTRIES=str(len(tracks)), TYPE="LIST", UUID=uuid.uuid4().hex)
    for track in tracks:
        entry = ET.SubElement(playlist, "ENTRY")
        ET.SubElement(entry, "PRIMARYKEY", TYPE="TRACK", KEY=track.key)
    ET.SubElement(root, "INDEXING")
    return _NML_DECLARATION + ET.tostring(root, encoding="utf-8", short_empty_elements=False)


def write_playlist_nml(path: str | PathLike[str], playlist_name: str, tracks: Iterable[NmlExportTrack]) -> None:
    """Writes a new single-playlist .nml at exactly `path` (never a real
    collection.nml on its own initiative), for Traktor's Import Playlist."""
    Path(path).write_bytes(build_playlist_nml(playlist_name, tracks))
