from __future__ import annotations

from .db import LibraryDB, LibraryRoot, TrackRecord
from .metadata import (
    MANAGED_FIELDS,
    TrackMetadata,
    clean_noise_frames,
    read_metadata,
    write_metadata,
)
from .rekordbox_library import (
    RekordboxPlaylist,
    RekordboxTrack,
    parse_export,
    parse_playlists,
)
from .scanner import AUDIO_EXTENSIONS, ScanResult, iter_audio_files, scan_root
from .serato_library import (
    iter_chunks,
    parse_crate,
    write_chunk,
    write_chunks,
    write_crate,
    write_crate_file,
)

__all__ = [
    "AUDIO_EXTENSIONS",
    "MANAGED_FIELDS",
    "LibraryDB",
    "LibraryRoot",
    "RekordboxPlaylist",
    "RekordboxTrack",
    "ScanResult",
    "TrackMetadata",
    "TrackRecord",
    "clean_noise_frames",
    "iter_audio_files",
    "iter_chunks",
    "parse_crate",
    "parse_export",
    "parse_playlists",
    "read_metadata",
    "scan_root",
    "write_chunk",
    "write_chunks",
    "write_crate",
    "write_crate_file",
    "write_metadata",
]
