from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from djmidi.library.db import LibraryDB
from djmidi.library.history import TrackPlays
from djmidi.library.metadata import TrackMetadata
from djmidi.library.smart_playlist import (
    SORT_BPM,
    SORT_MIX,
    SORT_PATH,
    SOURCE_SMART,
    SmartRules,
    create_smart_playlist,
    evaluate,
    last_played_map,
    load_rules,
    play_stats_rows,
    refresh_smart_playlists,
    update_smart_playlist,
)
from djmidi.library.workspace import LibraryRow

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _row(path, *, category=None, bpm=None, camelot=None, genre=None, title=None, missing=False, track_id=1):
    metadata = TrackMetadata(title=title, genre=genre, bpm=bpm)
    return LibraryRow(
        track_id=track_id,
        path=path,
        missing=missing,
        metadata=metadata,
        camelot_key=camelot,
        category=category,
    )


ROWS = [
    _row("/m/a.mp3", category="Tek%%HardTek", bpm=175, camelot="8A", genre="Hard Tek", title="Alpha"),
    _row("/m/b.mp3", category="Tek%%PsyTrance", bpm=172, camelot="9A", genre="Psy", title="Bravo"),
    _row("/m/c.mp3", category="Tek%%Tribe", bpm=165, camelot="8A", title="Charlie"),
    _row("/m/d.mp3", category="Electro%%Dub", bpm=176, camelot="8A", genre="Dub"),
    _row("/m/e.mp3", category="Tek%%HardTek", bpm=178, camelot="3B"),
    _row("/m/f.mp3", category="Tek%%HardTek", bpm=None, camelot="8A"),
    _row("/m/g.mp3", category="Tek%%HardTek", bpm=174, camelot="8B", missing=True),
]


def test_empty_rules_match_every_present_track():
    assert evaluate(SmartRules(sort=SORT_PATH), ROWS, now=NOW) == [
        "/m/a.mp3", "/m/b.mp3", "/m/c.mp3", "/m/d.mp3", "/m/e.mp3", "/m/f.mp3",
    ]


def test_issue_example_family_bpm_range_and_compatible_key():
    rules = SmartRules(category="Tek", bpm_min=170, bpm_max=180, camelot_key="8A", sort=SORT_PATH)
    # e: incompatible key; f: no BPM; d: other family; g: missing file.
    assert evaluate(rules, ROWS, now=NOW) == ["/m/a.mp3", "/m/b.mp3"]


def test_exact_key_and_single_category():
    rules = SmartRules(category="Tek%%HardTek", camelot_key="8A", key_compatible=False, sort=SORT_PATH)
    assert evaluate(rules, ROWS, now=NOW) == ["/m/a.mp3", "/m/f.mp3"]


def test_category_display_form_and_case_are_accepted():
    rules = SmartRules(category="tek / psytrance")
    assert evaluate(rules, ROWS, now=NOW) == ["/m/b.mp3"]


def test_uncategorized_track_never_matches_a_category_rule():
    rows = [_row("/m/x.mp3", category=None, bpm=170)]
    assert evaluate(SmartRules(category="Tek"), rows, now=NOW) == []


def test_key_rule_accepts_other_notations():
    rules = SmartRules(camelot_key="Am", key_compatible=False, sort=SORT_PATH)
    assert rules.normalized().camelot_key == "8A"
    assert evaluate(rules, ROWS, now=NOW) == ["/m/a.mp3", "/m/c.mp3", "/m/d.mp3", "/m/f.mp3"]


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError):
        SmartRules(camelot_key="H#").normalized()


def test_genre_and_text_are_case_insensitive_substrings():
    assert evaluate(SmartRules(genre="tek"), ROWS, now=NOW) == ["/m/a.mp3"]
    assert evaluate(SmartRules(text="CHAR"), ROWS, now=NOW) == ["/m/c.mp3"]
    assert evaluate(SmartRules(text="d.mp3"), ROWS, now=NOW) == ["/m/d.mp3"]


def test_reversed_bpm_range_is_swapped():
    rules = SmartRules(bpm_min=176, bpm_max=170, sort=SORT_PATH).normalized()
    assert (rules.bpm_min, rules.bpm_max) == (170, 176)


def test_not_played_rule_uses_last_played_times():
    last_played = {
        "/m/a.mp3": NOW - timedelta(days=10),  # recent
        "/m/b.mp3": NOW - timedelta(days=200),  # old enough
        "/m/c.mp3": None,  # played at an unknown time: can't prove it's old
    }
    rules = SmartRules(category="Tek", not_played_days=90, sort=SORT_PATH)
    assert evaluate(rules, ROWS, last_played, now=NOW) == ["/m/b.mp3", "/m/e.mp3", "/m/f.mp3"]


def test_sorts_and_limit():
    rules = SmartRules(category="Tek", bpm_min=1, sort=SORT_BPM)
    assert evaluate(rules, ROWS, now=NOW) == ["/m/c.mp3", "/m/b.mp3", "/m/a.mp3", "/m/e.mp3"]
    assert evaluate(SmartRules(category="Tek", bpm_min=1, sort=SORT_BPM, limit=2), ROWS, now=NOW) == [
        "/m/c.mp3", "/m/b.mp3",
    ]
    mixed = evaluate(SmartRules(category="Tek", sort=SORT_MIX), ROWS, now=NOW)
    assert sorted(mixed) == ["/m/a.mp3", "/m/b.mp3", "/m/c.mp3", "/m/e.mp3", "/m/f.mp3"]


def test_json_round_trip_and_tolerance():
    rules = SmartRules(category="Tek", bpm_min=170, bpm_max=180, camelot_key="8A", not_played_days=90, limit=50)
    assert SmartRules.from_json(rules.to_json()) == rules.normalized()
    assert SmartRules.from_json('{"category": "Tek", "future_rule": 1}').category == "Tek"
    for bad in ("not json", "[]", '{"sort": "random"}'):
        with pytest.raises(ValueError):
            SmartRules.from_json(bad)


def test_describe():
    text = SmartRules(category="Tek", bpm_min=170, bpm_max=180, camelot_key="8A", not_played_days=90).describe()
    assert text == "category Tek · BPM 170–180 · key compatible with 8A · not played for 90 days"
    assert SmartRules().describe() == "every track"


def test_play_stats_round_trip_through_db():
    last = datetime(2026, 7, 1, 21, 30, tzinfo=UTC)
    plays = {"/m/a.mp3": TrackPlays("/m/a.mp3", 3, last, last), "/m/b.mp3": TrackPlays("/m/b.mp3", 1, None, None)}
    with LibraryDB() as db:
        db.set_play_stats(play_stats_rows(plays))
        assert db.has_play_stats()
        assert last_played_map(db.play_stats()) == {"/m/a.mp3": last, "/m/b.mp3": None}
        db.set_play_stats([])
        assert not db.has_play_stats()


def _db_with_tracks() -> LibraryDB:
    db = LibraryDB()
    root = db.add_root("/m")
    for name, bpm, key in [("a", 175.0, "Am"), ("b", 120.0, "Am"), ("c", 178.0, "C#")]:
        db.upsert_track(root.id, f"/m/{name}.mp3", 1, 1.0)
        track = db.get_track_by_path(f"/m/{name}.mp3")
        db.set_cached_metadata(track.id, 1.0, TrackMetadata(title=name, bpm=bpm, key=key))
    db.commit()
    return db


def test_stored_smart_playlist_is_evaluated_updated_and_refreshed():
    with _db_with_tracks() as db:
        rules = SmartRules(bpm_min=170, bpm_max=180, camelot_key="8A", sort=SORT_PATH)
        playlist_id = create_smart_playlist(db, "Fast 8A", rules, now=NOW)
        record = next(p for p in db.list_playlists() if p.id == playlist_id)
        assert record.source == SOURCE_SMART
        assert db.playlist_paths(playlist_id) == ["/m/a.mp3"]
        assert load_rules(db, playlist_id) == rules.normalized()

        # A new matching track appears after a scan: refresh picks it up.
        root = db.list_roots()[0]
        db.upsert_track(root.id, "/m/d.mp3", 1, 1.0)
        track = db.get_track_by_path("/m/d.mp3")
        db.set_cached_metadata(track.id, 1.0, TrackMetadata(bpm=171.0, key="Em"))
        db.commit()
        assert refresh_smart_playlists(db, now=NOW) == {playlist_id: 2}
        assert db.playlist_paths(playlist_id) == ["/m/a.mp3", "/m/d.mp3"]

        # Played last week: the "not played for 90 days" rule drops it.
        db.set_play_stats([("/m/a.mp3", 1, (NOW - timedelta(days=7)).isoformat())])
        count = update_smart_playlist(db, playlist_id, SmartRules(bpm_min=170, not_played_days=90), now=NOW)
        assert count == 2
        assert sorted(db.playlist_paths(playlist_id)) == ["/m/c.mp3", "/m/d.mp3"]

        db.delete_playlist(playlist_id)
        assert db.list_smart_rules() == {}


def test_ordinary_playlists_have_no_rules_and_unreadable_rules_are_skipped():
    with _db_with_tracks() as db:
        plain = db.create_playlist("Hand-made", ["/m/b.mp3"])
        assert load_rules(db, plain) is None
        broken = db.create_playlist("Broken", ["/m/b.mp3"], SOURCE_SMART)
        db.set_smart_rules(broken, "not json")
        assert refresh_smart_playlists(db, now=NOW) == {}
        assert db.playlist_paths(broken) == ["/m/b.mp3"]
