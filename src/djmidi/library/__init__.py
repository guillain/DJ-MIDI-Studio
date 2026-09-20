from __future__ import annotations

from .db import LibraryDB, LibraryRoot, TrackRecord
from .metadata import (
    MANAGED_FIELDS,
    TrackMetadata,
    clean_noise_frames,
    read_metadata,
    write_metadata,
)
from .scanner import AUDIO_EXTENSIONS, ScanResult, iter_audio_files, scan_root

__all__ = [
    "AUDIO_EXTENSIONS",
    "MANAGED_FIELDS",
    "LibraryDB",
    "LibraryRoot",
    "ScanResult",
    "TrackMetadata",
    "TrackRecord",
    "clean_noise_frames",
    "iter_audio_files",
    "read_metadata",
    "scan_root",
    "write_metadata",
]
