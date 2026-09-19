from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from os import PathLike


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
