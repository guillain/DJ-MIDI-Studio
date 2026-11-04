"""Auto-organize library files into category folders (issue #406).

A sibling to the template-based renamer (`rename.py`, issue #260): moves
each selected track from wherever it is now into
``<its own library root>/<Family>/<Name>/<unchanged filename>``, following
the taxonomy category the library already resolved for it -- the
filename itself is never touched (use *Rename files…* for that, before or
after organizing). Same safety discipline as `rename.py`, reused directly
where it's generic: a file outside its own configured library root or
inside a protected DJ-software folder (`in_protected_folder`,
`is_within_roots`) is refused, a target path already taken on disk or in
the index is a conflict, and `LibraryDB.rename_track_paths` (already
old/new-path-agnostic, not folder-specific) follows every move in the
index. Only a track with a confirmed (exact/alias) category moves --
never a fuzzy suggestion, which isn't applied anywhere else either.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .db import LibraryDB
from .rename import in_protected_folder, is_within_roots, sanitize

if TYPE_CHECKING:
    from .workspace import LibraryRow

STATUS_MOVE = "move"
STATUS_UNCHANGED = "unchanged"
STATUS_NO_CATEGORY = "no category"
STATUS_CONFLICT = "conflict"
STATUS_REFUSED = "refused"


@dataclass(frozen=True)
class OrganizeSource:
    """One track to organize, as the library table knows it."""

    track_id: int
    path: str
    category: str | None
    """A confirmed ``"Family%%Name"`` -- a fuzzy suggestion is never used."""
    root_path: str | None
    """The one configured library root `path` lies under, or `None`."""
    missing: bool = False


@dataclass(frozen=True)
class OrganizeItem:
    track_id: int
    old_path: str
    new_path: str | None
    status: str
    reason: str = ""

    @property
    def will_move(self) -> bool:
        return self.status == STATUS_MOVE


@dataclass(frozen=True)
class OrganizePlan:
    items: tuple[OrganizeItem, ...]

    @property
    def moves(self) -> list[tuple[str, str]]:
        """``(old path, new path)`` of every track that will move."""
        return [(item.old_path, item.new_path) for item in self.items if item.will_move and item.new_path]

    def count(self, status: str) -> int:
        return sum(1 for item in self.items if item.status == status)


@dataclass
class OrganizeResult:
    renamed: list[tuple[str, str]] = field(default_factory=list)
    """``(old path, new path)`` actually moved, in order -- named like
    `rename.RenameResult`'s so `gui.commands.RenameFilesCommand` can apply
    either without caring which."""
    failed: list[tuple[str, str]] = field(default_factory=list)
    """``(path, reason)`` left as it was."""


def category_folder(category: str) -> tuple[str, str]:
    """``"Family%%Name"`` -> sanitized ``(family, name)`` path components."""
    family, _, name = category.partition("%%")
    return sanitize(family) or "Other", sanitize(name) or "Other"


def target_path(old_path: str, root_path: str, category: str) -> str:
    family, name = category_folder(category)
    return str(Path(root_path) / family / name / Path(old_path).name)


def _real(path: str | Path) -> str:
    return os.path.realpath(os.fspath(path))


def root_for_path(path: str | Path, roots: Iterable[str | Path]) -> str | None:
    """The one configured root `path` lies strictly under, else `None`."""
    real = Path(_real(path))
    for root in roots:
        root_real = Path(_real(root))
        if real != root_real and real.is_relative_to(root_real):
            return str(root)
    return None


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def plan_organize(sources: Iterable[OrganizeSource], indexed_paths: Iterable[str] = ()) -> OrganizePlan:
    """The preview of organizing `sources`; see the module docstring for
    the rules. Reads the disk (existence checks) but never changes it."""
    indexed = {path.casefold() for path in indexed_paths}
    drafts: list[OrganizeItem] = []
    for source in sources:
        old = str(source.path)

        def item(
            status: str, reason: str = "", new: str | None = None, old: str = old, track_id: int = source.track_id
        ) -> OrganizeItem:
            return OrganizeItem(track_id, old, new, status, reason)

        if source.missing or not Path(old).is_file():
            drafts.append(item(STATUS_REFUSED, "file not found"))
            continue
        if in_protected_folder(old):
            drafts.append(item(STATUS_REFUSED, "inside a DJ software folder"))
            continue
        if source.root_path is None or not is_within_roots(old, [source.root_path]):
            drafts.append(item(STATUS_REFUSED, "outside its library root"))
            continue
        if not source.category:
            drafts.append(item(STATUS_NO_CATEGORY, "no confirmed category"))
            continue
        new = target_path(old, source.root_path, source.category)
        if new == old or _same_file(old, new):
            drafts.append(item(STATUS_UNCHANGED, "already in its category folder", new))
            continue
        drafts.append(item(STATUS_MOVE, "", new))

    # Two tracks of the batch landing on one path both stay as they are.
    targets = Counter(draft.new_path.casefold() for draft in drafts if draft.will_move and draft.new_path)
    items: list[OrganizeItem] = []
    for draft in drafts:
        if not draft.will_move or draft.new_path is None:
            items.append(draft)
            continue
        new, old = draft.new_path, draft.old_path
        reason = ""
        if targets[new.casefold()] > 1:
            reason = f"{targets[new.casefold()] - 1} other selected track(s) would land on the same path"
        elif os.path.lexists(new) and not _same_file(old, new):
            reason = "a file already exists at the target path"
        elif new.casefold() in indexed and new.casefold() != old.casefold():
            reason = "this path is already in the library index"
        if reason:
            items.append(OrganizeItem(draft.track_id, old, new, STATUS_CONFLICT, reason))
        else:
            items.append(draft)
    return OrganizePlan(items=tuple(items))


def plan_from_rows(db: LibraryDB, rows: Iterable[LibraryRow]) -> OrganizePlan:
    """`plan_organize` for library rows the Music Library table already
    resolved a category for (a row not indexed under any root is refused,
    not silently skipped)."""
    roots = [root.path for root in db.list_roots()]
    indexed = [record.path for record in db.list_tracks()]
    sources = [
        OrganizeSource(row.track_id, row.path, row.category, root_for_path(row.path, roots), row.missing)
        for row in rows
    ]
    return plan_organize(sources, indexed)


def apply_organize(
    db: LibraryDB,
    pairs: Iterable[tuple[str, str]],
    makedirs: Callable[[str], None] = lambda path: os.makedirs(path, exist_ok=True),
    move: Callable[[str, str], None] = os.rename,
) -> OrganizeResult:
    """Move each ``(old, new)`` file (creating the target's category
    folders as needed) then point the index at the new paths. Each pair is
    re-checked first -- `old` still a file, outside any DJ software folder,
    `new` not already taken -- and a pair failing a check or the move
    itself is reported in `failed` while the others still go. Undoing a
    batch is the same call with every moved pair swapped, which also moves
    the files right back (an emptied category folder is left behind, like
    any other empty folder this app doesn't clean up)."""
    result = OrganizeResult()
    for old, new in pairs:
        old, new = str(old), str(new)
        if in_protected_folder(old):
            result.failed.append((old, "inside a DJ software folder"))
            continue
        if not Path(old).is_file():
            result.failed.append((old, "file not found"))
            continue
        if os.path.lexists(new) and not _same_file(old, new):
            result.failed.append((old, f"{Path(new).name} already exists at the target path"))
            continue
        try:
            makedirs(str(Path(new).parent))
            move(old, new)
        except OSError as exc:
            result.failed.append((old, str(exc)))
            continue
        result.renamed.append((old, new))
    db.rename_track_paths(result.renamed)
    return result


__all__ = [
    "STATUS_CONFLICT",
    "STATUS_MOVE",
    "STATUS_NO_CATEGORY",
    "STATUS_REFUSED",
    "STATUS_UNCHANGED",
    "OrganizeItem",
    "OrganizePlan",
    "OrganizeResult",
    "OrganizeSource",
    "apply_organize",
    "category_folder",
    "plan_from_rows",
    "plan_organize",
    "root_for_path",
    "target_path",
]
