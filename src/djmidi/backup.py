"""One-click workspace backup and restore (issue #187).

A backup is one zip holding everything the app keeps for the user, so a DJ
can move to another Mac (or recover from a bad edit) in two clicks:

* ``workspace/...``           the DJ MIDI Studio folder (``user_paths``):
  installed controller profiles, sync sets, drafts, logs, exports;
* ``preferences/preferences.json``  the preferences file;
* ``library/library.sqlite3``  the music library index -- optional, since it
  can be large; copied with SQLite's online backup API rather than as raw
  bytes, so a database the Music Library tab still has open is captured in
  a consistent state;
* ``manifest.json``            format/version, the app version, the creation
  time and every entry above.

Restoring is two-step, like ``metadata.clean_noise_frames``:
``restore_backup(..., dry_run=True)`` (the default) validates the manifest,
refuses any entry that would land outside its target folder (zip-slip) and
returns a :class:`RestorePlan` saying which files would be created or
overwritten, so the GUI can ask before anything is written; ``dry_run=False``
then writes them. A restore only adds and overwrites -- files that exist on
this machine but not in the backup are left alone. Qt-free.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from djmidi import user_paths

FORMAT = "djmidi-workspace-backup"
FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
BACKUP_SUFFIX = ".djmidi-backup.zip"

WORKSPACE = "workspace"
PREFERENCES = "preferences"
LIBRARY = "library"
KINDS = (WORKSPACE, PREFERENCES, LIBRARY)
_PREFERENCES_MEMBER = "preferences/preferences.json"
_LIBRARY_MEMBER = "library/library.sqlite3"


class BackupError(Exception):
    """The archive is not a usable DJ MIDI Studio backup."""


@dataclass(frozen=True)
class BackupEntry:
    kind: str
    path: str  # archive member name, POSIX, under the kind's prefix
    size: int

    def to_json(self) -> dict:
        return {"kind": self.kind, "path": self.path, "size": self.size}


@dataclass(frozen=True)
class BackupManifest:
    app_version: str
    created_at: str
    entries: tuple[BackupEntry, ...]

    def has(self, kind: str) -> bool:
        return any(entry.kind == kind for entry in self.entries)

    def to_json(self) -> dict:
        return {
            "format": FORMAT,
            "version": FORMAT_VERSION,
            "app_version": self.app_version,
            "created_at": self.created_at,
            "entries": [entry.to_json() for entry in self.entries],
        }


@dataclass(frozen=True)
class RestoreItem:
    kind: str
    member: str
    target: Path
    exists: bool


@dataclass
class RestorePlan:
    manifest: BackupManifest
    items: list[RestoreItem] = field(default_factory=list)
    skipped_library: bool = False  # in the archive but not restored

    @property
    def overwrites(self) -> list[RestoreItem]:
        return [item for item in self.items if item.exists]

    @property
    def creates(self) -> list[RestoreItem]:
        return [item for item in self.items if not item.exists]


def app_version() -> str:
    try:
        return importlib.metadata.version("djmidi")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def default_backup_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC).astimezone()).strftime("%Y-%m-%d %H%M")
    return f"DJ MIDI Studio {stamp}{BACKUP_SUFFIX}"


def _default_preferences_path() -> Path:
    from djmidi.plugins.preferences import default_preferences_path

    return default_preferences_path()


def _default_library_db_path() -> Path:
    from djmidi.library.db import default_library_db_path

    return default_library_db_path()


def _is_real_db(path: Path | None) -> bool:
    return path is not None and str(path) != ":memory:"


def library_db_size(library_db_path: str | Path | None = None) -> int | None:
    """Size in bytes of the library index, or None when there is none."""
    path = Path(library_db_path) if library_db_path is not None else _default_library_db_path()
    if not _is_real_db(path) or not path.is_file():
        return None
    return path.stat().st_size


def _workspace_files(root: Path, exclude: Path) -> Iterable[tuple[Path, str]]:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        # Never back up a backup: the default save folder is inside the
        # workspace, so every backup would otherwise contain the previous one.
        if path.name.endswith(BACKUP_SUFFIX) or path.resolve() == exclude:
            continue
        yield path, f"{WORKSPACE}/{path.relative_to(root).as_posix()}"


def _copy_sqlite(source: Path, destination: Path) -> None:
    """A consistent snapshot of `source`, even while another connection has
    it open (SQLite's online backup API, not a byte copy)."""
    src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def create_backup(
    dest_zip: str | Path,
    *,
    include_library: bool = False,
    workspace: str | Path | None = None,
    preferences_path: str | Path | None = None,
    library_db_path: str | Path | None = None,
) -> BackupManifest:
    """Write a backup zip at `dest_zip` (atomically) and return its manifest."""
    dest = Path(dest_zip)
    root = Path(workspace) if workspace is not None else user_paths.workspace_dir()
    prefs = Path(preferences_path) if preferences_path is not None else _default_preferences_path()
    library = Path(library_db_path) if library_db_path is not None else _default_library_db_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    entries: list[BackupEntry] = []
    try:
        with (
            tempfile.TemporaryDirectory(prefix="djmidi-backup-") as scratch,
            zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive,
        ):
            for path, member in _workspace_files(root, dest.resolve()):
                archive.write(path, member)
                entries.append(BackupEntry(WORKSPACE, member, path.stat().st_size))
            if prefs.is_file():
                archive.write(prefs, _PREFERENCES_MEMBER)
                entries.append(BackupEntry(PREFERENCES, _PREFERENCES_MEMBER, prefs.stat().st_size))
            if include_library and _is_real_db(library) and library.is_file():
                snapshot = Path(scratch) / "library.sqlite3"
                _copy_sqlite(library, snapshot)
                archive.write(snapshot, _LIBRARY_MEMBER)
                entries.append(BackupEntry(LIBRARY, _LIBRARY_MEMBER, snapshot.stat().st_size))
            manifest = BackupManifest(
                app_version=app_version(),
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
                entries=tuple(entries),
            )
            archive.writestr(MANIFEST_NAME, json.dumps(manifest.to_json(), indent=2))
        os.replace(partial, dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return manifest


def _safe_relative(member: str, prefix: str) -> PurePosixPath:
    """The part of `member` under `prefix/`, refusing anything that could
    escape its target folder (absolute paths, drive letters, ``..``)."""
    # A colon is an ordinary file-name character on macOS but a drive letter
    # or an alternate data stream on Windows.
    if "\\" in member or "\x00" in member or (os.name == "nt" and ":" in member):
        raise BackupError(f"Unsafe path in backup: {member!r}")
    path = PurePosixPath(member)
    if path.is_absolute() or not path.parts or path.parts[0] != prefix:
        raise BackupError(f"Unsafe path in backup: {member!r}")
    relative = PurePosixPath(*path.parts[1:])
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise BackupError(f"Unsafe path in backup: {member!r}")
    return relative


def _parse_manifest(data: object) -> BackupManifest:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("This file is not a DJ MIDI Studio backup.")
    version = data.get("version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise BackupError(f"This backup uses format version {version!r}; update DJ MIDI Studio to restore it.")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise BackupError("The backup manifest has no entry list.")
    entries = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS or not isinstance(raw.get("path"), str):
            raise BackupError(f"Invalid manifest entry: {raw!r}")
        kind, member = raw["kind"], raw["path"]
        _safe_relative(member, kind)
        if kind == PREFERENCES and member != _PREFERENCES_MEMBER:
            raise BackupError(f"Unexpected preferences entry: {member!r}")
        if kind == LIBRARY and member != _LIBRARY_MEMBER:
            raise BackupError(f"Unexpected library entry: {member!r}")
        entries.append(BackupEntry(kind, member, int(raw.get("size", 0))))
    return BackupManifest(
        app_version=str(data.get("app_version", "unknown")),
        created_at=str(data.get("created_at", "")),
        entries=tuple(entries),
    )


def read_manifest(backup_zip: str | Path) -> BackupManifest:
    try:
        with zipfile.ZipFile(backup_zip) as archive:
            return _read_manifest(archive)
    except zipfile.BadZipFile as exc:
        raise BackupError(f"Not a zip archive: {exc}") from exc


def _read_manifest(archive: zipfile.ZipFile) -> BackupManifest:
    try:
        raw = archive.read(MANIFEST_NAME)
    except KeyError as exc:
        raise BackupError("This file is not a DJ MIDI Studio backup (no manifest).") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupError(f"The backup manifest is unreadable: {exc}") from exc
    manifest = _parse_manifest(data)
    names = set(archive.namelist())
    missing = [entry.path for entry in manifest.entries if entry.path not in names]
    if missing:
        raise BackupError(f"The backup is incomplete; missing: {', '.join(missing[:5])}")
    return manifest


def _validate_payload(kind: str, data: bytes, scratch: Path) -> None:
    if kind == PREFERENCES:
        try:
            json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError(f"The backed-up preferences are not valid JSON: {exc}") from exc
    elif kind == LIBRARY:
        candidate = scratch / "check.sqlite3"
        candidate.write_bytes(data)
        try:
            connection = sqlite3.connect(f"{candidate.resolve().as_uri()}?mode=ro", uri=True)
            try:
                connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            raise BackupError(f"The backed-up library index is not a SQLite database: {exc}") from exc


def _write_atomically(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _restore_library(data: bytes, target: Path, scratch: Path) -> None:
    """Load the snapshot into `target` through SQLite's backup API, so an
    existing index is replaced as a whole rather than byte-overwritten."""
    snapshot = scratch / "restore.sqlite3"
    snapshot.write_bytes(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    _copy_sqlite(snapshot, target)


def restore_backup(
    backup_zip: str | Path,
    *,
    dry_run: bool = True,
    include_library: bool = True,
    workspace: str | Path | None = None,
    preferences_path: str | Path | None = None,
    library_db_path: str | Path | None = None,
) -> RestorePlan:
    """Plan (dry run, the default) or perform a restore of `backup_zip`.

    Raises :class:`BackupError` for anything that is not a valid backup --
    before writing a single file, since every entry is validated first."""
    root = Path(workspace) if workspace is not None else user_paths.workspace_dir()
    prefs = Path(preferences_path) if preferences_path is not None else _default_preferences_path()
    library = Path(library_db_path) if library_db_path is not None else _default_library_db_path()
    try:
        archive = zipfile.ZipFile(backup_zip)
    except zipfile.BadZipFile as exc:
        raise BackupError(f"Not a zip archive: {exc}") from exc
    with archive:
        manifest = _read_manifest(archive)
        plan = RestorePlan(manifest)
        resolved_root = root.resolve()
        for entry in manifest.entries:
            if entry.kind == WORKSPACE:
                target = root.joinpath(*_safe_relative(entry.path, WORKSPACE).parts)
                if not target.resolve().is_relative_to(resolved_root):
                    raise BackupError(f"Unsafe path in backup: {entry.path!r}")
            elif entry.kind == PREFERENCES:
                target = prefs
            else:
                if not include_library or not _is_real_db(library):
                    plan.skipped_library = True
                    continue
                target = library
            plan.items.append(RestoreItem(entry.kind, entry.path, target, target.exists()))
        if dry_run:
            return plan
        with tempfile.TemporaryDirectory(prefix="djmidi-restore-") as scratch_dir:
            scratch = Path(scratch_dir)
            payloads = {}
            for item in plan.items:
                if item.kind != WORKSPACE:
                    payloads[item.member] = archive.read(item.member)
                    _validate_payload(item.kind, payloads[item.member], scratch)
            for item in plan.items:
                if item.kind == LIBRARY:
                    _restore_library(payloads[item.member], item.target, scratch)
                else:
                    data = payloads.get(item.member)
                    _write_atomically(item.target, data if data is not None else archive.read(item.member))
    return plan


__all__ = [
    "BACKUP_SUFFIX",
    "BackupEntry",
    "BackupError",
    "BackupManifest",
    "RestoreItem",
    "RestorePlan",
    "app_version",
    "create_backup",
    "default_backup_name",
    "library_db_size",
    "read_manifest",
    "restore_backup",
]
