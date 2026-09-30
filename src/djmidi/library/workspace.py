"""Qt-free glue between the library index and the Music Library tab (#132).

Everything the tab needs beyond raw widgets lives here so it stays testable
without a `QApplication`: the consolidated per-track view (cached tags +
Camelot key + taxonomy category), step-wise metadata refresh for a
`QTimer`-driven GUI, persistence of taxonomy edits, and playlist
import/export path handling for Serato/Traktor/Rekordbox.

Standing rule of this initiative: nothing here writes to a DJ software's own
library or playlist files. Imports only read them; exports only ever write a
brand-new file at a path the caller passes.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from djmidi import taxonomy
from djmidi.taxonomy import Category

from .analysis import to_camelot
from .db import LibraryDB, StoredCategory, TrackRecord
from .metadata import TrackMetadata, read_metadata
from .playlist import PlaylistTrack, build_playlist_draft, find_compatible_tracks
from .rekordbox_library import parse_export
from .rekordbox_library import parse_playlists as parse_rekordbox_playlists
from .serato_library import parse_crate, write_crate_file
from .traktor_library import parse_playlists as parse_traktor_playlists

_LOGGER = logging.getLogger(__name__)

_METADATA_COMMIT_EVERY = 200

# Playlist `source` values recorded in LibraryDB.
SOURCE_MANUAL = "manual"
SOURCE_GENERATED = "generated"
SOURCE_SERATO = "serato"
SOURCE_TRAKTOR = "traktor"
SOURCE_REKORDBOX = "rekordbox"


# --- consolidated view --------------------------------------------------


@dataclass(frozen=True)
class LibraryRow:
    """One track as the Music Library table shows it."""

    track_id: int
    path: str
    missing: bool
    metadata: TrackMetadata | None
    camelot_key: str | None
    category: str | None
    """Canonical `Family%%Name` of an exact/alias taxonomy match only."""
    category_suggestion: str | None = None
    """Canonical name of a *fuzzy* match -- shown, never auto-applied."""

    @property
    def title(self) -> str | None:
        return self.metadata.title if self.metadata else None

    @property
    def bpm(self) -> float | None:
        return self.metadata.bpm if self.metadata else None


def folder_hint(track_path: str, root_path: str | None) -> str | None:
    """The track's folder relative to its library root, `/`-joined (e.g.
    ``Tek/PsyTrance/Album``) -- the hand-curated hierarchy
    `taxonomy.resolve_category` weighs over the raw genre tag."""
    parent = Path(track_path).parent
    if root_path:
        try:
            relative = parent.relative_to(root_path)
        except ValueError:
            relative = None
        if relative is not None:
            return relative.as_posix() if relative.parts else None
    return parent.name or None


def crate_hints(db: LibraryDB) -> dict[str, str]:
    """Track path -> name of the first imported Serato crate listing it."""
    hints: dict[str, str] = {}
    for playlist in db.list_playlists():
        if playlist.source != SOURCE_SERATO:
            continue
        for path in db.playlist_paths(playlist.id):
            hints.setdefault(path, playlist.name)
    return hints


def consolidate(db: LibraryDB) -> list[LibraryRow]:
    roots = {root.id: root.path for root in db.list_roots()}
    crates = crate_hints(db)
    resolved: dict[tuple[str | None, str | None, str | None], taxonomy.CategoryMatch] = {}
    rows: list[LibraryRow] = []
    for record, metadata in db.list_tracks_with_metadata():
        genre = metadata.genre if metadata else None
        hints = (genre, folder_hint(record.path, roots.get(record.root_id)), crates.get(record.path))
        match = resolved.get(hints)
        if match is None:
            match = taxonomy.resolve_category(hints[0], folder_hint=hints[1], crate_hint=hints[2])
            resolved[hints] = match
        canonical = match.category.canonical if match.category is not None else None
        confident = match.confidence in ("exact", "alias")
        rows.append(
            LibraryRow(
                track_id=record.id,
                path=record.path,
                missing=record.missing,
                metadata=metadata,
                camelot_key=to_camelot(metadata.key) if metadata else None,
                category=canonical if confident else None,
                category_suggestion=canonical if match.confidence == "fuzzy" else None,
            )
        )
    return rows


def iter_refresh_metadata(db: LibraryDB) -> Generator[int, None, int]:
    """Read tags for every present track whose cache is missing or stale,
    yielding the running count; returns the total refreshed.

    A file mutagen can't parse (or that vanished mid-run) caches as empty
    metadata rather than aborting the whole refresh."""
    count = 0
    for record in db.tracks_needing_metadata():
        db.set_cached_metadata(record.id, record.mtime, _safe_read(record))
        count += 1
        if count % _METADATA_COMMIT_EVERY == 0:
            db.commit()
        yield count
    db.commit()
    return count


def _safe_read(record: TrackRecord) -> TrackMetadata:
    try:
        return read_metadata(record.path) or TrackMetadata()
    except Exception:
        _LOGGER.warning("Could not read tags from %s", record.path, exc_info=True)
        return TrackMetadata()


def refresh_track_metadata(db: LibraryDB, track_path: str) -> None:
    """Re-read one track right after this app wrote its tags."""
    record = db.get_track_by_path(track_path)
    if record is None:
        return
    stat = Path(track_path).stat()
    db.upsert_track(record.root_id, track_path, stat.st_size, stat.st_mtime)
    db.set_cached_metadata(record.id, stat.st_mtime, _safe_read(record))
    db.commit()


# --- taxonomy persistence ----------------------------------------------


def _stored(category: Category) -> StoredCategory:
    return StoredCategory(family=category.family, name=category.name, aliases=tuple(sorted(category.aliases)))


def load_taxonomy_overrides(db: LibraryDB) -> None:
    """Replay the user's saved category edits on top of the built-in
    families. Safe to call repeatedly."""
    saved, removed = db.category_overrides()
    for canonical in removed:
        taxonomy.unregister(canonical)
    for stored in saved:
        taxonomy.register(Category(stored.family, stored.name, frozenset(stored.aliases)), replace=True)


def create_category(db: LibraryDB, family: str, name: str, aliases: Iterable[str] = ()) -> Category:
    family, name = family.strip(), name.strip()
    if not family or not name:
        raise ValueError("A category needs both a family and a name")
    category = Category(family, name, frozenset(a.strip() for a in aliases if a.strip()))
    taxonomy.register(category)
    db.save_category(_stored(category))
    return category


def add_category_alias(db: LibraryDB, canonical: str, alias: str) -> Category:
    alias = alias.strip()
    if not alias:
        raise ValueError("An alias can't be empty")
    category = taxonomy.add_alias(canonical, alias)
    db.save_category(_stored(category))
    return category


def rename_category(db: LibraryDB, canonical: str, new_name: str) -> Category:
    """Renames in place, keeping the old name as an alias so tracks already
    tagged/filed under it still resolve."""
    old = taxonomy.get_category(canonical)
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("A category name can't be empty")
    if new_name == old.name:
        return old
    renamed = Category(old.family, new_name, old.aliases | {old.name})
    taxonomy.register(renamed)
    taxonomy.unregister(canonical)
    db.save_category(_stored(renamed))
    db.remove_category(canonical)
    return renamed


def merge_categories(db: LibraryDB, keep: str, absorb: str) -> Category:
    if keep == absorb:
        raise ValueError("Pick two different categories to merge")
    merged = taxonomy.merge_categories(keep, absorb)
    db.save_category(_stored(merged))
    db.remove_category(absorb)
    return merged


def delete_category(db: LibraryDB, canonical: str) -> None:
    taxonomy.get_category(canonical)
    taxonomy.unregister(canonical)
    db.remove_category(canonical)


# --- playlists -----------------------------------------------------------


def to_playlist_tracks(rows: Iterable[LibraryRow]) -> list[PlaylistTrack]:
    return [
        PlaylistTrack(identifier=row.path, category=row.category, bpm=row.bpm, camelot_key=row.camelot_key)
        for row in rows
    ]


def generate_playlist(
    rows: list[LibraryRow],
    seed_path: str | None = None,
    bpm_tolerance_pct: float = 6.0,
    same_category_only: bool = False,
) -> list[str]:
    """Issue #131's simple mode: with a seed, the seed followed by its
    compatible tracks (closest BPM first); without one, `rows` in the
    maintainer's default category -> BPM range -> key order."""
    tracks = to_playlist_tracks(row for row in rows if not row.missing)
    if seed_path is None:
        return [track.identifier for track in build_playlist_draft(tracks)]
    seed = next((track for track in tracks if track.identifier == seed_path), None)
    if seed is None:
        raise ValueError(f"Seed track is not in the candidate list: {seed_path}")
    compatible = find_compatible_tracks(seed, tracks, bpm_tolerance_pct, same_category_only)
    return [seed.identifier, *(track.identifier for track in compatible)]


def volume_root(path: str | os.PathLike[str]) -> Path:
    """The volume a path lives on: ``/Volumes/<name>`` for an external macOS
    drive, else the path's anchor (``/``, or ``C:\\`` on Windows)."""
    path = Path(path)
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "Volumes":
        return Path("/", "Volumes", parts[2])
    return Path(path.anchor or "/")


def read_serato_crate(crate_path: str | os.PathLike[str]) -> list[str]:
    """A crate's tracks as absolute paths. Serato stores them relative to
    the root of the volume the crate itself lives on."""
    root = volume_root(Path(crate_path).resolve())
    paths = []
    for stored in parse_crate(crate_path):
        candidate = Path(stored)
        paths.append(str(candidate if candidate.is_absolute() else root / PurePosixPath(stored)))
    return paths


def export_serato_crate(crate_path: str | os.PathLike[str], track_paths: Iterable[str]) -> None:
    """Writes a new crate at exactly `crate_path`, storing each track
    relative to that crate's volume root the way Serato does."""
    root = volume_root(Path(crate_path).resolve().parent)
    stored = []
    for track_path in track_paths:
        path = Path(track_path)
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = path.relative_to(path.anchor) if path.anchor else path
        stored.append(relative.as_posix())
    write_crate_file(crate_path, stored)


def traktor_key_to_path(key: str) -> str:
    """Turns a Traktor playlist `PRIMARYKEY` (``VOLUME/:DIR/:FILE``) into a
    filesystem path. Prefers ``/Volumes/<VOLUME>/...`` when that exists (an
    external drive; on macOS the boot volume is a symlink there too, so
    `realpath` folds it back to ``/...``), else assumes the boot volume."""
    separator = key.find("/:")
    if separator < 0:
        return key
    volume, rest = key[:separator], key[separator:].replace("/:", "/")
    if volume:
        candidate = Path("/Volumes", volume, rest.lstrip("/"))
        if candidate.exists():
            return os.path.realpath(candidate)
    return rest


def read_traktor_playlists(nml_path: str | os.PathLike[str]) -> dict[str, list[str]]:
    return {
        name: [traktor_key_to_path(key) for key in keys] for name, keys in parse_traktor_playlists(nml_path).items()
    }


def read_rekordbox_playlists(pdb_path: str | os.PathLike[str]) -> dict[str, list[str]]:
    """Playlists of a Rekordbox device export. Track paths in `export.pdb`
    are relative to the device root, i.e. the folder holding ``PIONEER/``."""
    pdb_path = Path(pdb_path)
    device_root = pdb_path.parent
    if device_root.name.lower() == "rekordbox" and device_root.parent.name.upper() == "PIONEER":
        device_root = device_root.parent.parent
    tracks = {track.id: track for track in parse_export(pdb_path)}
    playlists: dict[str, list[str]] = {}
    for playlist in parse_rekordbox_playlists(pdb_path):
        if playlist.is_folder:
            continue
        paths = []
        for track_id in playlist.track_ids:
            track = tracks.get(track_id)
            if track is not None and track.file_path:
                paths.append(str(device_root / track.file_path.lstrip("/")))
        playlists[playlist.name] = paths
    return playlists
