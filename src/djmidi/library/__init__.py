from __future__ import annotations

from .analysis import estimate_bpm, estimate_key, resolve_bpm_key, to_camelot
from .db import LibraryDB, LibraryRoot, TrackRecord
from .metadata import (
    MANAGED_FIELDS,
    TrackMetadata,
    clean_noise_frames,
    read_metadata,
    write_metadata,
)
from .playlist import (
    PlaylistTrack,
    build_playlist_draft,
    compatibility_score,
    find_compatible_tracks,
    is_bpm_compatible,
    is_camelot_compatible,
)
from .rekordbox_library import (
    RekordboxPlaylist,
    RekordboxTrack,
    parse_export,
)
from .rekordbox_library import parse_playlists as parse_rekordbox_playlists
from .scanner import AUDIO_EXTENSIONS, ScanResult, iter_audio_files, scan_root
from .traktor_library import NmlTrack, parse_collection
from .traktor_library import parse_playlists as parse_traktor_playlists

__all__ = [
    "AUDIO_EXTENSIONS",
    "MANAGED_FIELDS",
    "LibraryDB",
    "LibraryRoot",
    "NmlTrack",
    "PlaylistTrack",
    "RekordboxPlaylist",
    "RekordboxTrack",
    "ScanResult",
    "TrackMetadata",
    "TrackRecord",
    "build_playlist_draft",
    "clean_noise_frames",
    "compatibility_score",
    "estimate_bpm",
    "estimate_key",
    "find_compatible_tracks",
    "is_bpm_compatible",
    "is_camelot_compatible",
    "iter_audio_files",
    "parse_collection",
    "parse_export",
    "parse_rekordbox_playlists",
    "parse_traktor_playlists",
    "read_metadata",
    "resolve_bpm_key",
    "scan_root",
    "to_camelot",
    "write_metadata",
]
