from __future__ import annotations

import struct

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import COMM, GEOB, ID3, PRIV, TXXX
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.ogg import OggPage
from mutagen.oggvorbis import OggVorbis

from djmidi.library import (
    MANAGED_FIELDS,
    clean_noise_frames,
    read_metadata,
    write_metadata,
)


def _mp3_frame() -> bytes:
    header = bytes([0xFF, 0xFB, 0x90, 0xC4])
    return header + b"\x00" * (417 - len(header))


def _make_mp3(path) -> None:
    frame = _mp3_frame()
    path.write_bytes(frame * 20)


def _atom(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), name) + payload


def _make_m4a(path) -> None:
    ilst = _atom(b"ilst", b"")
    meta = _atom(b"meta", b"\x00\x00\x00\x00" + ilst)
    udta = _atom(b"udta", meta)
    moov = _atom(b"moov", udta)
    ftyp = _atom(b"ftyp", b"isom" + b"\x00\x00\x02\x00" + b"isomiso2mp41")
    mdat = _atom(b"mdat", b"\x00" * 16)
    path.write_bytes(ftyp + moov + mdat)


def _make_flac(path) -> None:
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
    assert len(bits) == 144
    streaminfo = int(bits, 2).to_bytes(18, "big") + b"\x00" * 16
    header = bytes([0x80]) + len(streaminfo).to_bytes(3, "big")
    path.write_bytes(b"fLaC" + header + streaminfo + b"\x00" * 32)


def _ogg_id_packet() -> bytes:
    return (
        b"\x01vorbis"
        + struct.pack("<I", 0)
        + struct.pack("<B", 2)
        + struct.pack("<I", 44100)
        + struct.pack("<i", 0)
        + struct.pack("<i", 0)
        + struct.pack("<i", 0)
        + bytes([0xB8])
        + b"\x01"
    )


def _ogg_comment_packet() -> bytes:
    vendor = b"djmidi-test"
    return b"\x03vorbis" + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0) + b"\x01"


def _make_ogg(path) -> None:
    serial = 424242
    p0 = OggPage()
    p0.serial = serial
    p0.sequence = 0
    p0.first = True
    p0.packets = [_ogg_id_packet()]

    p1 = OggPage()
    p1.serial = serial
    p1.sequence = 1
    p1.packets = [_ogg_comment_packet()]

    p2 = OggPage()
    p2.serial = serial
    p2.sequence = 2
    p2.last = True
    p2.packets = [b"\x05vorbis" + b"\x00" * 8, b"\x00" * 32]

    path.write_bytes(p0.write() + p1.write() + p2.write())


def test_read_metadata_returns_none_for_unrecognized_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")

    assert read_metadata(path) is None


def test_read_metadata_returns_empty_metadata_for_untagged_mp3(tmp_path):
    path = tmp_path / "a.mp3"
    _make_mp3(path)

    meta = read_metadata(path)

    assert meta is not None
    assert meta.title is None
    assert meta.bpm is None


def test_write_and_read_roundtrip_mp3(tmp_path):
    path = tmp_path / "a.mp3"
    _make_mp3(path)

    write_metadata(
        path,
        title="Track Title",
        artist="Some Artist",
        album="Some Album",
        genre="Tech House",
        bpm=128.0,
        key="8A",
        comment="Yeahhh JiM",
        rating="5",
        energy="7",
    )

    meta = read_metadata(path)
    assert meta.title == "Track Title"
    assert meta.artist == "Some Artist"
    assert meta.album == "Some Album"
    assert meta.genre == "Tech House"
    assert meta.bpm == 128.0
    assert meta.key == "8A"
    assert meta.comment == "Yeahhh JiM"
    assert meta.rating == "5"
    assert meta.energy == "7"


def test_write_metadata_rejects_unknown_field(tmp_path):
    path = tmp_path / "a.mp3"
    _make_mp3(path)

    with pytest.raises(ValueError):
        write_metadata(path, bogus_field="x")


def test_write_mp3_preserves_serato_and_traktor_frames_byte_identical(tmp_path):
    path = tmp_path / "a.mp3"
    _make_mp3(path)

    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Overview", data=b"SERATO_OVERVIEW_BLOB"))
    audio.tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Markers2", data=b"SERATO_MARKERS2_BLOB"))
    audio.tags.add(PRIV(owner="TRAKTOR4", data=b"TRAKTOR_BINARY_BLOB"))
    audio.tags.add(TXXX(encoding=3, desc="EnergyLevel", text=["6"]))
    audio.tags.add(TXXX(encoding=3, desc="STYLE", text=["Deep Tech"]))
    audio.save()

    before = ID3(path)
    geob_before = {f.desc: f.data for f in before.getall("GEOB")}
    priv_before = {f.owner: f.data for f in before.getall("PRIV")}
    style_before = next(f for f in before.getall("TXXX") if f.desc == "STYLE").text[0]

    write_metadata(path, title="New Title", bpm=140.0, comment="a fresh comment")

    after = ID3(path)
    geob_after = {f.desc: f.data for f in after.getall("GEOB")}
    priv_after = {f.owner: f.data for f in after.getall("PRIV")}
    style_after = next(f for f in after.getall("TXXX") if f.desc == "STYLE").text[0]

    assert geob_after == geob_before
    assert priv_after == priv_before
    assert style_after == style_before
    assert after.getall("TIT2")[0].text[0] == "New Title"


def test_write_mp3_preserves_unrelated_comm_frames(tmp_path):
    path = tmp_path / "a.mp3"
    _make_mp3(path)

    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=["original personal note"]))
    audio.tags.add(COMM(encoding=3, lang="eng", desc="ID3v1 Comment", text=["original personal note"]))
    audio.tags.add(COMM(encoding=3, lang="eng", desc="Songs-DB_Preference", text=["junk"]))
    audio.save()

    write_metadata(path, comment="updated personal note")

    tags = ID3(path)
    comms = {f.desc: str(f.text[0]) for f in tags.getall("COMM")}
    assert comms[""] == "updated personal note"
    assert comms["ID3v1 Comment"] == "original personal note"
    assert comms["Songs-DB_Preference"] == "junk"


def test_clean_noise_frames_dry_run_does_not_modify_file(tmp_path):
    path = tmp_path / "a.mp3"
    _make_mp3(path)

    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(COMM(encoding=3, lang="eng", desc="ID3v1 Comment", text=["dup"]))
    audio.tags.add(COMM(encoding=3, lang="eng", desc="Songs-DB_Preference", text=["junk"]))
    audio.tags.add(PRIV(owner="WM/MediaClassPrimaryID", data=b"x"))
    audio.tags.add(TXXX(encoding=3, desc="replaygain_track_gain", text=["-6 dB"]))
    audio.tags.add(TXXX(encoding=3, desc="LABELNO", text=["123"]))
    audio.tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Overview", data=b"BLOB"))
    audio.tags.add(PRIV(owner="TRAKTOR4", data=b"BLOB2"))
    audio.save()

    found = clean_noise_frames(path, dry_run=True)

    assert set(found) == {
        "COMM:ID3v1 Comment:eng",
        "COMM:Songs-DB_Preference:eng",
        "PRIV:WM/MediaClassPrimaryID:x",
        "TXXX:replaygain_track_gain",
        "TXXX:LABELNO",
    }

    reloaded = ID3(path)
    assert reloaded.getall("GEOB")
    assert reloaded.getall("PRIV:TRAKTOR4")
    assert len(reloaded.getall("COMM")) == 2
    assert len(reloaded.getall("PRIV")) == 2


def test_clean_noise_frames_removes_only_confirmed_noise(tmp_path):
    path = tmp_path / "a.mp3"
    _make_mp3(path)

    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=["keep me"]))
    audio.tags.add(COMM(encoding=3, lang="eng", desc="ID3v1 Comment", text=["keep me"]))
    audio.tags.add(PRIV(owner="WM/MediaClassPrimaryID", data=b"x"))
    audio.tags.add(TXXX(encoding=3, desc="replaygain_track_gain", text=["-6 dB"]))
    audio.tags.add(TXXX(encoding=3, desc="EnergyLevel", text=["8"]))
    audio.tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Overview", data=b"BLOB"))
    audio.tags.add(PRIV(owner="TRAKTOR4", data=b"BLOB2"))
    audio.save()

    removed = clean_noise_frames(path, dry_run=False)

    assert set(removed) == {
        "COMM:ID3v1 Comment:eng",
        "PRIV:WM/MediaClassPrimaryID:x",
        "TXXX:replaygain_track_gain",
    }

    reloaded = ID3(path)
    assert len(reloaded.getall("COMM")) == 1
    assert reloaded.getall("COMM")[0].desc == ""
    assert reloaded.getall("GEOB")[0].data == b"BLOB"
    assert reloaded.getall("PRIV:TRAKTOR4")[0].data == b"BLOB2"
    assert reloaded.getall("TXXX:EnergyLevel")[0].text[0] == "8"


def test_write_and_read_roundtrip_flac(tmp_path):
    path = tmp_path / "a.flac"
    _make_flac(path)

    write_metadata(path, title="Flac Title", bpm=126.5, key="5A", comment="deep note")

    meta = read_metadata(path)
    assert meta.title == "Flac Title"
    assert meta.bpm == 126.5
    assert meta.key == "5A"
    assert meta.comment == "deep note"


def test_write_flac_preserves_serato_vorbis_comments_byte_identical(tmp_path):
    path = tmp_path / "a.flac"
    _make_flac(path)

    audio = FLAC(path)
    audio["serato_overview"] = ["base64serialisedoverviewdata"]
    audio["serato_markers_v2"] = ["base64serialisedmarkersdata"]
    audio["serato_autogain"] = ["1.0"]
    audio["serato_beatgrid"] = ["base64beatgriddata"]
    audio.save()

    before = FLAC(path)
    serato_before = {k: list(v) for k, v in before.items() if k.startswith("serato_")}

    write_metadata(path, title="New Flac Title", artist="New Artist")

    after = FLAC(path)
    serato_after = {k: list(v) for k, v in after.items() if k.startswith("serato_")}

    assert serato_after == serato_before
    assert after["title"] == ["New Flac Title"]


def test_clean_noise_frames_flac_removes_replaygain_keeps_serato(tmp_path):
    path = tmp_path / "a.flac"
    _make_flac(path)

    audio = FLAC(path)
    audio["serato_overview"] = ["blob"]
    audio["replaygain_track_gain"] = ["-6.0 dB"]
    audio["replaygain_track_peak"] = ["0.99"]
    audio["labelno"] = ["12345"]
    audio.save()

    removed = clean_noise_frames(path, dry_run=False)

    assert set(removed) == {"replaygain_track_gain", "replaygain_track_peak", "labelno"}
    reloaded = FLAC(path)
    assert reloaded["serato_overview"] == ["blob"]
    assert "replaygain_track_gain" not in reloaded


def test_write_and_read_roundtrip_m4a(tmp_path):
    path = tmp_path / "a.m4a"
    _make_m4a(path)

    write_metadata(path, title="M4A Title", artist="M4A Artist", bpm=120.0, comment="nice track")

    meta = read_metadata(path)
    assert meta.title == "M4A Title"
    assert meta.artist == "M4A Artist"
    assert meta.bpm == 120.0
    assert meta.comment == "nice track"


def test_m4a_write_preserves_unrelated_atoms(tmp_path):
    path = tmp_path / "a.m4a"
    _make_m4a(path)

    audio = MP4(path)
    audio.tags["\xa9alb"] = ["Existing Album"]
    audio.save()

    write_metadata(path, title="New Title")

    reloaded = MP4(path)
    assert reloaded.tags["\xa9alb"] == ["Existing Album"]
    assert reloaded.tags["\xa9nam"] == ["New Title"]


def test_write_and_read_roundtrip_ogg(tmp_path):
    path = tmp_path / "a.ogg"
    _make_ogg(path)

    write_metadata(path, title="Ogg Title", genre="Electro")

    meta = read_metadata(path)
    assert meta.title == "Ogg Title"
    assert meta.genre == "Electro"


def test_ogg_uses_same_vorbis_helpers_as_flac(tmp_path):
    path = tmp_path / "a.ogg"
    _make_ogg(path)

    audio = OggVorbis(path)
    audio["title"] = ["Preexisting"]
    audio.save()

    write_metadata(path, artist="Ogg Artist")

    reloaded = OggVorbis(path)
    assert reloaded["title"] == ["Preexisting"]
    assert reloaded["artist"] == ["Ogg Artist"]


def test_managed_fields_matches_track_metadata_dataclass():
    from djmidi.library.metadata import TrackMetadata

    assert MANAGED_FIELDS == set(TrackMetadata.__dataclass_fields__)
