"""Relink missing library tracks (issue #190).

A scan never deletes a row: a file that moved shows up as one `missing`
row plus one new row at its new path. This module finds, for each missing
track, the files it most likely became -- same file name (case-insensitive)
and same size, or failing that the same name only, or the same cached
title + artist -- and `apply_relinks` folds the old row into the new one in
**this app's index only** (`LibraryDB.relink_tracks`). No audio file, tag
or DJ-software library is ever written; the configured roots are only
listed, never opened.

Like `scanner.iter_scan_root`, the search is a generator a GUI can advance a
slice at a time; `find_relink_proposals` drains it for scripted use.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .db import LibraryDB, TrackRecord
from .metadata import TrackMetadata
from .scanner import iter_audio_files

# How each candidate matched, strongest first.
MATCH_EXACT = "name+size"
MATCH_NAME = "name"
MATCH_TAGS = "tags"
_MATCH_RANK = {MATCH_EXACT: 0, MATCH_NAME: 1, MATCH_TAGS: 2}


@dataclass(frozen=True)
class RelinkCandidate:
    path: str
    root_id: int
    size: int
    mtime: float
    match: str
    tags_agree: bool = False
    indexed: bool = True


@dataclass
class RelinkProposal:
    missing: TrackRecord
    candidates: list[RelinkCandidate] = field(default_factory=list)
    confident: bool = False

    @property
    def best(self) -> RelinkCandidate | None:
        return self.candidates[0] if self.candidates else None


@dataclass
class RelinkResult:
    relinked: int = 0
    skipped: list[str] = field(default_factory=list)


def _tag_key(metadata: TrackMetadata | None) -> tuple[str, str] | None:
    if metadata is None or not metadata.title or not metadata.artist:
        return None
    return metadata.title.strip().casefold(), metadata.artist.strip().casefold()


def _root_for(path: str, roots: list[tuple[int, Path]]) -> int | None:
    """The configured root holding `path` (the deepest one, if nested)."""
    best: tuple[int, int] | None = None
    for root_id, root in roots:
        if Path(path).is_relative_to(root) and (best is None or len(root.parts) > best[1]):
            best = (root_id, len(root.parts))
    return best[0] if best else None


def iter_relink_proposals(
    db: LibraryDB, search_roots: bool = True
) -> Generator[int, None, list[RelinkProposal]]:
    """Yield a running count of files looked at; return one proposal per
    missing track, candidates ranked best first.

    Candidates are present indexed tracks and, with `search_roots`, audio
    files under the configured roots that a scan hasn't indexed yet (only
    files whose name matches a missing track are kept). A proposal is
    `confident` when exactly one candidate has the same name and size, and
    no other missing track's confident pick is that same file."""
    entries = db.list_tracks_with_metadata()
    missing = [(record, metadata) for record, metadata in entries if record.missing]
    if not missing:
        return []
    wanted_names = {Path(record.path).name.casefold() for record, _ in missing}

    by_name: dict[str, list[tuple[RelinkCandidate, tuple[str, str] | None]]] = defaultdict(list)
    by_tags: dict[tuple[str, str], list[RelinkCandidate]] = defaultdict(list)
    indexed_paths = {record.path for record, _ in entries}
    count = 0
    for record, metadata in entries:
        if record.missing:
            continue
        candidate = RelinkCandidate(record.path, record.root_id, record.size, record.mtime, MATCH_NAME)
        tags = _tag_key(metadata)
        if tags is not None:
            by_tags[tags].append(candidate)
        name = Path(record.path).name.casefold()
        if name in wanted_names:
            by_name[name].append((candidate, tags))
        count += 1
        if count % 200 == 0:
            yield count

    if search_roots:
        for root in db.list_roots():
            root_path = Path(root.path)
            if not root_path.is_dir():
                continue
            for file_path in iter_audio_files(root_path):
                count += 1
                if count % 200 == 0:
                    yield count
                path_str = str(file_path)
                name = file_path.name.casefold()
                if name not in wanted_names or path_str in indexed_paths:
                    continue
                stat = file_path.stat()
                indexed_paths.add(path_str)
                candidate = RelinkCandidate(path_str, root.id, stat.st_size, stat.st_mtime, MATCH_NAME, indexed=False)
                by_name[name].append((candidate, None))

    proposals: list[RelinkProposal] = []
    for record, metadata in missing:
        tags = _tag_key(metadata)
        found: dict[str, RelinkCandidate] = {}
        for candidate, candidate_tags in by_name.get(Path(record.path).name.casefold(), []):
            match = MATCH_EXACT if candidate.size == record.size else MATCH_NAME
            agree = tags is not None and candidate_tags == tags
            found[candidate.path] = _with(candidate, match, agree)
        for candidate in by_tags.get(tags, []) if tags is not None else []:
            if candidate.path not in found:
                found[candidate.path] = _with(candidate, MATCH_TAGS, True)
        ranked = sorted(found.values(), key=lambda c: (_MATCH_RANK[c.match], not c.tags_agree, c.path))
        exact = [c for c in ranked if c.match == MATCH_EXACT]
        proposals.append(RelinkProposal(missing=record, candidates=ranked, confident=len(exact) == 1))

    # Two missing tracks can't both confidently be the same file.
    claims: dict[str, int] = defaultdict(int)
    for proposal in proposals:
        if proposal.confident:
            claims[proposal.best.path] += 1
    for proposal in proposals:
        if proposal.confident and claims[proposal.best.path] > 1:
            proposal.confident = False
    return proposals


def _with(candidate: RelinkCandidate, match: str, tags_agree: bool) -> RelinkCandidate:
    return RelinkCandidate(
        candidate.path, candidate.root_id, candidate.size, candidate.mtime, match, tags_agree, candidate.indexed
    )


def find_relink_proposals(db: LibraryDB, search_roots: bool = True) -> list[RelinkProposal]:
    steps = iter_relink_proposals(db, search_roots)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def apply_relinks(db: LibraryDB, choices: Iterable[tuple[TrackRecord, RelinkCandidate]]) -> RelinkResult:
    """Relink each missing track to its chosen candidate, in one transaction.

    A candidate file that vanished since the search, or that lies outside
    every configured root, is skipped and reported rather than linked."""
    result = RelinkResult()
    roots = [(root.id, Path(root.path)) for root in db.list_roots()]
    links: list[tuple[int, str, int, int, float]] = []
    for missing, candidate in choices:
        path = Path(candidate.path)
        root_id = _root_for(candidate.path, roots)
        if not path.is_file() or root_id is None:
            result.skipped.append(candidate.path)
            continue
        stat = path.stat()
        links.append((missing.id, candidate.path, root_id, stat.st_size, stat.st_mtime))
    result.relinked = db.relink_tracks(links)
    return result
