"""Controller sync sets stored as one visible file per controller (issue #175)."""

from djmidi import sync_store
from djmidi.controller_sync import ControllerSyncSet, SyncMessage


def _set(controller: str, note: int = 1) -> ControllerSyncSet:
    return ControllerSyncSet(controller, "Port", (SyncMessage.create("Note On", 1, note, 127),))


def test_saved_sets_load_back_one_file_per_controller(tmp_path):
    sync_store.save_sync_sets(tmp_path, [_set("DDJ-XP2"), _set("Behringer CMD LC-1", 5)])
    assert sorted(p.name for p in tmp_path.glob("*.json")) == ["behringer-cmd-lc-1.json", "ddj-xp2.json"]
    loaded = {s.controller: s for s in sync_store.load_sync_sets(tmp_path)}
    assert loaded["Behringer CMD LC-1"] == _set("Behringer CMD LC-1", 5)


def test_saving_removes_the_files_of_deleted_sets(tmp_path):
    sync_store.save_sync_sets(tmp_path, [_set("A"), _set("B")])
    sync_store.save_sync_sets(tmp_path, [_set("B")])
    assert [p.name for p in tmp_path.glob("*.json")] == ["b.json"]


def test_a_broken_file_is_skipped(tmp_path):
    sync_store.save_sync_sets(tmp_path, [_set("A")])
    (tmp_path / "broken.json").write_text("{not json")
    assert [s.controller for s in sync_store.load_sync_sets(tmp_path)] == ["A"]


def test_sets_still_in_preferences_move_into_the_folder_once(tmp_path):
    from_preferences = [_set("A")]
    assert sync_store.adopt_sync_sets(tmp_path, from_preferences) == from_preferences
    assert [p.name for p in tmp_path.glob("*.json")] == ["a.json"]
    # From then on the folder wins, even over stale preferences.
    assert sync_store.adopt_sync_sets(tmp_path, [_set("Stale")]) == [_set("A")]
