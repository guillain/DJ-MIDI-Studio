"""A playlist as rekordbox XML (issue #441), checked against the structure in
Pioneer's "XML file format for playlists sharing" list."""

from unittest.mock import patch
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

import pytest

from djmidi.library import workspace
from djmidi.library.rekordbox_xml import (
    FORMAT_VERSION,
    RekordboxXmlTrack,
    build_playlist_xml,
    location_uri,
    write_playlist_xml,
)


@pytest.mark.parametrize(
    ("path", "uri"),
    [
        ("/Users/dj/Music/A b & c.mp3", "file://localhost/Users/dj/Music/A%20b%20%26%20c.mp3"),
        ("/Users/dj/Music/Été #1.mp3", "file://localhost/Users/dj/Music/%C3%89t%C3%A9%20%231.mp3"),
        ("C:\\Music\\a b.mp3", "file://localhost/C:/Music/a%20b.mp3"),
    ],
)
def test_location_is_a_file_localhost_uri(path, uri):
    assert location_uri(path) == uri
    if not path.startswith("C:"):
        assert unquote(urlparse(uri).path) == path


def test_the_file_has_the_documented_shape():
    a = RekordboxXmlTrack("/m/a.mp3", "Alpha", "Zed", "LP", "Techno", 172.0, "Am", 301.6)
    b = RekordboxXmlTrack("/m/b.mp3", "Bravo")
    text = build_playlist_xml("Friday", [a, b, a], product_version="0.48.206")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')
    root = ET.fromstring(text)
    assert root.tag == "DJ_PLAYLISTS" and root.get("Version") == FORMAT_VERSION
    product = root.find("PRODUCT")
    assert product.get("Name") == "DJ MIDI Studio" and product.get("Version") == "0.48.206"
    collection = root.find("COLLECTION")
    tracks = collection.findall("TRACK")
    assert collection.get("Entries") == "2" and len(tracks) == 2  # a track listed twice is one entry
    first = tracks[0].attrib
    assert first == {
        "TrackID": "1",
        "Name": "Alpha",
        "Artist": "Zed",
        "Album": "LP",
        "Genre": "Techno",
        "Tonality": "Am",
        "AverageBpm": "172",
        "TotalTime": "302",
        "Location": "file://localhost/m/a.mp3",
    }
    assert tracks[1].attrib == {"TrackID": "2", "Name": "Bravo", "Location": "file://localhost/m/b.mp3"}
    folder = root.find("PLAYLISTS/NODE")
    assert folder.attrib == {"Type": "0", "Name": "ROOT", "Count": "1"}
    playlist = folder.find("NODE")
    assert playlist.attrib == {"Name": "Friday", "Type": "1", "KeyType": "0", "Entries": "3"}
    assert [t.get("Key") for t in playlist.findall("TRACK")] == ["1", "2", "1"]


def test_bpm_is_locale_independent_and_text_is_escaped():
    text = build_playlist_xml("A & B", [RekordboxXmlTrack("/m/x.mp3", 'Say "hi" <now>', bpm=128.25)])
    root = ET.fromstring(text)
    assert root.find("COLLECTION/TRACK").get("AverageBpm") == "128.25"
    assert root.find("COLLECTION/TRACK").get("Name") == 'Say "hi" <now>'
    assert root.find("PLAYLISTS/NODE/NODE").get("Name") == "A & B"


def test_write_goes_through_a_part_file(tmp_path):
    target = tmp_path / "out.xml"
    write_playlist_xml(target, "P", [RekordboxXmlTrack("/m/a.mp3")])
    assert target.exists() and not (tmp_path / "out.xml.part").exists()
    assert ET.parse(target).getroot().tag == "DJ_PLAYLISTS"


# --- from the Music Library ------------------------------------------------------


def test_export_from_a_library_playlist_uses_cached_tags(tmp_path, monkeypatch):
    from test_music_library_view import _mp3

    from djmidi.gui import music_library_view as mlv
    from djmidi.gui.music_library_view import MusicLibraryView

    music = tmp_path / "music"
    _mp3(music / "a.mp3", title="Alpha", artist="Zed", bpm="172", key="Am", genre="Techno")
    view = MusicLibraryView(db_path=":memory:")
    try:
        view.add_root(music)
        view.start_scan()
        view.run_pending_job()
        track = str(music / "a.mp3")
        view.create_playlist("Set", [track])
        view.playlist_list.setCurrentRow(0)
        out = tmp_path / "Set.xml"
        monkeypatch.setattr(mlv.QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
        view._on_export_rekordbox_clicked()
        entry = ET.parse(out).getroot().find("COLLECTION/TRACK").attrib
        assert entry["Name"] == "Alpha" and entry["Artist"] == "Zed" and entry["Tonality"] == "Am"
        assert float(entry["AverageBpm"]) == 172 and unquote(urlparse(entry["Location"]).path) == track
        assert "Set.xml" in view.status_label.text()
    finally:
        view.close_db()


def test_export_without_a_db_writes_locations_only(tmp_path):
    out = tmp_path / "x.xml"
    workspace.export_rekordbox_xml(out, "P", ["/m/a.mp3"])
    assert ET.parse(out).getroot().find("COLLECTION/TRACK").attrib == {
        "TrackID": "1",
        "Location": "file://localhost/m/a.mp3",
    }


def test_set_panel_exports_the_draft(tmp_path):
    from djmidi.gui.set_preparation import SetPreparationPanel

    panel = SetPreparationPanel(lambda: None, list, lambda: None, lambda _text: None)
    panel._paths = ["/m/a.mp3", "/m/b.mp3"]
    with patch.object(panel, "_db", lambda: None):
        panel.export_rekordbox_xml(str(tmp_path / "Set.xml"), "Set")
    playlist = ET.parse(tmp_path / "Set.xml").getroot().find("PLAYLISTS/NODE/NODE")
    assert playlist.get("Entries") == "2"
