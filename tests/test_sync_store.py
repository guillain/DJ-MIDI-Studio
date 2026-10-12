"""Controller sync sets stored as one visible file per controller (issue #175)."""

import json

from djmidi import sync_store
from djmidi.controller_sync import DEFAULT_SCENE, ControllerSyncSet, SyncMessage


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


# --- Scenes (issue #188) ----------------------------------------------------


def test_each_scene_gets_its_own_readable_file(tmp_path):
    sets = [_set("DDJ-XP2"), _set("DDJ-XP2", 2).in_scene("Tek"), _set("DDJ-XP2", 3).in_scene("Warm up!")]
    sync_store.save_sync_sets(tmp_path, sets)
    assert sorted(p.name for p in tmp_path.glob("*.json")) == [
        "ddj-xp2.json",
        "ddj-xp2.tek.json",
        "ddj-xp2.warm-up.json",
    ]
    assert sorted(sync_store.load_sync_sets(tmp_path), key=lambda s: s.scene) == sorted(sets, key=lambda s: s.scene)


def test_a_file_written_before_scenes_loads_as_the_default_scene(tmp_path):
    (tmp_path / "ddj-xp2.json").write_text(
        json.dumps(
            {
                "controller": "DDJ-XP2",
                "output_port": "Port",
                "messages": [{"event_type": "Note On", "channel": 1, "data1": 1, "data2": 127}],
            }
        )
    )
    [loaded] = sync_store.load_sync_sets(tmp_path)
    assert loaded == _set("DDJ-XP2")
    assert loaded.scene == DEFAULT_SCENE
    # Saving it back keeps the same file name, now with an explicit scene.
    sync_store.save_sync_sets(tmp_path, [loaded])
    assert [p.name for p in tmp_path.glob("*.json")] == ["ddj-xp2.json"]
    assert json.loads((tmp_path / "ddj-xp2.json").read_text())["scene"] == DEFAULT_SCENE


def test_sets_whose_names_slug_alike_never_overwrite_each_other(tmp_path):
    sets = [_set("DDJ XP2"), _set("DDJ-XP2", 2), _set("A", 3).in_scene("Tek"), _set("A", 4).in_scene("TEK")]
    sync_store.save_sync_sets(tmp_path, sets)
    assert sorted(p.name for p in tmp_path.glob("*.json")) == ["a.tek-2.json", "a.tek.json", "ddj-xp2-2.json", "ddj-xp2.json"]
    assert {s.key for s in sync_store.load_sync_sets(tmp_path)} == {s.key for s in sets}


def test_scene_sets_migrate_from_preferences_into_the_folder(tmp_path):
    from_preferences = [_set("A"), _set("A", 2).in_scene("DnB")]
    assert sync_store.adopt_sync_sets(tmp_path, from_preferences) == from_preferences
    assert sorted(p.name for p in tmp_path.glob("*.json")) == ["a.dnb.json", "a.json"]
