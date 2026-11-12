"""Issue #458: merge a duplicate group onto the kept copy -- tags field by
field, then this app's playlists and set draft. Nothing is discarded."""

from pathlib import Path

from mutagen.id3 import GEOB, ID3, TCON, TIT2, TKEY, TPE1

from djmidi.library import set_prep
from djmidi.library.db import LibraryDB
from djmidi.library.metadata import TrackMetadata, read_metadata
from djmidi.library.tag_merge import merge_changes, propose_tag_merge, repoint_to_kept


def test_empty_fields_take_the_most_common_value_and_filled_ones_stay():
    kept = TrackMetadata(title="Alpha", artist="Zed", genre=None)
    others = [
        TrackMetadata(title="Alpha (Original Mix)", artist="Zed", genre="House", key="Am"),
        TrackMetadata(title="Alpha", genre="Techno"),
        TrackMetadata(genre="Techno"),
        None,
    ]
    proposals = {proposal.field: proposal for proposal in propose_tag_merge(kept, others)}
    assert set(proposals) == {"title", "genre", "key"}  # artist agrees everywhere
    assert proposals["genre"].proposed == "Techno" and proposals["genre"].chosen
    assert proposals["genre"].alternatives == ("House", "Techno")
    assert not proposals["title"].chosen and proposals["title"].current == "Alpha"
    assert merge_changes("/k.mp3", proposals.values()) == {
        "/k.mp3": ({"genre": None, "key": None}, {"genre": "Techno", "key": "Am"})
    }
    picked = merge_changes("/k.mp3", proposals.values(), {"title": "Alpha (Original Mix)"})
    assert picked == {"/k.mp3": ({"title": "Alpha"}, {"title": "Alpha (Original Mix)"})}
    assert merge_changes("/k.mp3", proposals.values(), {}) == {}


def test_playlists_and_the_set_draft_list_the_kept_copy_once():
    db = LibraryDB(":memory:")
    friday = db.create_playlist("Friday", ["/dl/a.mp3", "/m/c.mp3", "/m/a.mp3"])
    saturday = db.create_playlist("Saturday", ["/m/c.mp3", "/old/a.mp3"])
    db.create_playlist("Untouched", ["/m/c.mp3"])
    set_prep.save_set_draft(db, set_prep.SetDraft(("/old/a.mp3", "/m/c.mp3")))
    pairs = [("/dl/a.mp3", "/m/a.mp3"), ("/old/a.mp3", "/m/a.mp3")]
    preview = repoint_to_kept(db, pairs, apply=False)
    assert preview.playlists == {"Friday": 1, "Saturday": 1} and preview.set_draft == 1
    assert db.playlist_paths(friday) == ["/dl/a.mp3", "/m/c.mp3", "/m/a.mp3"]  # a preview changes nothing
    repoint_to_kept(db, pairs)
    assert db.playlist_paths(friday) == ["/m/a.mp3", "/m/c.mp3"]
    assert db.playlist_paths(saturday) == ["/m/c.mp3", "/m/a.mp3"]
    assert set_prep.load_set_draft(db).paths == ("/m/a.mp3", "/m/c.mp3")


def _mp3(path: Path, **tags: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4])
    path.write_bytes((frame + b"\x00" * (417 - len(frame))) * 20)
    id3 = ID3()
    frames = {"title": TIT2, "artist": TPE1, "genre": TCON, "key": TKEY}
    for name, value in tags.items():
        id3.add(frames[name](encoding=3, text=[value]))
    id3.add(GEOB(encoding=0, mime="application/octet-stream", filename="", desc="Serato Markers2", data=b"CUES"))
    id3.save(path)
    return path


class _Accept:
    def __init__(self, choices=None, repoint=True):
        self._choices, self.repoint = choices, repoint

    def __call__(self, kept, dropped, proposals, preview, parent):
        self.proposals, self.preview = proposals, preview
        return self

    def exec(self):
        from PySide6.QtWidgets import QDialog

        return QDialog.DialogCode.Accepted

    def choices(self):
        return self._choices if self._choices is not None else {p.field: p.proposed for p in self.proposals if p.chosen}


def test_the_music_library_merges_tags_undoably_and_repoints(tmp_path):
    from djmidi.gui.music_library_view import MusicLibraryView

    kept = _mp3(tmp_path / "m" / "a.mp3", title="Alpha", artist="Zed")
    dropped = _mp3(tmp_path / "dl" / "a.mp3", title="Alpha", artist="Zed", genre="Techno", key="Am")
    view = MusicLibraryView(db_path=":memory:")
    playlist = view.db.create_playlist("Friday", [str(dropped)])
    factory = _Accept()
    assert view.merge_duplicates(str(kept), [str(dropped)], dialog_factory=factory)
    merged = read_metadata(kept)
    assert (merged.genre, merged.key) == ("Techno", "Am")
    assert ID3(kept).getall("GEOB")[0].data == b"CUES"  # Serato data untouched
    assert dropped.exists() and view.db.playlist_paths(playlist) == [str(kept)]
    assert "2 tag(s) written, 1 playlist entry(ies)" in view.status_label.text()
    view.undo_stack.undo()
    assert read_metadata(kept).genre is None
    view.close_db()


def test_the_duplicates_dialog_asks_to_merge_the_selected_group():
    from djmidi.gui.duplicates_dialog import PATH_ROLE, DuplicatesDialog
    from djmidi.library.duplicates import TIER_EXACT, DuplicateGroup
    from djmidi.library.keep_copy import CopyFacts

    facts = {"/a.mp3": CopyFacts("/a.mp3", bitrate=128_000), "/b.mp3": CopyFacts("/b.mp3", bitrate=320_000)}
    dialog = DuplicatesDialog(
        [DuplicateGroup(TIER_EXACT, "x", ("/a.mp3", "/b.mp3"), 1)], facts_reader=lambda path, roots: facts[path]
    )
    asked = []
    dialog.mergeRequested.connect(lambda kept, others: asked.append((kept, others)))
    assert not dialog.merge_button.isEnabled()
    group = dialog.tree.topLevelItem(0).child(0)
    dialog.tree.setCurrentItem(group)
    dialog.merge_button.click()  # the group: the suggested copy is kept
    file_a = next(item for item in dialog.file_items() if item.data(0, PATH_ROLE) == "/a.mp3")
    dialog.tree.setCurrentItem(file_a)
    dialog.merge_button.click()  # a file: that one is kept
    assert asked == [("/b.mp3", ["/a.mp3"]), ("/a.mp3", ["/b.mp3"])]
    dialog.close()


def test_the_merge_dialog_collects_the_ticked_values():
    from djmidi.gui.merge_copies_dialog import MergeCopiesDialog
    from djmidi.library.tag_merge import RepointPreview

    proposals = propose_tag_merge(TrackMetadata(title="A"), [TrackMetadata(title="B", genre="House")])
    dialog = MergeCopiesDialog("/k.mp3", ["/d.mp3"], proposals, RepointPreview({"Friday": 1}, 0))
    assert dialog.choices() == {"genre": "House"} and dialog.repoint
    dialog.field_checks["title"].setChecked(True)
    assert dialog.choices() == {"genre": "House", "title": "B"}
    empty = MergeCopiesDialog("/k.mp3", ["/d.mp3"], [], RepointPreview({}, 0))
    assert not empty.repoint and not empty.playlists_check.isEnabled()
    dialog.close()
    empty.close()
