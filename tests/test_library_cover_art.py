from __future__ import annotations

import base64
import struct

import pytest
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, GEOB, ID3, PRIV, TIT2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.ogg import OggPage
from mutagen.oggvorbis import OggVorbis

from djmidi.library import cover_art
from djmidi.library.cover_art import (
    FRONT_COVER,
    CoverArt,
    image_mime,
    load_cover_file,
    read_cover_art,
    read_front_cover,
    write_cover_art,
)
from djmidi.library.metadata import read_metadata

JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
OTHER_JPEG = b"\xff\xd8\xff\xe1" + b"back-cover" * 4


def _mp3(path):
    header = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((header + b"\x00" * (417 - len(header))) * 20)
    return path


def _atom(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), name) + payload


def _m4a(path):
    ilst = _atom(b"ilst", b"")
    meta = _atom(b"meta", b"\x00\x00\x00\x00" + ilst)
    moov = _atom(b"moov", _atom(b"udta", meta))
    ftyp = _atom(b"ftyp", b"isom" + b"\x00\x00\x02\x00" + b"isomiso2mp41")
    path.write_bytes(ftyp + moov + _atom(b"mdat", b"\x00" * 16))
    return path


def _flac(path):
    bits = (
        format(4096, "016b")
        + format(4096, "016b")
        + format(0, "024b")
        + format(0, "024b")
        + format(44100, "020b")
        + format(1, "03b")
        + format(15, "05b")
        + format(0, "036b")
    )
    streaminfo = int(bits, 2).to_bytes(18, "big") + b"\x00" * 16
    path.write_bytes(b"fLaC" + bytes([0x80]) + len(streaminfo).to_bytes(3, "big") + streaminfo + b"\x00" * 32)
    return path


def _ogg(path):
    ident = (
        b"\x01vorbis"
        + struct.pack("<I", 0)
        + struct.pack("<B", 2)
        + struct.pack("<I", 44100)
        + struct.pack("<i", 0) * 3
        + bytes([0xB8])
        + b"\x01"
    )
    vendor = b"djmidi-test"
    comment = b"\x03vorbis" + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0) + b"\x01"
    pages = []
    for sequence, packets in enumerate([[ident], [comment], [b"\x05vorbis" + b"\x00" * 8, b"\x00" * 32]]):
        page = OggPage()
        page.serial = 424242
        page.sequence = sequence
        page.first = sequence == 0
        page.last = sequence == 2
        page.packets = packets
        pages.append(page.write())
    path.write_bytes(b"".join(pages))
    return path


_MAKERS = {"mp3": _mp3, "m4a": _m4a, "flac": _flac, "ogg": _ogg}


def _protected_id3(path) -> dict[str, bytes]:
    return {key: bytes(frame.data) for key, frame in ID3(path).items() if key[:4] in ("GEOB", "PRIV")}


def _picture(type_: int, data: bytes) -> Picture:
    picture = Picture()
    picture.type, picture.mime, picture.data = type_, "image/jpeg", data
    return picture


def test_image_mime_from_magic_bytes():
    assert image_mime(JPEG) == "image/jpeg"
    assert image_mime(PNG) == "image/png"
    assert image_mime(b"GIF89a....") is None


def test_load_cover_file_accepts_jpeg_and_png_only(tmp_path, monkeypatch):
    (tmp_path / "c.jpg").write_bytes(JPEG)
    (tmp_path / "c.png").write_bytes(PNG)
    (tmp_path / "c.gif").write_bytes(b"GIF89a" + b"\x00" * 10)
    assert load_cover_file(tmp_path / "c.jpg") == CoverArt(JPEG, "image/jpeg")
    assert load_cover_file(tmp_path / "c.png").mime == "image/png"
    with pytest.raises(ValueError, match="not a JPEG or PNG"):
        load_cover_file(tmp_path / "c.gif")
    monkeypatch.setattr(cover_art, "MAX_COVER_BYTES", 8)
    with pytest.raises(ValueError, match="larger than"):
        load_cover_file(tmp_path / "c.jpg")


@pytest.mark.parametrize("fmt", sorted(_MAKERS))
def test_set_replace_and_remove_front_cover(tmp_path, fmt):
    path = _MAKERS[fmt](tmp_path / f"t.{fmt}")
    assert read_cover_art(path) is None

    write_cover_art(path, CoverArt(JPEG, "image/jpeg"))
    cover = read_cover_art(path)
    assert cover.data == JPEG and cover.mime == "image/jpeg"
    assert read_front_cover(path) == cover

    write_cover_art(path, CoverArt(PNG, "image/png"))
    assert read_cover_art(path).data == PNG
    assert read_cover_art(path).mime == "image/png"

    write_cover_art(path, None)
    assert read_cover_art(path) is None


def test_write_rejects_non_image_and_unreadable_audio(tmp_path):
    path = _mp3(tmp_path / "a.mp3")
    with pytest.raises(ValueError, match="JPEG or PNG"):
        write_cover_art(path, CoverArt(b"not an image", "image/jpeg"))
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    with pytest.raises(ValueError, match="unreadable"):
        write_cover_art(text, CoverArt(JPEG, "image/jpeg"))
    assert read_cover_art(text) is None


def test_removing_from_an_untagged_file_is_a_noop(tmp_path):
    path = _mp3(tmp_path / "a.mp3")
    before = path.read_bytes()
    write_cover_art(path, None)
    assert path.read_bytes() == before


def test_mp3_write_preserves_serato_traktor_and_other_pictures_byte_identical(tmp_path):
    path = _mp3(tmp_path / "a.mp3")
    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["Alpha"]))
    audio.tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Overview", data=b"SERATO_OVERVIEW_BLOB"))
    audio.tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Markers2", data=b"SERATO_MARKERS2_BLOB"))
    audio.tags.add(PRIV(owner="TRAKTOR4", data=b"TRAKTOR_BINARY_BLOB"))
    audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=4, desc="back", data=OTHER_JPEG))
    audio.save()
    protected_before = _protected_id3(path)
    assert len(protected_before) == 3

    write_cover_art(path, CoverArt(JPEG, "image/jpeg"))

    assert _protected_id3(path) == protected_before
    assert {frame.type: bytes(frame.data) for frame in ID3(path).getall("APIC")} == {4: OTHER_JPEG, FRONT_COVER: JPEG}
    assert read_metadata(path).title == "Alpha"

    write_cover_art(path, None)
    assert _protected_id3(path) == protected_before
    assert [(frame.type, bytes(frame.data)) for frame in ID3(path).getall("APIC")] == [(4, OTHER_JPEG)]


def test_mp3_falls_back_to_a_non_front_picture_for_display_only(tmp_path):
    path = _mp3(tmp_path / "a.mp3")
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/jpeg", type=0, desc="", data=OTHER_JPEG))
    tags.save(path)
    assert read_cover_art(path).data == OTHER_JPEG
    assert read_front_cover(path) is None


def test_front_cover_description_never_collides_with_a_kept_picture(tmp_path):
    path = _mp3(tmp_path / "a.mp3")
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/jpeg", type=4, desc="", data=OTHER_JPEG))
    tags.save(path)
    write_cover_art(path, CoverArt(JPEG, "image/jpeg"))
    frames = ID3(path).getall("APIC")
    assert {frame.type: bytes(frame.data) for frame in frames} == {4: OTHER_JPEG, FRONT_COVER: JPEG}


def test_flac_write_preserves_serato_comments_and_other_pictures(tmp_path):
    path = _flac(tmp_path / "a.flac")
    audio = FLAC(path)
    audio["title"] = ["Alpha"]
    audio["serato_overview"] = ["c2VyYXRvLW92ZXJ2aWV3LWJsb2I="]
    audio["serato_markers_v2"] = ["c2VyYXRvLW1hcmtlcnMtYmxvYg=="]
    audio.add_picture(_picture(4, OTHER_JPEG))
    audio.save()
    serato_before = [(key, value) for key, value in FLAC(path).tags if key.startswith("serato_")]

    write_cover_art(path, CoverArt(PNG, "image/png"))

    after = FLAC(path)
    assert [(key, value) for key, value in after.tags if key.startswith("serato_")] == serato_before
    assert {picture.type: picture.data for picture in after.pictures} == {4: OTHER_JPEG, FRONT_COVER: PNG}
    assert after["title"] == ["Alpha"]


def test_ogg_keeps_other_pictures_and_reads_legacy_coverart(tmp_path):
    path = _ogg(tmp_path / "a.ogg")
    audio = OggVorbis(path)
    back_entry = base64.b64encode(_picture(4, OTHER_JPEG).write()).decode("ascii")
    audio["metadata_block_picture"] = [back_entry]
    audio["serato_overview"] = ["blob"]
    audio.save()

    write_cover_art(path, CoverArt(JPEG, "image/jpeg"))
    after = OggVorbis(path)
    assert after["metadata_block_picture"][0] == back_entry
    assert after["serato_overview"] == ["blob"]
    assert read_front_cover(path).data == JPEG

    write_cover_art(path, None)
    assert OggVorbis(path)["metadata_block_picture"] == [back_entry]

    legacy = _ogg(tmp_path / "legacy.ogg")
    audio = OggVorbis(legacy)
    audio["coverart"] = [base64.b64encode(PNG).decode("ascii")]
    audio.save()
    assert read_cover_art(legacy) == CoverArt(PNG, "image/png")
    assert read_front_cover(legacy) is None


def test_m4a_replaces_only_the_first_image(tmp_path):
    path = _m4a(tmp_path / "a.m4a")
    audio = MP4(path)
    audio["covr"] = [MP4Cover(OTHER_JPEG, MP4Cover.FORMAT_JPEG), MP4Cover(PNG, MP4Cover.FORMAT_PNG)]
    audio["\xa9nam"] = ["Alpha"]
    audio.save()
    write_cover_art(path, CoverArt(JPEG, "image/jpeg"))
    assert [bytes(cover) for cover in MP4(path)["covr"]] == [JPEG, PNG]
    write_cover_art(path, None)
    assert [bytes(cover) for cover in MP4(path)["covr"]] == [PNG]
    assert MP4(path)["\xa9nam"] == ["Alpha"]
