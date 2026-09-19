from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .db import LibraryDB

# Scope matches the real files found in the maintainer's own collection
# (issue #125): standard DJ-relevant audio formats only.
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".aiff", ".aif", ".flac", ".m4a", ".ogg", ".aac"})

# macOS AppleDouble sidecar files (e.g. "._track.mp3") and Finder metadata --
# never real audio, seen throughout the maintainer's real library.
_SKIP_FILE_PREFIXES = ("._",)
_SKIP_FILENAMES = frozenset({".DS_Store"})


def iter_audio_files(root: Path) -> Iterator[Path]:
    """Yield every real audio file under `root`, read-only.

    Skips hidden directories (e.g. `.Trash`, `.fseventsd`) and macOS
    AppleDouble sidecar files, neither of which are real tracks.
    """
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts[:-1]):
            continue
        name = path.name
        if name in _SKIP_FILENAMES or name.startswith(_SKIP_FILE_PREFIXES):
            continue
        if path.suffix.lower() in AUDIO_EXTENSIONS:
            yield path


@dataclass
class ScanResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0


def scan_root(
    root_path: str | Path,
    db: LibraryDB,
    progress_callback: Callable[[int], None] | None = None,
) -> ScanResult:
    """Incrementally index every audio file under `root_path` into `db`.

    Read-only against the filesystem: only path/size/mtime are recorded, the
    file content is never opened. A file already indexed with an unchanged
    size and mtime is skipped rather than re-touched.
    """
    root_path = Path(root_path)
    root = db.add_root(root_path)
    result = ScanResult()
    seen_paths: list[str] = []
    for count, file_path in enumerate(iter_audio_files(root_path), start=1):
        path_str = str(file_path)
        seen_paths.append(path_str)
        stat = file_path.stat()
        existing = db.get_track_by_path(path_str)
        if existing is None:
            result.added += 1
        elif existing.missing or existing.size != stat.st_size or existing.mtime != stat.st_mtime:
            result.updated += 1
        else:
            result.unchanged += 1
        db.upsert_track(root.id, path_str, stat.st_size, stat.st_mtime)
        if progress_callback is not None:
            progress_callback(count)
    db.commit()
    result.missing = db.mark_missing_except(root.id, seen_paths)
    return result
