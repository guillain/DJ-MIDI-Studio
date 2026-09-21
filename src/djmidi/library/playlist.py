from __future__ import annotations

import re
from dataclasses import dataclass

_CAMELOT_RE = re.compile(r"^(1[0-2]|[1-9])([AB])$", re.IGNORECASE)


@dataclass(frozen=True)
class PlaylistTrack:
    """The minimal, decoupled view this engine needs of a track.

    Deliberately not tied to LibraryDB or to catalog/#127's taxonomy
    Category or #128's analysis module: the caller resolves those and
    passes plain values here, so this module builds against today's main
    without depending on #127/#129 merging first.
    """

    identifier: str
    category: str | None = None
    bpm: float | None = None
    camelot_key: str | None = None


def _parse_camelot(key: str) -> tuple[int, str] | None:
    match = _CAMELOT_RE.match(key.strip())
    if match is None:
        return None
    return int(match.group(1)), match.group(2).upper()


def is_camelot_compatible(key_a: str, key_b: str) -> bool:
    """Same key, +/-1 on the wheel (energy change), or same number/other
    letter (relative major/minor) -- the standard harmonic-mixing rule."""
    parsed_a = _parse_camelot(key_a)
    parsed_b = _parse_camelot(key_b)
    if parsed_a is None or parsed_b is None:
        return False
    number_a, letter_a = parsed_a
    number_b, letter_b = parsed_b
    if number_a == number_b:
        return True
    if letter_a == letter_b:
        diff = (number_a - number_b) % 12
        return diff in (1, 11)
    return False


def is_bpm_compatible(bpm_a: float, bpm_b: float, tolerance_pct: float = 6.0) -> bool:
    if bpm_a <= 0 or bpm_b <= 0:
        return False
    tolerance = max(bpm_a, bpm_b) * (tolerance_pct / 100.0)
    return abs(bpm_a - bpm_b) <= tolerance


def compatibility_score(
    seed: PlaylistTrack,
    candidate: PlaylistTrack,
    bpm_tolerance_pct: float = 6.0,
    same_category_only: bool = False,
) -> float | None:
    """Lower is closer. None means incompatible (filtered out by the caller)."""
    if same_category_only and seed.category is not None and seed.category != candidate.category:
        return None
    if seed.bpm is None or candidate.bpm is None:
        return None
    if not is_bpm_compatible(seed.bpm, candidate.bpm, bpm_tolerance_pct):
        return None
    if (
        seed.camelot_key is not None
        and candidate.camelot_key is not None
        and not is_camelot_compatible(seed.camelot_key, candidate.camelot_key)
    ):
        return None
    return abs(seed.bpm - candidate.bpm)


def find_compatible_tracks(
    seed: PlaylistTrack,
    candidates: list[PlaylistTrack],
    bpm_tolerance_pct: float = 6.0,
    same_category_only: bool = False,
) -> list[PlaylistTrack]:
    """The "simple filter+sort" mode from issue #131: candidates compatible
    with `seed`, closest BPM first. Never includes `seed` itself."""
    scored = []
    for candidate in candidates:
        if candidate.identifier == seed.identifier:
            continue
        score = compatibility_score(seed, candidate, bpm_tolerance_pct, same_category_only)
        if score is not None:
            scored.append((score, candidate))
    scored.sort(key=lambda pair: pair[0])
    return [candidate for _, candidate in scored]


def bpm_bucket(bpm: float, width: float = 4.0) -> float:
    """The lower bound of the `width`-BPM-wide bucket `bpm` falls into,
    used to group close-but-not-identical BPMs together (e.g. 143.8 and
    145.2 land in the same bucket at width=4)."""
    return (bpm // width) * width


def build_playlist_draft(tracks: list[PlaylistTrack], bpm_bucket_width: float = 4.0) -> list[PlaylistTrack]:
    """Default ordering confirmed by the maintainer for issue #131: grouped
    by category, then by BPM range, then sorted by (Camelot) key within
    that range. Tracks with no category/bpm sort last within their group,
    rather than being dropped."""

    def sort_key(track: PlaylistTrack) -> tuple[object, ...]:
        category_key = (track.category is None, track.category or "")
        bpm_key = (track.bpm is None, bpm_bucket(track.bpm, bpm_bucket_width) if track.bpm is not None else 0.0)
        key_key = (track.camelot_key is None, track.camelot_key or "")
        return (*category_key, *bpm_key, *key_key)

    return sorted(tracks, key=sort_key)
