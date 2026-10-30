"""Named mapping snapshots (phase 5 item 5)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from djmidi import snapshots
from djmidi.snapshots import (
    delete_snapshot,
    list_snapshots,
    save_snapshot,
    snapshot_dir,
)

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_snapshots_are_kept_per_mapping_newest_first(tmp_path):
    mapping = tmp_path / "a" / "mapping.xml"
    other = tmp_path / "b" / "mapping.xml"
    first = save_snapshot(mapping, "  before   the gig ", "<midi/>", "serato",
                          now=datetime(2026, 10, 1, 20, 0, tzinfo=UTC), root=tmp_path / "snaps")  # fmt: skip
    second = save_snapshot(mapping, "club", "<midi app='x'/>", "serato",
                           now=datetime(2026, 10, 2, 20, 0, tzinfo=UTC), root=tmp_path / "snaps")  # fmt: skip
    assert first.name == "before the gig" and first.path.suffix == ".xml"
    assert first.path.read_text(encoding="utf-8") == "<midi/>"
    assert [s.name for s in list_snapshots(mapping, tmp_path / "snaps")] == ["club", "before the gig"]
    assert list_snapshots(other, tmp_path / "snaps") == []
    assert snapshot_dir(mapping, tmp_path / "snaps") != snapshot_dir(other, tmp_path / "snaps")
    delete_snapshot(second)
    assert [s.name for s in list_snapshots(mapping, tmp_path / "snaps")] == ["before the gig"]
    assert not second.path.exists()


def test_same_second_same_name_gets_its_own_file_and_bad_names_are_refused(tmp_path):
    now = datetime(2026, 10, 1, tzinfo=UTC)
    a = save_snapshot("m.xml", "x", "1", "serato", now=now, root=tmp_path)
    b = save_snapshot("m.xml", "x", "2", "serato", now=now, root=tmp_path)
    assert a.path != b.path and b.path.name.endswith("-2.xml")
    for name in ("   ", "y" * 81):
        with pytest.raises(ValueError):
            save_snapshot("m.xml", name, "1", "serato", root=tmp_path)


def test_a_broken_index_or_a_missing_file_is_ignored(tmp_path):
    kept = save_snapshot("m.xml", "kept", "1", "serato", root=tmp_path)
    gone = save_snapshot("m.xml", "gone", "2", "serato", root=tmp_path)
    gone.path.unlink()
    assert [s.name for s in list_snapshots("m.xml", tmp_path)] == ["kept"]
    (kept.path.parent / snapshots.INDEX).write_text("not json", encoding="utf-8")
    assert list_snapshots("m.xml", tmp_path) == []
    (kept.path.parent / snapshots.INDEX).write_text(json.dumps([{"name": "x"}, 3]), encoding="utf-8")
    assert list_snapshots("m.xml", tmp_path) == []


def test_main_window_saves_compares_and_restores(tmp_path):
    from djmidi.gui.main_window import MainWindow

    mapping = tmp_path / "mapping.xml"
    mapping.write_bytes(FIXTURE.read_bytes())
    window = MainWindow()
    try:
        window._load_mapping_from_path(mapping, software_id="serato")
        assert window._save_snapshot_action.isEnabled()
        snapshot = window.save_snapshot("original")
        assert snapshot is not None and snapshot.path.is_file()
        original = list(window.config.controls)
        window.config.controls = original[:10]  # an edit that drops most controls
        dialog = window.open_snapshots()
        assert [s.name for s in dialog.snapshots] == ["original"] and dialog.restore_button.isEnabled()
        diff = window._compare_with_snapshot(snapshot)
        assert diff is not None and window._diff_dialog is diff
        assert window.restore_snapshot(snapshot) and len(window.config.controls) == len(original)
        window.undo_stack.undo()
        assert len(window.config.controls) == 10
        dialog._confirm = lambda _name: True
        assert dialog.delete_selected() and dialog.snapshots == []
        dialog.close()
    finally:
        window.close()
