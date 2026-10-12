"""Workspace backup and restore (issue #187) -- temporary folders only."""

import json
import sqlite3
import zipfile

import pytest

from djmidi import backup
from djmidi.backup import BackupError, create_backup, read_manifest, restore_backup
from djmidi.library.db import LibraryDB


def _make_source(tmp_path):
    workspace = tmp_path / "src" / "workspace"
    (workspace / "Controllers").mkdir(parents=True)
    (workspace / "Controllers" / "my-pad.json").write_text('{"name": "My Pad"}')
    (workspace / "Sync").mkdir()
    (workspace / "Sync" / "DDJ-XP2.json").write_text("{}")
    (workspace / "README.txt").write_text("hello")
    preferences = tmp_path / "src" / "preferences.json"
    preferences.write_text('{"theme": "dark"}')
    library = tmp_path / "src" / "library.sqlite3"
    with LibraryDB(library) as db:
        db.add_root("/Music/Tek")
        db.commit()
    return workspace, preferences, library


def _targets(tmp_path):
    return {
        "workspace": tmp_path / "dst" / "workspace",
        "preferences_path": tmp_path / "dst" / "prefs" / "preferences.json",
        "library_db_path": tmp_path / "dst" / "library.sqlite3",
    }


def _backup(tmp_path, *, include_library=True):
    workspace, preferences, library = _make_source(tmp_path)
    archive = tmp_path / "out" / "backup.djmidi-backup.zip"
    manifest = create_backup(
        archive,
        include_library=include_library,
        workspace=workspace,
        preferences_path=preferences,
        library_db_path=library,
    )
    return archive, manifest


def test_create_backup_writes_manifest_and_files(tmp_path):
    archive, manifest = _backup(tmp_path)
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        data = json.loads(zf.read("manifest.json"))
    assert {
        "workspace/Controllers/my-pad.json",
        "workspace/Sync/DDJ-XP2.json",
        "workspace/README.txt",
        "preferences/preferences.json",
        "library/library.sqlite3",
        "manifest.json",
    } == names
    assert data["format"] == backup.FORMAT
    assert data["version"] == backup.FORMAT_VERSION
    assert data["app_version"] == backup.app_version()
    assert data["created_at"]
    assert {entry["path"] for entry in data["entries"]} == names - {"manifest.json"}
    assert manifest.has(backup.LIBRARY)
    assert not (archive.parent / (archive.name + ".part")).exists()


def test_library_is_optional(tmp_path):
    archive, manifest = _backup(tmp_path, include_library=False)
    assert not manifest.has(backup.LIBRARY)
    assert "library/library.sqlite3" not in zipfile.ZipFile(archive).namelist()


def test_library_snapshot_is_consistent_while_open(tmp_path):
    """The library DB is copied through SQLite's backup API: a DB another
    connection holds open (with committed data) is captured whole."""
    workspace, preferences, library = _make_source(tmp_path)
    holder = LibraryDB(library)
    holder.add_root("/Music/Electro")
    holder.commit()
    try:
        archive = tmp_path / "b.zip"
        create_backup(archive, include_library=True, workspace=workspace,
                      preferences_path=preferences, library_db_path=library)
    finally:
        holder.close()
    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(zipfile.ZipFile(archive).read("library/library.sqlite3"))
    with LibraryDB(restored) as db:
        assert {root.path for root in db.list_roots()} == {"/Music/Tek", "/Music/Electro"}


def test_backup_skips_earlier_backups_and_itself(tmp_path):
    workspace, preferences, library = _make_source(tmp_path)
    exports = workspace / "Exports"
    exports.mkdir()
    (exports / "old.djmidi-backup.zip").write_bytes(b"old")
    (exports / "playlist.crate").write_bytes(b"crate")
    archive = exports / "new.djmidi-backup.zip"
    create_backup(archive, workspace=workspace, preferences_path=preferences, library_db_path=library)
    names = zipfile.ZipFile(archive).namelist()
    assert "workspace/Exports/playlist.crate" in names
    assert not any(name.endswith(backup.BACKUP_SUFFIX) for name in names)


def test_memory_library_is_never_backed_up(tmp_path):
    workspace, preferences, _ = _make_source(tmp_path)
    manifest = create_backup(tmp_path / "b.zip", include_library=True, workspace=workspace,
                             preferences_path=preferences, library_db_path=":memory:")
    assert not manifest.has(backup.LIBRARY)
    assert backup.library_db_size(":memory:") is None


def test_dry_run_plans_without_writing(tmp_path):
    archive, _ = _backup(tmp_path)
    targets = _targets(tmp_path)
    targets["workspace"].mkdir(parents=True)
    (targets["workspace"] / "README.txt").write_text("mine")
    plan = restore_backup(archive, **targets)
    assert [item.member for item in plan.overwrites] == ["workspace/README.txt"]
    assert len(plan.creates) == 4
    assert (targets["workspace"] / "README.txt").read_text() == "mine"
    assert not targets["preferences_path"].exists()
    assert not targets["library_db_path"].exists()


def test_restore_round_trip(tmp_path):
    archive, _ = _backup(tmp_path)
    targets = _targets(tmp_path)
    targets["workspace"].mkdir(parents=True)
    (targets["workspace"] / "README.txt").write_text("mine")
    (targets["workspace"] / "keep.txt").write_text("untouched")
    with LibraryDB(targets["library_db_path"]) as db:
        db.add_root("/Other")
        db.commit()
    restore_backup(archive, dry_run=False, **targets)
    assert (targets["workspace"] / "README.txt").read_text() == "hello"
    assert (targets["workspace"] / "Controllers" / "my-pad.json").read_text() == '{"name": "My Pad"}'
    assert (targets["workspace"] / "keep.txt").read_text() == "untouched"
    assert json.loads(targets["preferences_path"].read_text()) == {"theme": "dark"}
    with LibraryDB(targets["library_db_path"]) as db:
        assert [root.path for root in db.list_roots()] == ["/Music/Tek"]


def test_restore_can_leave_the_library_alone(tmp_path):
    archive, _ = _backup(tmp_path)
    targets = _targets(tmp_path)
    plan = restore_backup(archive, dry_run=False, include_library=False, **targets)
    assert plan.skipped_library
    assert not targets["library_db_path"].exists()
    assert targets["preferences_path"].is_file()


def _forge(path, manifest, members):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def _manifest(*entries):
    return {
        "format": backup.FORMAT,
        "version": 1,
        "app_version": "0",
        "created_at": "",
        "entries": [{"kind": kind, "path": path, "size": 1} for kind, path in entries],
    }


@pytest.mark.parametrize(
    "member",
    ["workspace/../evil.txt", "workspace/a/../../evil.txt", "/etc/evil", "workspace/", "workspace\\..\\evil",
     "preferences/../workspace/x"],
)
def test_restore_refuses_path_traversal(tmp_path, member):
    kind = member.split("/")[0] if member.split("/")[0] in backup.KINDS else "workspace"
    archive = _forge(tmp_path / "evil.zip", _manifest((kind, member)), {member: b"x"})
    with pytest.raises(BackupError):
        restore_backup(archive, dry_run=False, **_targets(tmp_path))
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "dst").exists()


def test_restore_refuses_symlink_escape(tmp_path):
    """A target folder that is a symlink out of the workspace is refused."""
    targets = _targets(tmp_path)
    targets["workspace"].mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (targets["workspace"] / "Controllers").symlink_to(outside)
    archive = _forge(tmp_path / "b.zip", _manifest(("workspace", "workspace/Controllers/x.json")),
                     {"workspace/Controllers/x.json": b"{}"})
    with pytest.raises(BackupError):
        restore_backup(archive, **targets)
    assert list(outside.iterdir()) == []


def test_restore_rejects_non_backups(tmp_path):
    not_zip = tmp_path / "a.zip"
    not_zip.write_text("nope")
    with pytest.raises(BackupError):
        read_manifest(not_zip)
    no_manifest = tmp_path / "b.zip"
    with zipfile.ZipFile(no_manifest, "w") as zf:
        zf.writestr("x", "y")
    with pytest.raises(BackupError):
        read_manifest(no_manifest)
    wrong_format = _forge(tmp_path / "c.zip", {"format": "other"}, {})
    with pytest.raises(BackupError):
        read_manifest(wrong_format)
    future = _forge(tmp_path / "d.zip", {**_manifest(), "version": 99}, {})
    with pytest.raises(BackupError, match="update"):
        read_manifest(future)
    incomplete = _forge(tmp_path / "e.zip", _manifest(("workspace", "workspace/x")), {})
    with pytest.raises(BackupError, match="incomplete"):
        read_manifest(incomplete)


def test_restore_validates_payloads_before_writing(tmp_path):
    archive = _forge(
        tmp_path / "b.zip",
        _manifest(("workspace", "workspace/a.txt"), ("preferences", "preferences/preferences.json")),
        {"workspace/a.txt": b"a", "preferences/preferences.json": b"{not json"},
    )
    targets = _targets(tmp_path)
    with pytest.raises(BackupError, match="JSON"):
        restore_backup(archive, dry_run=False, **targets)
    assert not (targets["workspace"] / "a.txt").exists()


def test_restore_rejects_a_corrupt_library(tmp_path):
    archive = _forge(tmp_path / "b.zip", _manifest(("library", "library/library.sqlite3")),
                     {"library/library.sqlite3": b"garbage" * 200})
    targets = _targets(tmp_path)
    with LibraryDB(targets["library_db_path"]) as db:
        db.add_root("/Keep")
        db.commit()
    with pytest.raises(BackupError):
        restore_backup(archive, dry_run=False, **targets)
    connection = sqlite3.connect(targets["library_db_path"])
    assert connection.execute("SELECT path FROM roots").fetchall() == [("/Keep",)]
    connection.close()


def test_default_backup_name():
    from datetime import UTC, datetime

    assert backup.default_backup_name(datetime(2026, 10, 11, 15, 30, tzinfo=UTC)) == (
        "DJ MIDI Studio 2026-10-11 1530.djmidi-backup.zip"
    )
