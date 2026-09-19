from djmidi.library import LibraryDB


def test_add_root_is_idempotent():
    db = LibraryDB()
    first = db.add_root("/music/root")
    second = db.add_root("/music/root")
    assert first.id == second.id
    assert [r.path for r in db.list_roots()] == ["/music/root"]


def test_upsert_and_list_tracks():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=100, mtime=1.0)
    db.upsert_track(root.id, "/music/root/b.mp3", size=200, mtime=2.0)

    tracks = db.list_tracks(root_id=root.id)
    assert [t.path for t in tracks] == ["/music/root/a.mp3", "/music/root/b.mp3"]
    assert tracks[0].size == 100
    assert tracks[0].missing is False


def test_upsert_updates_existing_track():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=100, mtime=1.0)
    db.upsert_track(root.id, "/music/root/a.mp3", size=999, mtime=5.0)

    track = db.get_track_by_path("/music/root/a.mp3")
    assert track.size == 999
    assert track.mtime == 5.0


def test_mark_missing_except_flags_absent_tracks():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    db.upsert_track(root.id, "/music/root/b.mp3", size=1, mtime=1.0)

    flagged = db.mark_missing_except(root.id, seen_paths=["/music/root/a.mp3"])

    assert flagged == 1
    tracks = {t.path: t.missing for t in db.list_tracks(root_id=root.id)}
    assert tracks["/music/root/a.mp3"] is False
    assert tracks["/music/root/b.mp3"] is True


def test_upsert_clears_missing_flag_when_track_reappears():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    db.mark_missing_except(root.id, seen_paths=[])
    assert db.get_track_by_path("/music/root/a.mp3").missing is True

    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    assert db.get_track_by_path("/music/root/a.mp3").missing is False


def test_remove_root_cascades_to_tracks():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)

    db.remove_root(root.id)

    assert db.list_roots() == []
    assert db.list_tracks() == []


def test_list_tracks_can_exclude_missing():
    db = LibraryDB()
    root = db.add_root("/music/root")
    db.upsert_track(root.id, "/music/root/a.mp3", size=1, mtime=1.0)
    db.upsert_track(root.id, "/music/root/b.mp3", size=1, mtime=1.0)
    db.mark_missing_except(root.id, seen_paths=["/music/root/a.mp3"])

    present_only = db.list_tracks(root_id=root.id, include_missing=False)

    assert [t.path for t in present_only] == ["/music/root/a.mp3"]
