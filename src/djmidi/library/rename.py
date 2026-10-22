"""Rename audio files from a tag template (issue #260).

A template such as ``"{artist} - {title}"`` names each selected track
from its cached tags. `plan_renames` builds the preview -- one `RenameItem`
per track with its new path and a status -- and `apply_renames` performs
the renames it allows, then updates this app's index (`LibraryDB`
track rows and playlist entries follow the new path).

Guardrails, all checked before anything moves (and again right before
each rename, since the disk may have changed since the preview):

- a file is only ever renamed **inside its own folder** -- a template can't
  hold a path separator, and every tag value has its separators replaced
  -- so nothing leaves the library folder it was in;
- a file outside every configured library root, or inside a DJ software
  folder (`_Serato_`, `PIONEER`, `_Traktor`, …), is refused;
- a new name already taken on disk, in the index, or by another track of
  the same batch is a conflict and that track is skipped (case-only
  renames of the same file are allowed).

Serato, Traktor and Rekordbox store full paths, so a renamed file shows up
missing there until relinked: `RELINK_WARNING` says so and
`export_mapping_csv` writes an ``old_path,new_path`` CSV to relink from.
Their libraries are never written. Qt-free, so it's testable without a
`QApplication`; the GUI wraps `apply_renames` in an undoable command whose
undo is `apply_renames` with every pair swapped.
"""

from __future__ import annotations

import csv
import io
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .analysis import to_camelot
from .db import LibraryDB
from .metadata import TrackMetadata

DEFAULT_TEMPLATE = "{artist} - {title}"

TEMPLATE_FIELDS = ("artist", "title", "album", "genre", "bpm", "key", "camelot", "filename")
"""Placeholders a template may use; ``{filename}`` is the current name
without its extension."""

STATUS_RENAME = "rename"
STATUS_UNCHANGED = "unchanged"
STATUS_MISSING_TAGS = "missing tags"
STATUS_CONFLICT = "conflict"
STATUS_REFUSED = "refused"

PROTECTED_FOLDERS = frozenset(
    {"_serato_", "_serato_backup", "pioneer", "rekordbox", "_traktor", "native instruments"}
)
"""Folder names (case-insensitive) holding a DJ software's own library: a
file anywhere below one is never renamed."""

def QT_TRANSLATE_NOOP(context: str, text: str) -> str:
    """Marks `text` for the interface translations (issue #306) without
    importing Qt here: pyside6-lupdate finds it by this name, and the dialog
    translates it with QCoreApplication.translate(context, text)."""
    return text


RELINK_WARNING = QT_TRANSLATE_NOOP(
    "RenameFilesDialog",
    "Serato, Traktor and Rekordbox remember each track by its full path: renamed files will show "
    "as missing there until you relink them (their libraries are not modified by this app). "
    "Keep the old → new CSV to find each file again.",
)

CSV_HEADER = ("old_path", "new_path")

# Characters no file name may hold on macOS/Windows (plus control characters).
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
# Room left for the extension under the common 255-byte name limit.
_MAX_STEM_BYTES = 240


class TemplateError(ValueError):
    """A template that can't name a file (unknown field, stray brace, …)."""


@dataclass(frozen=True)
class RenameSource:
    """One track to rename, as the library table knows it."""

    track_id: int
    path: str
    metadata: TrackMetadata | None
    missing: bool = False


@dataclass(frozen=True)
class RenameItem:
    track_id: int
    old_path: str
    new_path: str | None
    status: str
    reason: str = ""

    @property
    def will_rename(self) -> bool:
        return self.status == STATUS_RENAME


@dataclass(frozen=True)
class RenamePlan:
    template: str
    items: tuple[RenameItem, ...]

    @property
    def renames(self) -> list[tuple[str, str]]:
        """``(old path, new path)`` of every track that will be renamed."""
        return [(item.old_path, item.new_path) for item in self.items if item.will_rename and item.new_path]

    def count(self, status: str) -> int:
        return sum(1 for item in self.items if item.status == status)


@dataclass
class RenameResult:
    renamed: list[tuple[str, str]] = field(default_factory=list)
    """``(old path, new path)`` actually renamed, in order."""
    failed: list[tuple[str, str]] = field(default_factory=list)
    """``(path, reason)`` left as it was."""


def parse_template(template: str) -> list[str]:
    """The fields `template` uses, in order; raises `TemplateError` when it
    is empty, holds a path separator or a stray brace, or names an unknown
    field."""
    if not template.strip():
        raise TemplateError("The template is empty.")
    if "/" in template or "\\" in template:
        raise TemplateError("The template can't contain / or \\ -- files are renamed inside their own folder.")
    names = _PLACEHOLDER.findall(template)
    leftover = _PLACEHOLDER.sub("", template)
    if "{" in leftover or "}" in leftover:
        raise TemplateError("Unbalanced { } in the template.")
    if not names:
        raise TemplateError("The template uses no field, e.g. {artist} or {title}.")
    unknown = [name for name in names if name.strip().lower() not in TEMPLATE_FIELDS]
    if unknown:
        raise TemplateError(f"Unknown field {{{unknown[0]}}}; use one of " + ", ".join(f"{{{f}}}" for f in TEMPLATE_FIELDS))
    return [name.strip().lower() for name in names]


def _format_bpm(bpm: float) -> str:
    return str(int(bpm)) if float(bpm).is_integer() else f"{bpm:.1f}"


def field_values(path: str, metadata: TrackMetadata | None) -> dict[str, str | None]:
    """Every template field's text for one track (None when untagged)."""
    metadata = metadata or TrackMetadata()

    def text(value: object) -> str | None:
        value = str(value).strip() if value is not None else ""
        return value or None

    return {
        "artist": text(metadata.artist),
        "title": text(metadata.title),
        "album": text(metadata.album),
        "genre": text(metadata.genre),
        "bpm": _format_bpm(metadata.bpm) if metadata.bpm else None,
        "key": text(metadata.key),
        "camelot": to_camelot(metadata.key) if metadata.key else None,
        "filename": Path(path).stem,
    }


def sanitize(text: str) -> str:
    """`text` made safe as one file name component: unsafe characters
    become ``_``, whitespace collapses, and leading/trailing spaces and dots
    go (a leading dot would hide the file)."""
    text = " ".join(text.split())
    text = _UNSAFE.sub("_", text)
    return text.strip(" .")


def _truncate(stem: str) -> str:
    encoded = stem.encode("utf-8")
    if len(encoded) <= _MAX_STEM_BYTES:
        return stem
    return encoded[:_MAX_STEM_BYTES].decode("utf-8", errors="ignore").rstrip(" .")


def render_stem(template: str, values: dict[str, str | None]) -> tuple[str | None, list[str]]:
    """The new file name (without extension) and the fields it lacks.

    Returns ``(None, missing)`` when a field is untagged, or ``(None, [])``
    when the result would be empty."""
    names = parse_template(template)
    missing = [name for name in dict.fromkeys(names) if not values.get(name)]
    if missing:
        return None, missing
    stem = _PLACEHOLDER.sub(lambda match: sanitize(values[match.group(1).strip().lower()] or ""), template)
    stem = _truncate(sanitize(stem))
    return (stem or None), []


def _real(path: str | Path) -> str:
    return os.path.realpath(os.fspath(path))


def is_within_roots(path: str | Path, roots: Iterable[str | Path]) -> bool:
    """True when `path` lies strictly below one of `roots` (symlinks resolved)."""
    real = Path(_real(path))
    return any(real != Path(_real(root)) and real.is_relative_to(_real(root)) for root in roots)


def in_protected_folder(path: str | Path) -> bool:
    """True when a folder of `path` is a DJ software library folder."""
    return any(part.casefold() in PROTECTED_FOLDERS for part in Path(path).parent.parts)


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def plan_renames(
    sources: Iterable[RenameSource],
    template: str,
    roots: Iterable[str | Path],
    indexed_paths: Iterable[str] = (),
) -> RenamePlan:
    """The preview of renaming `sources` with `template`; see the module
    docstring for the rules. Raises `TemplateError` for a bad template.
    Reads the disk (existence checks) but never changes it."""
    parse_template(template)
    roots = list(roots)
    indexed = {path.casefold() for path in indexed_paths}
    drafts: list[RenameItem] = []
    for source in sources:
        old = str(source.path)

        def item(
            status: str, reason: str = "", new: str | None = None, old: str = old, track_id: int = source.track_id
        ) -> RenameItem:
            return RenameItem(track_id, old, new, status, reason)

        if source.missing or not Path(old).is_file():
            drafts.append(item(STATUS_REFUSED, "file not found"))
            continue
        if in_protected_folder(old):
            drafts.append(item(STATUS_REFUSED, "inside a DJ software folder"))
            continue
        if not is_within_roots(old, roots):
            drafts.append(item(STATUS_REFUSED, "outside the library folders"))
            continue
        stem, missing = render_stem(template, field_values(old, source.metadata))
        if stem is None:
            reason = "no " + ", ".join(missing) + " tag" if missing else "the new name would be empty"
            drafts.append(item(STATUS_MISSING_TAGS, reason))
            continue
        new = str(Path(old).with_name(stem + Path(old).suffix))
        if new == old:
            drafts.append(item(STATUS_UNCHANGED, "already named this way", new))
            continue
        drafts.append(item(STATUS_RENAME, "", new))

    # Two tracks of the batch landing on one name (case-insensitively, as
    # on a default macOS/Windows disk) both stay as they are.
    targets = Counter(draft.new_path.casefold() for draft in drafts if draft.will_rename and draft.new_path)
    items: list[RenameItem] = []
    for draft in drafts:
        if not draft.will_rename or draft.new_path is None:
            items.append(draft)
            continue
        new, old = draft.new_path, draft.old_path
        reason = ""
        if targets[new.casefold()] > 1:
            reason = f"{targets[new.casefold()] - 1} other selected track(s) get the same name"
        elif os.path.lexists(new) and not _same_file(old, new):
            reason = "a file with this name already exists"
        elif new.casefold() in indexed and new.casefold() != old.casefold():
            reason = "this name is already in the library index"
        if reason:
            items.append(RenameItem(draft.track_id, old, new, STATUS_CONFLICT, reason))
        else:
            items.append(draft)
    return RenamePlan(template=template, items=tuple(items))


def plan_from_db(db: LibraryDB, paths: Iterable[str], template: str) -> RenamePlan:
    """`plan_renames` for the indexed tracks at `paths`, from the cached
    tags and the configured roots (a path not indexed is left out)."""
    wanted = list(dict.fromkeys(str(path) for path in paths))
    by_path = {record.path: (record, metadata) for record, metadata in db.list_tracks_with_metadata()}
    sources = [
        RenameSource(by_path[path][0].id, path, by_path[path][1], by_path[path][0].missing)
        for path in wanted
        if path in by_path
    ]
    return plan_renames(sources, template, [root.path for root in db.list_roots()], by_path)


def apply_renames(
    db: LibraryDB,
    pairs: Iterable[tuple[str, str]],
    rename: Callable[[str, str], None] = os.rename,
) -> RenameResult:
    """Rename each ``(old, new)`` file, then point the index at the new
    paths (`LibraryDB.rename_track_paths`). Each pair is re-checked first --
    `old` still a file, `new` in the same folder, free, outside any DJ
    software folder -- and a pair failing a check or the rename itself is
    reported in `failed` while the others still go. Undoing a batch is the
    same call with every renamed pair swapped."""
    result = RenameResult()
    for old, new in pairs:
        old, new = str(old), str(new)
        if Path(old).parent != Path(new).parent:
            result.failed.append((old, "a file is only renamed inside its own folder"))
            continue
        if in_protected_folder(old):
            result.failed.append((old, "inside a DJ software folder"))
            continue
        if not Path(old).is_file():
            result.failed.append((old, "file not found"))
            continue
        if os.path.lexists(new) and not _same_file(old, new):
            result.failed.append((old, f"{Path(new).name} already exists"))
            continue
        try:
            rename(old, new)
        except OSError as exc:
            result.failed.append((old, str(exc)))
            continue
        result.renamed.append((old, new))
    db.rename_track_paths(result.renamed)
    return result


def write_mapping_csv(handle: TextIO, pairs: Iterable[tuple[str, str]]) -> int:
    """Write ``old_path,new_path`` rows; returns how many were written."""
    writer = csv.writer(handle)
    writer.writerow(CSV_HEADER)
    count = 0
    for old, new in pairs:
        writer.writerow((old, new))
        count += 1
    return count


def mapping_to_csv(pairs: Iterable[tuple[str, str]]) -> str:
    buffer = io.StringIO()
    write_mapping_csv(buffer, pairs)
    return buffer.getvalue()


def export_mapping_csv(path: str | Path, pairs: Iterable[tuple[str, str]]) -> int:
    """Write the CSV to `path` (UTF-8 with BOM so spreadsheet apps detect it)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        return write_mapping_csv(handle, pairs)


__all__ = [
    "CSV_HEADER",
    "DEFAULT_TEMPLATE",
    "PROTECTED_FOLDERS",
    "RELINK_WARNING",
    "STATUS_CONFLICT",
    "STATUS_MISSING_TAGS",
    "STATUS_REFUSED",
    "STATUS_RENAME",
    "STATUS_UNCHANGED",
    "TEMPLATE_FIELDS",
    "RenameItem",
    "RenamePlan",
    "RenameResult",
    "RenameSource",
    "TemplateError",
    "apply_renames",
    "export_mapping_csv",
    "field_values",
    "in_protected_folder",
    "is_within_roots",
    "mapping_to_csv",
    "parse_template",
    "plan_from_db",
    "plan_renames",
    "render_stem",
    "sanitize",
    "write_mapping_csv",
]
