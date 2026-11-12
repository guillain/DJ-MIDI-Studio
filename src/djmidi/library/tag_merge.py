"""Merge a duplicate group onto the copy kept (issue #458).

Two steps, both proposed and confirmed by the DJ, neither discards a file:

- **Tags**: per managed field, what the kept copy has and what the other
  copies offer. An empty field of the kept copy takes the value the other
  copies agree on most (ticked by default); a filled field stays as it is,
  the other copies' different values listed as alternatives the DJ may pick
  (never by default: the kept copy's own tags, edits included, win). The
  result is a `change_log.TagChanges` entry written through the Music
  Library's undoable tag write: only `MANAGED_FIELDS`, frame-level, Serato
  and Traktor frames untouched, logged and revertible.
- **Playlists**: this app's playlists and the set preparation draft list the
  kept copy instead of the others, each track once. DJ software playlists
  are not touched here.

Qt-free.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from djmidi.library.db import LibraryDB
from djmidi.library.metadata import TrackMetadata

# The managed fields, in the order the Music Library shows them.
MERGE_FIELDS = ("artist", "title", "album", "genre", "bpm", "key", "energy", "rating", "comment")


def _empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


@dataclass(frozen=True)
class FieldProposal:
    field: str
    current: object  # the kept copy's value (None when empty)
    proposed: object  # the value to write when chosen
    alternatives: tuple[object, ...]  # every distinct value of the other copies
    chosen: bool  # ticked by default: only when the kept copy's field is empty


def propose_tag_merge(kept: TrackMetadata | None, others: Sequence[TrackMetadata | None]) -> list[FieldProposal]:
    """One proposal per field another copy has a value for that the kept
    copy doesn't share."""
    kept = kept or TrackMetadata()
    proposals = []
    for field in MERGE_FIELDS:
        current = getattr(kept, field)
        values = [getattr(other, field) for other in others if other is not None]
        values = [value for value in values if not _empty(value)]
        distinct = tuple(dict.fromkeys(value for value in values if value != current))
        if not distinct:
            continue
        if _empty(current):
            counts = Counter(values)
            best = max(dict.fromkeys(values), key=lambda value: counts[value])  # ties: first seen
            proposals.append(FieldProposal(field, None, best, distinct, True))
        else:
            proposals.append(FieldProposal(field, current, distinct[0], distinct, False))
    return proposals


def merge_changes(
    kept_path: str, proposals: Iterable[FieldProposal], choices: Mapping[str, object] | None = None
) -> dict[str, tuple[dict[str, object], dict[str, object]]]:
    """The tag write for the kept copy: the chosen proposals, ``choices``
    (field -> value) overriding them. Empty when nothing changes."""
    old: dict[str, object] = {}
    new: dict[str, object] = {}
    for proposal in proposals:
        if choices is not None:
            if proposal.field not in choices:
                continue
            value = choices[proposal.field]
        elif proposal.chosen:
            value = proposal.proposed
        else:
            continue
        if value == proposal.current:
            continue
        old[proposal.field] = proposal.current
        new[proposal.field] = value
    return {kept_path: (old, new)} if new else {}


@dataclass(frozen=True)
class RepointPreview:
    playlists: dict[str, int]  # playlist name -> entries replaced
    set_draft: int  # entries replaced in the set preparation draft


def _replace(paths: Sequence[str], kept_for: Mapping[str, str]) -> tuple[list[str], int]:
    kept_paths = set(kept_for.values())
    result: list[str] = []
    seen: set[str] = set()
    replaced = 0
    for path in paths:
        target = kept_for.get(path, path)
        replaced += target != path
        if target in kept_paths and target in seen:
            continue  # the kept copy is listed already: each track once
        seen.add(target)
        result.append(target)
    return result, replaced


def repoint_to_kept(db: LibraryDB, pairs: Iterable[tuple[str, str]], apply: bool = True) -> RepointPreview:
    """Replaces each dropped copy by its kept copy in this app's playlists
    and the set preparation draft (``pairs``: dropped path, kept path).
    With ``apply=False`` only says what would change."""
    from djmidi.library import set_prep

    kept_for = {dropped: kept for dropped, kept in pairs if dropped != kept}
    playlists: dict[str, int] = {}
    if not kept_for:
        return RepointPreview({}, 0)
    for playlist in db.list_playlists():
        paths = db.playlist_paths(playlist.id)
        merged, replaced = _replace(paths, kept_for)
        if replaced:
            playlists[playlist.name] = playlists.get(playlist.name, 0) + replaced
            if apply:
                db.set_playlist_paths(playlist.id, merged)
    draft = set_prep.load_set_draft(db)
    merged, replaced = _replace(list(draft.paths), kept_for)
    if replaced and apply:
        set_prep.save_set_draft(db, set_prep.SetDraft(tuple(merged), draft.bpm_tolerance_pct))
    return RepointPreview(playlists, replaced)


__all__ = [
    "MERGE_FIELDS",
    "FieldProposal",
    "RepointPreview",
    "merge_changes",
    "propose_tag_merge",
    "repoint_to_kept",
]
