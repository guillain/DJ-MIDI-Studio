"""Issue #458: suggest which copy of a duplicate group to keep, and why."""

from mutagen.id3 import GEOB, PRIV
from mutagen.mp3 import MP3

from djmidi.library.duplicates import TIER_EXACT, TIER_METADATA, DuplicateGroup
from djmidi.library.keep_copy import CopyFacts, read_copy_facts, suggest_keep


def _make_mp3(path) -> None:
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((frame + b"\x00" * (417 - len(frame))) * 20)


def test_quality_wins_then_dj_data_location_and_tags():
    low = CopyFacts("/dl/a.mp3", bitrate=192_000, filled_tags=6, in_roots=False)
    high = CopyFacts("/music/a.mp3", bitrate=320_000, filled_tags=2, in_roots=True)
    suggestion = suggest_keep([low, high])
    assert suggestion.keep == "/music/a.mp3"
    assert suggestion.reasons == ("higher bitrate (320 kbps vs 192 kbps)", "inside your library folders")
    flac = CopyFacts("/music/a.flac", lossless=True)
    assert suggest_keep([high, flac]).reasons[0] == "lossless"
    same = [CopyFacts("/x/1.mp3", bitrate=320_000), CopyFacts("/x/2.mp3", bitrate=320_000)]
    assert suggest_keep(same).keep == "/x/1.mp3"
    assert suggest_keep(same[:1]) is None


def test_a_dropped_copy_holding_dj_data_is_flagged():
    cued = CopyFacts("/music/a.mp3", bitrate=256_000, dj_data=("Serato",))
    better = CopyFacts("/music/b.mp3", bitrate=320_000)
    suggestion = suggest_keep([cued, better])
    assert suggestion.keep == "/music/b.mp3" and suggestion.losses == {"/music/a.mp3": ("Serato",)}


def test_facts_are_read_from_the_file_without_writing_it(tmp_path):
    path = tmp_path / "music" / "a.mp3"
    path.parent.mkdir()
    _make_mp3(path)
    audio = MP3(path)
    audio.add_tags()
    audio.tags.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Markers2", data=b"x"))
    audio.tags.add(PRIV(owner="TRAKTOR4", data=b"y"))
    audio.save()
    before = path.read_bytes()
    facts = read_copy_facts(str(path), roots=[str(tmp_path / "music")])
    assert facts.dj_data == ("Serato", "Traktor") and facts.in_roots and not facts.lossless
    assert not read_copy_facts(str(path), roots=[str(tmp_path / "elsewhere")]).in_roots
    assert path.read_bytes() == before
    assert read_copy_facts(str(tmp_path / "missing.mp3")).bitrate is None


def test_the_dialog_shows_the_suggestion_and_ticks_the_others():
    from djmidi.gui.duplicates_dialog import (
        PATH_ROLE,
        SUGGESTION_COLUMN,
        DuplicatesDialog,
    )

    facts = {
        "/dl/a.mp3": CopyFacts("/dl/a.mp3", bitrate=192_000),
        "/m/a.mp3": CopyFacts("/m/a.mp3", bitrate=320_000, in_roots=True),
        "/m/cued.mp3": CopyFacts("/m/cued.mp3", bitrate=128_000, dj_data=("Serato",)),
        "/m/b.mp3": CopyFacts("/m/b.mp3", bitrate=320_000),
        "/m/b2.mp3": CopyFacts("/m/b2.mp3", bitrate=320_000),
    }
    groups = [
        DuplicateGroup(TIER_EXACT, "abc", ("/dl/a.mp3", "/m/a.mp3", "/m/cued.mp3"), 10),
        DuplicateGroup(TIER_METADATA, "b", ("/m/b.mp3", "/m/b2.mp3"), label="B"),
    ]
    dialog = DuplicatesDialog(groups, facts_reader=lambda path, roots: facts[path])
    assert dialog.tick_all_but_suggested() == 2
    assert dialog.checked_paths() == ["/dl/a.mp3", "/m/b2.mp3"]  # the cued copy stays unticked
    texts = {item.data(0, PATH_ROLE): item.text(SUGGESTION_COLUMN) for item in dialog.file_items()}
    assert texts["/m/a.mp3"].startswith("★ Keep: higher bitrate")
    assert texts["/m/cued.mp3"] == "⚠ Holds Serato data the suggested copy lacks"
    assert dialog.trash_button.isEnabled()
    dialog.close()
