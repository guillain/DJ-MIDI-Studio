"""Reading the playlists of a rekordbox XML file (issue #446), read-only."""

from djmidi.library import workspace
from djmidi.library.rekordbox_xml import path_from_location, read_playlists

NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.0.0" Company="AlphaTheta"/>
  <COLLECTION Entries="3">
    <TRACK TrackID="10" Name="A" Location="file://localhost/m/A%20b.mp3">
      <TEMPO Inizio="0.025" Bpm="128.00" Metro="4/4" Battito="1"/>
      <POSITION_MARK Name="" Type="0" Start="1.0" Num="-1"/>
    </TRACK>
    <TRACK TrackID="11" Name="B" Location="file://localhost/C:/Music/b.mp3"/>
    <TRACK TrackID="12" Name="C" Location="file://localhost/m/%C3%A9t%C3%A9.mp3"/>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="3">
      <NODE Name="Friday" Type="1" KeyType="0" Entries="3">
        <TRACK Key="12"/><TRACK Key="99"/><TRACK Key="10"/>
      </NODE>
      <NODE Type="0" Name="Gigs" Count="1">
        <NODE Type="0" Name="2026" Count="1">
          <NODE Name="Club" Type="1" KeyType="1" Entries="1">
            <TRACK Key="file://localhost/C:/Music/b.mp3"/>
          </NODE>
        </NODE>
      </NODE>
      <NODE Name="Empty" Type="1" KeyType="0" Entries="0"/>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""


def _write(tmp_path):
    path = tmp_path / "rekordbox.xml"
    path.write_text(NESTED, encoding="utf-8")
    return path


def test_reading_resolves_ids_locations_and_folders(tmp_path):
    assert read_playlists(_write(tmp_path)) == {
        "Friday": ["/m/été.mp3", "/m/A b.mp3"],  # unknown TrackID 99 skipped
        "Gigs / 2026 / Club": ["C:/Music/b.mp3"],
        "Empty": [],
    }


def test_what_the_export_writes_reads_back(tmp_path):
    paths = ["/Users/dj/Music/A b & c.mp3", "/Users/dj/Music/Été #1.mp3", "/Users/dj/Music/A b & c.mp3"]
    out = tmp_path / "set.xml"
    workspace.export_rekordbox_xml(out, "Set", paths)
    assert read_playlists(out) == {"Set": paths}


def test_path_from_location_handles_both_uri_forms():
    assert path_from_location("file://localhost/m/a%20b.mp3") == "/m/a b.mp3"
    assert path_from_location("file:///m/a.mp3") == "/m/a.mp3"
    assert path_from_location("file://localhost/D:/x.mp3") == "D:/x.mp3"


def test_read_rekordbox_any_picks_the_reader_by_suffix(tmp_path, monkeypatch):
    assert "Friday" in workspace.read_rekordbox_any(_write(tmp_path))
    called = []
    monkeypatch.setattr(workspace, "read_rekordbox_playlists", lambda p: called.append(p) or {})
    workspace.read_rekordbox_any(tmp_path / "export.pdb")
    assert called


def test_library_imports_and_compares_a_rekordbox_xml(tmp_path, monkeypatch):
    from djmidi.gui import music_library_view as mlv
    from djmidi.gui.music_library_view import MusicLibraryView

    xml = _write(tmp_path)
    view = MusicLibraryView(db_path=":memory:")
    try:
        monkeypatch.setattr(mlv.QFileDialog, "getOpenFileName", lambda *a, **k: (str(xml), ""))
        view._on_import_rekordbox_clicked()
        names = [view.playlist_list.item(row).text() for row in range(view.playlist_list.count())]
        assert any(name.startswith("Gigs / 2026 / Club") for name in names)
        friday = next(row for row, name in enumerate(names) if name.startswith("Friday"))
        view.playlist_list.setCurrentRow(friday)
        shown = []
        monkeypatch.setattr(view, "compare_playlist", lambda pid, label, paths: shown.append((label, paths)))
        monkeypatch.setattr(mlv.QInputDialog, "getItem", lambda *a, **k: ("Friday", True))
        view._on_compare_rekordbox_clicked()
        assert shown == [("rekordbox “Friday”", ["/m/été.mp3", "/m/A b.mp3"])]
    finally:
        view.close_db()
