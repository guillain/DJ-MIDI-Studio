from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen.id3 import COMM, ID3, TALB, TBPM, TCON, TIT2, TKEY, TPE1, TXXX
from mutagen.mp4 import MP4

# Fields this app actively manages -- everything else in a real file's tags
# (duplicate ID3v1 mirrors, old-software preference frames, ReplayGain, ...)
# is left alone unless `clean_noise_frames` is called explicitly.
MANAGED_FIELDS = frozenset({"title", "artist", "album", "genre", "bpm", "key", "comment", "rating", "energy"})

# Serato/Traktor binary blobs that must never be touched by a metadata write,
# confirmed against the maintainer's real files (issue #126). GEOB frames are
# matched by description prefix since Serato varies the exact set present
# per file (Overview/Analysis/Autotags/Markers_/Markers2/BeatGrid/Offsets_).
_PROTECTED_GEOB_PREFIX = "Serato "
_PROTECTED_PRIV_OWNER = "TRAKTOR4"
_PROTECTED_TXXX_DESCS = frozenset({"energylevel", "style"})
_PROTECTED_VORBIS_PREFIX = "serato_"


@dataclass
class TrackMetadata:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    bpm: float | None = None
    key: str | None = None
    comment: str | None = None
    rating: str | None = None
    energy: str | None = None


def read_metadata(path: str | Path) -> TrackMetadata | None:
    audio = mutagen.File(path)
    if audio is None:
        return None
    if isinstance(audio.tags, ID3):
        return _read_id3(audio.tags)
    if isinstance(audio, MP4):
        return _read_mp4(audio.tags)
    if _looks_like_vorbis(audio.tags):
        return _read_vorbis(audio.tags)
    return TrackMetadata()


def _looks_like_vorbis(tags: object) -> bool:
    return tags is not None and hasattr(tags, "get") and hasattr(tags, "keys") and not isinstance(tags, ID3)


def write_metadata(path: str | Path, **fields: object) -> None:
    unknown = set(fields) - MANAGED_FIELDS
    if unknown:
        raise ValueError(f"unknown metadata field(s): {sorted(unknown)}")
    audio = mutagen.File(path)
    if audio is None:
        raise ValueError(f"unrecognized or unreadable audio file: {path}")
    if audio.tags is None:
        audio.add_tags()
    if isinstance(audio.tags, ID3):
        _write_id3(audio.tags, fields)
    elif isinstance(audio, MP4):
        _write_mp4(audio.tags, fields)
    elif _looks_like_vorbis(audio.tags):
        _write_vorbis(audio.tags, fields)
    else:
        raise ValueError(f"unsupported tag format for {path}: {type(audio.tags)!r}")
    audio.save()


# --- ID3 (MP3, AIFF) -----------------------------------------------------

_ID3_TEXT_FRAMES = {
    "title": (TIT2, "TIT2"),
    "artist": (TPE1, "TPE1"),
    "album": (TALB, "TALB"),
    "genre": (TCON, "TCON"),
    "key": (TKEY, "TKEY"),
}


def _id3_primary_comment(tags: ID3) -> str | None:
    for frame in tags.getall("COMM"):
        if frame.desc == "":
            return str(frame.text[0]) if frame.text else None
    return None


def _id3_txxx(tags: ID3, desc: str) -> str | None:
    for frame in tags.getall("TXXX"):
        if frame.desc.lower() == desc.lower():
            return str(frame.text[0]) if frame.text else None
    return None


def _read_id3(tags: ID3) -> TrackMetadata:
    meta = TrackMetadata()
    for field_name, (_, frame_id) in _ID3_TEXT_FRAMES.items():
        frames = tags.getall(frame_id)
        if frames and frames[0].text:
            setattr(meta, field_name, str(frames[0].text[0]))
    bpm_frames = tags.getall("TBPM")
    if bpm_frames and bpm_frames[0].text:
        try:
            meta.bpm = float(str(bpm_frames[0].text[0]))
        except ValueError:
            pass
    meta.comment = _id3_primary_comment(tags)
    meta.rating = _id3_txxx(tags, "rating")
    meta.energy = _id3_txxx(tags, "energylevel")
    return meta


def _write_id3(tags: ID3, fields: dict[str, object]) -> None:
    for field_name, value in fields.items():
        if field_name in _ID3_TEXT_FRAMES:
            frame_cls, frame_id = _ID3_TEXT_FRAMES[field_name]
            tags.setall(frame_id, [frame_cls(encoding=3, text=[str(value)])] if value is not None else [])
        elif field_name == "bpm":
            tags.setall("TBPM", [TBPM(encoding=3, text=[str(round(value))])] if value is not None else [])
        elif field_name == "comment":
            others = [f for f in tags.getall("COMM") if f.desc != ""]
            tags.setall("COMM", others + ([COMM(encoding=3, lang="eng", desc="", text=[str(value)])] if value is not None else []))
        elif field_name in ("rating", "energy"):
            desc = "rating" if field_name == "rating" else "EnergyLevel"
            others = [f for f in tags.getall("TXXX") if f.desc.lower() != desc.lower()]
            tags.setall("TXXX", others + ([TXXX(encoding=3, desc=desc, text=[str(value)])] if value is not None else []))


# --- Vorbis comments (FLAC, OGG) -----------------------------------------

_VORBIS_KEYS = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "genre": "genre",
    "bpm": "bpm",
    "key": "key",
    "comment": "comment",
    "rating": "rating",
    "energy": "energylevel",
}


def _read_vorbis(tags: object) -> TrackMetadata:
    meta = TrackMetadata()
    for field_name, key in _VORBIS_KEYS.items():
        values = tags.get(key)
        if field_name == "key" and not values:
            values = tags.get("initialkey")
        if values:
            setattr(meta, field_name, values[0])
    if meta.bpm is not None:
        try:
            meta.bpm = float(meta.bpm)
        except ValueError:
            meta.bpm = None
    return meta


def _write_vorbis(tags: object, fields: dict[str, object]) -> None:
    for field_name, value in fields.items():
        key = _VORBIS_KEYS[field_name]
        if value is None:
            if key in tags:
                del tags[key]
        else:
            tags[key] = [str(value)]


# --- MP4 atoms (M4A) ------------------------------------------------------

_MP4_ATOMS = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "genre": "\xa9gen",
    "comment": "\xa9cmt",
}
_MP4_FREEFORM = {
    "key": "----:com.apple.iTunes:initialkey",
    "rating": "----:com.apple.iTunes:RATING",
    "energy": "----:com.apple.iTunes:ENERGYLEVEL",
}


def _read_mp4(tags: object) -> TrackMetadata:
    meta = TrackMetadata()
    if tags is None:
        return meta
    for field_name, atom in _MP4_ATOMS.items():
        values = tags.get(atom)
        if values:
            setattr(meta, field_name, str(values[0]))
    tmpo = tags.get("tmpo")
    if tmpo:
        meta.bpm = float(tmpo[0])
    for field_name, atom in _MP4_FREEFORM.items():
        values = tags.get(atom)
        if values:
            setattr(meta, field_name, values[0].decode("utf-8", errors="replace"))
    return meta


def _write_mp4(tags: object, fields: dict[str, object]) -> None:
    for field_name, value in fields.items():
        if field_name in _MP4_ATOMS:
            atom = _MP4_ATOMS[field_name]
            if value is None:
                tags.pop(atom, None)
            else:
                tags[atom] = [str(value)]
        elif field_name == "bpm":
            if value is None:
                tags.pop("tmpo", None)
            else:
                tags["tmpo"] = [round(value)]
        elif field_name in _MP4_FREEFORM:
            atom = _MP4_FREEFORM[field_name]
            if value is None:
                tags.pop(atom, None)
            else:
                tags[atom] = [str(value).encode("utf-8")]


# --- noise cleanup ---------------------------------------------------------

_ID3_NOISE_COMM_DESCS = frozenset({"id3v1 comment", "songs-db_preference", "musicmatch_preference"})
# Shared between ID3 TXXX descriptions and Vorbis comment keys -- both
# ecosystems use the same "replaygain_*"/"LABELNO" naming in practice.
_NOISE_KEY_PREFIXES = ("replaygain_",)
_NOISE_KEYS = frozenset({"labelno"})


def _is_protected_id3_frame(frame: object) -> bool:
    frame_id = getattr(frame, "FrameID", "")
    if frame_id == "GEOB":
        return frame.desc.startswith(_PROTECTED_GEOB_PREFIX)
    if frame_id == "PRIV":
        return frame.owner == _PROTECTED_PRIV_OWNER
    if frame_id == "TXXX":
        return frame.desc.lower() in _PROTECTED_TXXX_DESCS
    if frame_id == "COMM":
        return frame.desc == ""
    return False


def _is_noise_id3_frame(frame: object) -> bool:
    if _is_protected_id3_frame(frame):
        return False
    frame_id = getattr(frame, "FrameID", "")
    if frame_id == "COMM":
        return frame.desc.lower() in _ID3_NOISE_COMM_DESCS
    if frame_id == "PRIV":
        return frame.owner.startswith("WM/")
    if frame_id == "TXXX":
        desc = frame.desc.lower()
        return desc.startswith(_NOISE_KEY_PREFIXES) or desc in _NOISE_KEYS
    return False


def _clean_noise_id3(tags: ID3) -> list[str]:
    removed = []
    for key, frame in list(tags.items()):
        if _is_noise_id3_frame(frame):
            removed.append(key)
            del tags[key]
    return removed


def _is_protected_vorbis_key(key: str) -> bool:
    return key.lower().startswith(_PROTECTED_VORBIS_PREFIX)


def _is_noise_vorbis_key(key: str) -> bool:
    lowered = key.lower()
    if _is_protected_vorbis_key(lowered):
        return False
    return lowered.startswith(_NOISE_KEY_PREFIXES) or lowered in _NOISE_KEYS


def _clean_noise_vorbis(tags: object) -> list[str]:
    removed = [key for key in list(tags.keys()) if _is_noise_vorbis_key(key)]
    for key in removed:
        del tags[key]
    return removed


def clean_noise_frames(path: str | Path, dry_run: bool = True) -> list[str]:
    """Report (and, if `dry_run` is False, remove) confirmed-noise tag frames.

    Never touches Serato GEOB/`serato_*` blobs, PRIV:TRAKTOR4, or the
    managed fields in `MANAGED_FIELDS` -- only the specific noise patterns
    identified against the maintainer's real files in issue #126.
    """
    audio = mutagen.File(path)
    if audio is None or audio.tags is None:
        return []
    if isinstance(audio.tags, ID3):
        if dry_run:
            return [key for key, frame in audio.tags.items() if _is_noise_id3_frame(frame)]
        removed = _clean_noise_id3(audio.tags)
        if removed:
            audio.save()
        return removed
    if _looks_like_vorbis(audio.tags):
        if dry_run:
            return [key for key in audio.tags if _is_noise_vorbis_key(key)]
        removed = _clean_noise_vorbis(audio.tags)
        if removed:
            audio.save()
        return removed
    return []
