"""Embedded cover art: read, set and remove the front cover (issue #256).

Same surgical discipline as `metadata.py`: a write only ever touches the
*front cover* picture of a file -- ID3 ``APIC`` frames of picture type 3
(MP3, AIFF), FLAC picture blocks of type 3, Vorbis
``metadata_block_picture`` entries of type 3 (OGG), or the first MP4
``covr`` image (M4A, whose atom has no picture type; the first image is the
one every player shows). Other pictures (back cover, artist photo...),
every other tag and the protected Serato/Traktor frames are left exactly as
they were.

Two readers on purpose:

- `read_cover_art` is what a viewer shows: the front cover, else the first
  embedded picture of any type (and, for OGG, the legacy ``coverart`` key);
- `read_front_cover` returns only the picture `write_cover_art` manages, so
  an undo can restore exactly the slot a write replaced -- restoring a
  fallback picture into the front slot would leave a duplicate behind.

Only JPEG and PNG are accepted for writing, recognized from their magic
bytes rather than the file extension.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3
from mutagen.mp4 import MP4, MP4Cover

FRONT_COVER = 3  # ID3v2 / FLAC picture type "Cover (front)"
MAX_COVER_BYTES = 16 * 1024 * 1024

_JPEG = "image/jpeg"
_PNG = "image/png"
_VORBIS_PICTURE_KEY = "metadata_block_picture"
_VORBIS_LEGACY_KEY = "coverart"
_VORBIS_LEGACY_MIME_KEY = "coverartmime"


@dataclass(frozen=True)
class CoverArt:
    data: bytes
    mime: str
    description: str = ""


def image_mime(data: bytes) -> str | None:
    """``image/jpeg`` or ``image/png`` from the magic bytes, else None."""
    if data.startswith(b"\xff\xd8\xff"):
        return _JPEG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _PNG
    return None


def load_cover_file(path: str | Path) -> CoverArt:
    """Read an image file to embed. Raises ValueError for anything that is
    not a JPEG/PNG or is larger than `MAX_COVER_BYTES`."""
    path = Path(path)
    if path.stat().st_size > MAX_COVER_BYTES:
        raise ValueError(f"{path.name} is larger than {MAX_COVER_BYTES // (1024 * 1024)} MB")
    data = path.read_bytes()
    mime = image_mime(data)
    if mime is None:
        raise ValueError(f"{path.name} is not a JPEG or PNG image")
    return CoverArt(data, mime)


# --- reading ---------------------------------------------------------------


def read_cover_art(path: str | Path) -> CoverArt | None:
    """The picture to display: the front cover, else any embedded picture."""
    audio = mutagen.File(path)
    return None if audio is None else cover_from_audio(audio)


def read_front_cover(path: str | Path) -> CoverArt | None:
    """Only the front-cover slot `write_cover_art` manages."""
    audio = mutagen.File(path)
    return None if audio is None else cover_from_audio(audio, front_only=True)


def cover_from_audio(audio: mutagen.FileType, front_only: bool = False) -> CoverArt | None:
    if isinstance(audio, FLAC):
        return _pick_picture(audio.pictures, front_only)
    tags = audio.tags
    if tags is None:
        return None
    if isinstance(tags, ID3):
        frames = tags.getall("APIC")
        front = [frame for frame in frames if frame.type == FRONT_COVER]
        chosen = front[0] if front else (None if front_only or not frames else frames[0])
        return None if chosen is None else CoverArt(bytes(chosen.data), chosen.mime or _sniff(chosen.data), chosen.desc)
    if isinstance(audio, MP4):
        covers = tags.get("covr") or []
        if not covers:
            return None
        cover = covers[0]
        mime = _PNG if cover.imageformat == MP4Cover.FORMAT_PNG else _JPEG
        return CoverArt(bytes(cover), mime)
    if hasattr(tags, "get"):  # Vorbis comments (OGG)
        picture = _pick_picture(_vorbis_pictures(tags), front_only)
        if picture is not None or front_only:
            return picture
        return _vorbis_legacy_cover(tags)
    return None


def _sniff(data: bytes) -> str:
    return image_mime(data) or _JPEG


def _pick_picture(pictures: list[Picture], front_only: bool) -> CoverArt | None:
    front = [picture for picture in pictures if picture.type == FRONT_COVER]
    chosen = front[0] if front else (None if front_only or not pictures else pictures[0])
    if chosen is None:
        return None
    return CoverArt(bytes(chosen.data), chosen.mime or _sniff(chosen.data), chosen.desc)


def _vorbis_pictures(tags: object) -> list[Picture]:
    pictures = []
    for value in tags.get(_VORBIS_PICTURE_KEY) or []:
        try:
            pictures.append(Picture(base64.b64decode(value)))
        except (binascii.Error, ValueError, mutagen.MutagenError):
            continue  # a corrupt entry is skipped, never rewritten
    return pictures


def _vorbis_legacy_cover(tags: object) -> CoverArt | None:
    values = tags.get(_VORBIS_LEGACY_KEY) or []
    if not values:
        return None
    try:
        data = base64.b64decode(values[0])
    except (binascii.Error, ValueError):
        return None
    mimes = tags.get(_VORBIS_LEGACY_MIME_KEY) or []
    return CoverArt(data, mimes[0] if mimes else _sniff(data))


# --- writing ---------------------------------------------------------------


def write_cover_art(path: str | Path, cover: CoverArt | None) -> None:
    """Replace the front cover with `cover`, or remove it when None.

    Nothing else in the file changes: other pictures, every text tag and the
    Serato/Traktor frames are kept verbatim."""
    if cover is not None:
        if image_mime(cover.data) is None:
            raise ValueError("cover art must be a JPEG or PNG image")
        if len(cover.data) > MAX_COVER_BYTES:
            raise ValueError("cover art image is too large")
    audio = mutagen.File(path)
    if audio is None:
        raise ValueError(f"unrecognized or unreadable audio file: {path}")
    if isinstance(audio, FLAC):
        _write_flac(audio, cover)
    else:
        if audio.tags is None:
            if cover is None:
                return  # nothing to remove
            audio.add_tags()
        if isinstance(audio.tags, ID3):
            _write_id3(audio.tags, cover)
        elif isinstance(audio, MP4):
            _write_mp4(audio.tags, cover)
        elif hasattr(audio.tags, "get") and hasattr(audio.tags, "keys"):
            _write_vorbis(audio.tags, cover)
        else:
            raise ValueError(f"unsupported tag format for {path}: {type(audio.tags)!r}")
    audio.save()


def _new_picture(cover: CoverArt) -> Picture:
    picture = Picture()
    picture.type = FRONT_COVER
    picture.mime = cover.mime
    picture.desc = cover.description
    picture.data = cover.data
    return picture


def _write_id3(tags: ID3, cover: CoverArt | None) -> None:
    kept = [frame for frame in tags.getall("APIC") if frame.type != FRONT_COVER]
    new = []
    if cover is not None:
        # APIC frames are keyed by description: never collide with a kept one.
        taken = {frame.desc for frame in kept}
        desc = cover.description
        while desc in taken:
            desc = (desc + " (front)").strip()
        new = [APIC(encoding=3, mime=cover.mime, type=FRONT_COVER, desc=desc, data=cover.data)]
    tags.setall("APIC", kept + new)


def _write_flac(audio: FLAC, cover: CoverArt | None) -> None:
    kept = [picture for picture in audio.pictures if picture.type != FRONT_COVER]
    audio.clear_pictures()
    for picture in kept:
        audio.add_picture(picture)
    if cover is not None:
        audio.add_picture(_new_picture(cover))


def _write_vorbis(tags: object, cover: CoverArt | None) -> None:
    kept = []
    for value in tags.get(_VORBIS_PICTURE_KEY) or []:
        try:
            if Picture(base64.b64decode(value)).type == FRONT_COVER:
                continue
        except (binascii.Error, ValueError, mutagen.MutagenError):
            pass  # unreadable entry: keep it verbatim rather than guess
        kept.append(value)
    if cover is not None:
        kept.append(base64.b64encode(_new_picture(cover).write()).decode("ascii"))
    if kept:
        tags[_VORBIS_PICTURE_KEY] = kept
    elif _VORBIS_PICTURE_KEY in tags:
        del tags[_VORBIS_PICTURE_KEY]


def _write_mp4(tags: object, cover: CoverArt | None) -> None:
    rest = list(tags.get("covr") or [])[1:]
    if cover is not None:
        image_format = MP4Cover.FORMAT_PNG if cover.mime == _PNG else MP4Cover.FORMAT_JPEG
        rest.insert(0, MP4Cover(cover.data, imageformat=image_format))
    if rest:
        tags["covr"] = rest
    else:
        tags.pop("covr", None)
