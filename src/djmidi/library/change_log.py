"""Persistent change history for risky library writes (issue #261).

The Music Library tab's `QUndoStack` only lives for a session. Every write
this app makes to a real file is therefore also logged in `LibraryDB`
(`change_log` + `change_items`): one entry per operation, one item per file
with its before/after state, so the Change history window can show what
changed and revert it after a restart.

Built-in kinds:

- ``tags`` (`record_tag_changes`): before/after are the managed tag values
  that changed. Reverting writes the old values back through the same
  surgical `write_metadata`, but only for a field whose current value is
  still the one this app wrote -- a tag edited since (in Serato, say) is
  left alone and reported, never overwritten blindly.
- ``trash`` (`record_trash`): a duplicate copy moved to the Trash. Reverting
  moves it back from where the Trash put it, if nothing has taken its place,
  and un-flags it in the index. Playlists repointed at the kept copy stay
  repointed.
- ``rename`` (`record_renames`): a file moved/renamed (template renaming,
  #260). Reverting moves it back and relinks the index (and this app's
  playlists) to the old path.
- ``cover`` (`record_cover_change`, #279): a front cover set or removed
  (#256). ``before`` keeps the previous picture itself (Base64), ``after``
  only a fingerprint of what was written. Reverting restores the previous
  picture only while the file still holds the cover this app wrote; its
  reverter is plugged in with `register_reverter`, like any later writer's.

Other writers log through `record_change` with their own kind and plug a
reverter in with `register_reverter`; an entry whose kind has no reverter is
shown but can't be reverted.

Every revert is itself logged (``"Revert #N: ..."``), so the history stays
a faithful account of what happened to the files. Qt-free.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import shutil
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

from .db import ChangeItem, ChangeRecord, LibraryDB

_LOGGER = logging.getLogger(__name__)

KIND_TAGS = "tags"
KIND_TRASH = "trash"
KIND_RENAME = "rename"
KIND_COVER = "cover"
KIND_RESTORE = "restore"

# Oldest entries beyond this are dropped when a new one is logged.
MAX_ENTRIES = 1000

TagChanges = Mapping[str, tuple[Mapping[str, object], Mapping[str, object]]]


# Why a revert left a file alone (issue #319): English templates, shown in
# the interface language through `RevertSkipped.describe(translate)`.
_SKIP_NOT_FOUND = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "file not found")
_SKIP_UNREADABLE_TAGS = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "its tags can't be read")
_SKIP_CHANGED_SINCE = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "{fields} changed since")
_SKIP_TRASH_UNKNOWN = QT_TRANSLATE_NOOP(
    "ChangeHistoryDialog", "where the Trash put it is unknown -- put it back from the Trash yourself"
)
_SKIP_ORIGINAL_TAKEN = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "a file already exists at its original location")
_SKIP_NOT_IN_TRASH = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "no longer in the Trash")
_SKIP_NOT_FOUND_AT = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "not found at {path}")
_SKIP_OLD_NAME_TAKEN = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "a file already exists at its old name")
_SKIP_COVER_CHANGED = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "its cover changed since")
_SKIP_COVER_NOT_KEPT = QT_TRANSLATE_NOOP("ChangeHistoryDialog", "the previous cover wasn't kept")


class RevertSkipped(Exception):
    """A file a revert must leave alone (changed since, gone, ...).

    Built from an English `template` and its `fields`: ``str(exc)`` is the
    English reason, `describe` the reason in the interface language."""

    def __init__(self, template: str, **fields: object) -> None:
        super().__init__(template.format(**fields))
        self.template = template
        self.fields = fields

    def describe(self, translate: Translate = untranslated) -> str:
        return translate(self.template).format(**self.fields)


@dataclass
class RevertContext:
    """The I/O a reverter may use; injected so tests never touch real files."""

    writer: Callable[..., None] | None = None
    reader: Callable[[str], object] | None = None
    mover: Callable[[str, str], object] = shutil.move
    cover_writer: Callable[[str, object | None], None] | None = None
    cover_reader: Callable[[str], object | None] | None = None

    def write(self, path: str, **values: object) -> None:
        writer = self.writer
        if writer is None:
            from .metadata import write_metadata as writer
        writer(path, **values)

    def read(self, path: str) -> object:
        reader = self.reader
        if reader is None:
            from .metadata import read_metadata as reader
        return reader(path)

    def write_cover(self, path: str, cover: object | None) -> None:
        writer = self.cover_writer
        if writer is None:
            from .cover_art import write_cover_art as writer
        writer(path, cover)

    def read_cover(self, path: str) -> object | None:
        reader = self.cover_reader
        if reader is None:
            from .cover_art import read_front_cover as reader
        return reader(path)


# A reverter undoes one item and returns the item to log for that revert
# (its before/after swapped), or None when the file already holds the old
# state. It raises RevertSkipped (or OSError) to leave the file alone.
Reverter = Callable[[LibraryDB, ChangeItem, RevertContext], ChangeItem | None]


@dataclass
class RevertResult:
    change_id: int
    reverted: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    """Files that already held their old state: nothing to write."""
    failed: list[tuple[str, str]] = field(default_factory=list)
    log_id: int | None = None
    """The entry logging this revert, when anything was written."""

    @property
    def complete(self) -> bool:
        return not self.failed


# --- recording ----------------------------------------------------------


def record_change(
    db: LibraryDB,
    kind: str,
    summary: str,
    items: Iterable[ChangeItem],
    now: Callable[[], float] = time.time,
) -> int | None:
    """Log one operation. Returns its id, or None when `items` is empty.

    Never raises: the write it describes already happened, so a logging
    failure is reported in the log file rather than surfacing as a failed
    write."""
    items = list(items)
    if not items:
        return None
    try:
        change_id = db.add_change(kind, summary, items, now())
        db.prune_changes(MAX_ENTRIES)
    except Exception:  # see docstring
        _LOGGER.exception("Could not record %s change in the history", kind)
        return None
    return change_id


def record_tag_changes(db: LibraryDB, changes: TagChanges, summary: str | None = None, **kwargs) -> int | None:
    """Log tag writes: ``{path: (old values, new values)}`` for the files
    actually written."""
    items = [ChangeItem(str(path), _plain(old), _plain(new)) for path, (old, new) in changes.items()]
    if summary is None:
        names = sorted({name for item in items for name in item.after})
        summary = f"Edit {', '.join(names)} of {len(items)} track(s)"
    return record_change(db, KIND_TAGS, summary, items, **kwargs)


def record_trash(
    db: LibraryDB,
    moved: Iterable[tuple[str, str]],
    trash_paths: Mapping[str, str] | None = None,
    **kwargs,
) -> int | None:
    """Log copies moved to the Trash: ``(discarded copy, kept copy)``, and
    where the Trash put each one when known (needed to put it back)."""
    trash_paths = trash_paths or {}
    items = [
        ChangeItem(str(path), {"path": str(path), "kept": str(kept)}, {"trash_path": trash_paths.get(str(path))})
        for path, kept in moved
    ]
    return record_change(db, KIND_TRASH, f"Move {len(items)} duplicate(s) to the Trash", items, **kwargs)


def record_renames(db: LibraryDB, renames: Iterable[tuple[str, str]], summary: str | None = None, **kwargs) -> int | None:
    """Log files moved/renamed: ``(old path, new path)``."""
    items = [ChangeItem(str(old), {"path": str(old)}, {"path": str(new)}) for old, new in renames]
    return record_change(db, KIND_RENAME, summary or f"Rename {len(items)} file(s)", items, **kwargs)


def cover_state(cover: object | None, keep_data: bool = True) -> dict[str, object]:
    """JSON-safe record of a front cover (a `cover_art.CoverArt` or None).

    ``sha256`` fingerprints the picture bytes (None for "no cover"); with
    `keep_data` the bytes themselves are kept, Base64, so a revert can write
    them back. Only the side a revert may restore needs them."""
    data = getattr(cover, "data", None) if cover is not None else None
    if not data:
        return {"sha256": None}
    state: dict[str, object] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "mime": str(getattr(cover, "mime", "") or ""),
        "description": str(getattr(cover, "description", "") or ""),
        "size": len(data),
    }
    if keep_data:
        state["data"] = base64.b64encode(data).decode("ascii")
    return state


def cover_from_state(state: Mapping[str, object]) -> object | None:
    """The `CoverArt` a `cover_state` (with its data) describes, or None for
    "no cover". Raises RevertSkipped when the picture wasn't kept."""
    if not state.get("sha256"):
        return None
    encoded = state.get("data")
    if not isinstance(encoded, str):
        raise RevertSkipped(_SKIP_COVER_NOT_KEPT)
    from .cover_art import CoverArt

    return CoverArt(base64.b64decode(encoded), str(state.get("mime") or ""), str(state.get("description") or ""))


def record_cover_change(
    db: LibraryDB, path: str, old: object | None, new: object | None, summary: str | None = None, **kwargs
) -> int | None:
    """Log one front cover write: `old` is the cover the file held before
    (kept, so it can be restored), `new` the one written (None = removed)."""
    if summary is None:
        summary = f"{'Set' if new is not None else 'Remove'} cover of {Path(path).name}"
    item = ChangeItem(str(path), cover_state(old), cover_state(new, keep_data=False))
    return record_change(db, KIND_COVER, summary, [item], **kwargs)


def _plain(values: Mapping[str, object]) -> dict[str, object]:
    """JSON-safe copy (tag values are str/float/None; anything else as str)."""
    return {
        name: value if value is None or isinstance(value, (str, int, float, bool)) else str(value)
        for name, value in values.items()
    }


# --- reverting ----------------------------------------------------------


def _same_value(a: object, b: object) -> bool:
    if a == "":
        a = None
    if b == "":
        b = None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.005
    if a is None or b is None:
        return a is b
    return str(a) == str(b)


def _revert_tags(db: LibraryDB, item: ChangeItem, ctx: RevertContext) -> ChangeItem | None:
    if not Path(item.path).is_file():
        raise RevertSkipped(_SKIP_NOT_FOUND)
    current = ctx.read(item.path)
    if current is None:
        raise RevertSkipped(_SKIP_UNREADABLE_TAGS)
    now = {name: getattr(current, name, None) for name in item.before}
    if all(_same_value(now[name], item.before[name]) for name in item.before):
        return None
    changed_since = [
        name for name in item.before
        if not _same_value(now[name], item.after.get(name)) and not _same_value(now[name], item.before[name])
    ]
    if changed_since:
        raise RevertSkipped(_SKIP_CHANGED_SINCE, fields=", ".join(sorted(changed_since)))
    restore = {name: item.before[name] for name in item.before if not _same_value(now[name], item.before[name])}
    ctx.write(item.path, **restore)
    return ChangeItem(item.path, {name: now[name] for name in restore}, restore)


def _revert_trash(db: LibraryDB, item: ChangeItem, ctx: RevertContext) -> ChangeItem | None:
    original = str(item.before.get("path") or item.path)
    trash_path = item.after.get("trash_path")
    if not trash_path:
        raise RevertSkipped(_SKIP_TRASH_UNKNOWN)
    if Path(original).exists():
        if not Path(str(trash_path)).exists():
            return None
        raise RevertSkipped(_SKIP_ORIGINAL_TAKEN)
    if not Path(str(trash_path)).exists():
        raise RevertSkipped(_SKIP_NOT_IN_TRASH)
    Path(original).parent.mkdir(parents=True, exist_ok=True)
    ctx.mover(str(trash_path), original)
    stat = Path(original).stat()
    db.mark_path_present(original, stat.st_size, stat.st_mtime)
    return ChangeItem(original, {"trash_path": trash_path}, {"path": original})


def _revert_rename(db: LibraryDB, item: ChangeItem, ctx: RevertContext) -> ChangeItem | None:
    old, new = str(item.before["path"]), str(item.after["path"])
    if Path(old).exists() and not Path(new).exists():
        return None
    if not Path(new).exists():
        raise RevertSkipped(_SKIP_NOT_FOUND_AT, path=new)
    if Path(old).exists():
        raise RevertSkipped(_SKIP_OLD_NAME_TAKEN)
    Path(old).parent.mkdir(parents=True, exist_ok=True)
    ctx.mover(new, old)
    track = db.get_track_by_path(new)
    if track is not None:
        stat = Path(old).stat()
        db.mark_paths_missing([new])
        db.relink_tracks([(track.id, old, track.root_id, stat.st_size, stat.st_mtime)])
    return ChangeItem(old, {"path": new}, {"path": old})


def _revert_cover(db: LibraryDB, item: ChangeItem, ctx: RevertContext) -> ChangeItem | None:
    if not Path(item.path).is_file():
        raise RevertSkipped(_SKIP_NOT_FOUND)
    current = ctx.read_cover(item.path)
    current_sha = cover_state(current, keep_data=False)["sha256"]
    if current_sha == item.before.get("sha256"):
        return None
    if current_sha != item.after.get("sha256"):
        raise RevertSkipped(_SKIP_COVER_CHANGED)
    restored = cover_from_state(item.before)
    ctx.write_cover(item.path, restored)
    # What's being replaced is the cover this app wrote: keep it, so the
    # revert can itself be reverted.
    return ChangeItem(item.path, cover_state(current), cover_state(restored, keep_data=False))


_REVERTERS: dict[str, Reverter] = {
    KIND_TAGS: _revert_tags,
    KIND_TRASH: _revert_trash,
    KIND_RENAME: _revert_rename,
}

# The kind a revert is logged under (a restored Trash copy isn't itself a
# Trash move, so it gets a kind with no reverter).
_REVERT_KIND = {KIND_TRASH: KIND_RESTORE}


def register_reverter(kind: str, reverter: Reverter, *, replace: bool = False) -> None:
    """Make entries of `kind` revertible (e.g. cover art, #256)."""
    if kind in _REVERTERS and not replace:
        raise ValueError(f"a reverter is already registered for {kind!r}")
    _REVERTERS[kind] = reverter


register_reverter(KIND_COVER, _revert_cover)


def is_revertible(change: ChangeRecord) -> bool:
    return change.reverted_at is None and change.kind in _REVERTERS


def revert_change(
    db: LibraryDB,
    change_id: int,
    context: RevertContext | None = None,
    now: Callable[[], float] = time.time,
    translate: Translate = untranslated,
) -> RevertResult:
    """Revert every file of entry `change_id` that can safely be reverted.

    The entry is marked reverted once no file failed (a file already back
    in its old state counts as done), so a partly failed revert can be
    retried after fixing the cause. Raises ValueError for an unknown,
    already reverted or non-revertible entry. ``translate`` gives the
    reasons in `RevertResult.failed` in the interface language (issue #319)."""
    change = db.get_change(change_id)
    if change is None:
        raise ValueError(f"no change #{change_id} in the history")
    if change.reverted_at is not None:
        raise ValueError(f"change #{change_id} was already reverted")
    reverter = _REVERTERS.get(change.kind)
    if reverter is None:
        raise ValueError(f"{change.kind!r} changes can't be reverted")
    context = context or RevertContext()
    result = RevertResult(change_id)
    logged: list[ChangeItem] = []
    for item in change.items:
        try:
            inverse = reverter(db, item, context)
        except RevertSkipped as exc:
            result.failed.append((item.path, exc.describe(translate)))
            continue
        except (OSError, ValueError) as exc:
            result.failed.append((item.path, str(exc)))
            continue
        if inverse is None:
            result.already.append(item.path)
        else:
            result.reverted.append(item.path)
            logged.append(inverse)
    if logged:
        kind = _REVERT_KIND.get(change.kind, change.kind)
        result.log_id = record_change(db, kind, f"Revert #{change.id}: {change.summary}", logged, now=now)
    if result.complete:
        db.mark_change_reverted(change.id, now())
    return result


__all__ = [
    "KIND_COVER",
    "KIND_RENAME",
    "KIND_RESTORE",
    "KIND_TAGS",
    "KIND_TRASH",
    "MAX_ENTRIES",
    "RevertContext",
    "RevertResult",
    "RevertSkipped",
    "Reverter",
    "cover_from_state",
    "cover_state",
    "is_revertible",
    "record_change",
    "record_cover_change",
    "record_renames",
    "record_tag_changes",
    "record_trash",
    "register_reverter",
    "revert_change",
]
