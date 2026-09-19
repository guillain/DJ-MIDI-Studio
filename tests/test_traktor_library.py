from djmidi.library.traktor_library import NmlTrack, parse_collection, parse_playlists

# A small, hand-written fixture matching the real shape confirmed against the
# maintainer's own collection.nml (Traktor Pro 4, NML VERSION="20") -- never
# a copy of the real 51.7MB/44,564-entry file itself.
_SAMPLE_NML = """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20"><HEAD COMPANY="www.native-instruments.com" PROGRAM="Traktor Pro 4"></HEAD>
<COLLECTION ENTRIES="3">
<ENTRY MODIFIED_DATE="2025/12/6" MODIFIED_TIME="63527" TITLE="Bumpy" ARTIST="Bumpin Flava"><LOCATION DIR="/:Library/:Factory Sounds/:" FILE="Bumpin Flava - Bumpy.mp3" VOLUME="Macintosh HD" VOLUMEID="Macintosh HD"></LOCATION>
<ALBUM TITLE="Maschine Expansion"></ALBUM>
<MODIFICATION_INFO AUTHOR_TYPE="user"></MODIFICATION_INFO>
<INFO BITRATE="299000" LABEL="Native Instruments" KEY="7m" PLAYTIME="142" PLAYTIME_FLOAT="141.348572" IMPORT_DATE="2024/6/18" FLAGS="28" FILESIZE="5244"></INFO>
<TEMPO BPM="136.000000" BPM_QUALITY="100.000000"></TEMPO>
<LOUDNESS PEAK_DB="0.698550" PERCEIVED_DB="-0.143524" ANALYZED_DB="-0.143524"></LOUDNESS>
<MUSICAL_KEY VALUE="15"></MUSICAL_KEY>
<CUE_V2 NAME="AutoGrid" DISPL_ORDER="0" TYPE="4" START="1836.328431" LEN="0.000000" REPEATS="-1" HOTCUE="-1"><GRID BPM="136.000000"></GRID>
</CUE_V2>
</ENTRY>
<ENTRY MODIFIED_DATE="2025/12/6" MODIFIED_TIME="63528" TITLE="Au Ké de la Core" ARTIST="Various"><LOCATION DIR="/:Users/:guillain/:Music/:Tek/:Hard_Tek/:" FILE="Au Ké de la Core.mp3" VOLUME="Macintosh HD" VOLUMEID="Macintosh HD"></LOCATION>
<MODIFICATION_INFO AUTHOR_TYPE="user"></MODIFICATION_INFO>
<INFO BITRATE="320000" IMPORT_DATE="2024/6/18" FLAGS="28" FILESIZE="4000"></INFO>
<TEMPO BPM="180.000000" BPM_QUALITY="100.000000"></TEMPO>
<MUSICAL_KEY VALUE="3"></MUSICAL_KEY>
</ENTRY>
<ENTRY MODIFIED_DATE="2025/12/6" MODIFIED_TIME="63529" TITLE="No Metadata Track" ARTIST=""><LOCATION DIR="/:Users/:guillain/:Music/:Misc/:" FILE="no-metadata.mp3" VOLUME="Macintosh HD" VOLUMEID="Macintosh HD"></LOCATION>
<MODIFICATION_INFO AUTHOR_TYPE="user"></MODIFICATION_INFO>
</ENTRY>
</COLLECTION>
<SETS ENTRIES="0"></SETS>
<PLAYLISTS><NODE TYPE="FOLDER" NAME="$ROOT"><SUBNODES COUNT="2">
<NODE TYPE="SMARTLIST" NAME="Recently added"><SMARTLIST UUID="d6356fb44d4248f0b92615ad204f8326"><SEARCH_EXPRESSION VERSION="1" QUERY="$IMPORTDATE >= MONTHS_AGO(1)"></SEARCH_EXPRESSION>
</SMARTLIST>
</NODE>
<NODE TYPE="PLAYLIST" NAME="Hard_Tek"><PLAYLIST ENTRIES="2" TYPE="LIST" UUID="f5decd32610241bfa78b691bfea2021a"><ENTRY><PRIMARYKEY TYPE="TRACK" KEY="Macintosh HD/:Library/:Factory Sounds/:Bumpin Flava - Bumpy.mp3"></PRIMARYKEY>
</ENTRY>
<ENTRY><PRIMARYKEY TYPE="TRACK" KEY="Macintosh HD/:Users/:guillain/:Music/:Tek/:Hard_Tek/:Au Ké de la Core.mp3"></PRIMARYKEY>
</ENTRY>
</PLAYLIST>
</NODE>
</SUBNODES>
</NODE>
</PLAYLISTS>
<INDEXING><SORTING_INFO PATH="$COLLECTION"></SORTING_INFO>
</INDEXING>
</NML>
"""


def _write_fixture(tmp_path):
    path = tmp_path / "collection.nml"
    path.write_text(_SAMPLE_NML, encoding="utf-8")
    return path


def test_parse_collection_reads_all_entries(tmp_path):
    tracks = parse_collection(_write_fixture(tmp_path))

    assert len(tracks) == 3
    assert all(isinstance(t, NmlTrack) for t in tracks)


def test_parse_collection_reads_full_track_fields(tmp_path):
    tracks = parse_collection(_write_fixture(tmp_path))
    bumpy = tracks[0]

    assert bumpy.title == "Bumpy"
    assert bumpy.artist == "Bumpin Flava"
    assert bumpy.bpm == 136.0
    assert bumpy.musical_key == "7m"
    assert bumpy.musical_key_value == 15
    assert bumpy.album == "Maschine Expansion"
    assert bumpy.volume == "Macintosh HD"
    assert bumpy.location == "/Library/Factory Sounds/Bumpin Flava - Bumpy.mp3"
    assert bumpy.key == "Macintosh HD/:Library/:Factory Sounds/:Bumpin Flava - Bumpy.mp3"


def test_parse_collection_tolerates_missing_optional_elements(tmp_path):
    tracks = parse_collection(_write_fixture(tmp_path))
    bare = tracks[2]

    assert bare.title == "No Metadata Track"
    assert bare.bpm is None
    assert bare.musical_key is None
    assert bare.musical_key_value is None
    assert bare.album is None
    assert bare.location == "/Users/guillain/Music/Misc/no-metadata.mp3"


def test_parse_playlists_returns_named_track_key_lists(tmp_path):
    playlists = parse_playlists(_write_fixture(tmp_path))

    assert set(playlists) == {"Hard_Tek"}
    assert playlists["Hard_Tek"] == [
        "Macintosh HD/:Library/:Factory Sounds/:Bumpin Flava - Bumpy.mp3",
        "Macintosh HD/:Users/:guillain/:Music/:Tek/:Hard_Tek/:Au Ké de la Core.mp3",
    ]


def test_parse_playlists_skips_smartlists(tmp_path):
    playlists = parse_playlists(_write_fixture(tmp_path))

    assert "Recently added" not in playlists


def test_playlist_track_keys_join_against_collection_track_keys(tmp_path):
    fixture = _write_fixture(tmp_path)
    tracks_by_key = {t.key: t for t in parse_collection(fixture)}
    playlists = parse_playlists(fixture)

    resolved = [tracks_by_key[key].title for key in playlists["Hard_Tek"]]

    assert resolved == ["Bumpy", "Au Ké de la Core"]
