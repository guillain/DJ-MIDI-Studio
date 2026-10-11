from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
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


# --- "path" mode (issue #191) ---------------------------------------------
#
# Issue #131's follow-up: order a draft as a path, where every adjacent pair
# is BPM- and Camelot-compatible and the BPM moves in a chosen direction.
# A full-length beam search would copy a "used" set per beam state per step
# (quadratic in the collection size), so this is a receding-horizon beam
# search instead: at each step a small beam (`beam_width` states,
# `lookahead` moves deep) scores the possible continuations, and only the
# first move of the best one is committed. Candidates come from an index of
# BPM-sorted lists per Camelot key, scanned outwards from the current BPM,
# so a step only looks at the handful of tracks a DJ could actually mix into.

PATH_DIRECTIONS = ("up", "down", "flat")

# Step-cost weights. The BPM move is in percent of the current tempo, so a
# 2 % nudge costs 2; a key change costs about a 1 % nudge, a category change
# about a 2 % one. A continuation that dead-ends inside the lookahead window
# costs far more than any real move, so the beam steers away from it.
_KEY_STEP_COST = {"same": 0.0, "adjacent": 1.0, "relative": 1.5}
_CATEGORY_CHANGE_COST = 2.0
_CATEGORY_UNKNOWN_COST = 1.0
_DEAD_END_COST = 100.0

_CamelotKey = tuple[int, str]
_Move = tuple[PlaylistTrack, _CamelotKey]


@dataclass(frozen=True)
class PathResult:
    """A path-mode draft: `path` in play order, and every input track that
    couldn't be placed on it (no BPM/key, unreachable within the BPM
    tolerance and direction, or past `max_length`) in `leftovers`, in
    simple-mode order -- reported, never silently dropped."""

    path: list[PlaylistTrack]
    leftovers: list[PlaylistTrack]


def _key_step(key_a: _CamelotKey, key_b: _CamelotKey) -> str:
    """"same", "adjacent" (+/-1) or "relative" -- only called on pairs the
    index already knows are compatible."""
    if key_a == key_b:
        return "same"
    return "relative" if key_a[0] == key_b[0] else "adjacent"


def _compatible_keys(key: _CamelotKey) -> list[_CamelotKey]:
    number, letter = key
    other = "A" if letter == "B" else "B"
    return [key, (number % 12 + 1, letter), ((number - 2) % 12 + 1, letter), (number, other)]


def _entry_sort_key(entry: tuple[float, str, PlaylistTrack]) -> tuple[float, str]:
    return entry[0], entry[1]


def _entry_bpm(entry: tuple[float, str, PlaylistTrack]) -> float:
    return entry[0]


class _PathIndex:
    """Unplaced tracks, as BPM-sorted lists per Camelot key."""

    def __init__(self, moves: list[_Move]) -> None:
        self.by_key: dict[_CamelotKey, list[tuple[float, str, PlaylistTrack]]] = {}
        for track, key in moves:
            self.by_key.setdefault(key, []).append((track.bpm or 0.0, track.identifier, track))
        for entries in self.by_key.values():
            entries.sort(key=_entry_sort_key)

    def remove(self, track: PlaylistTrack, key: _CamelotKey) -> None:
        entries = self.by_key[key]
        del entries[bisect_left(entries, (track.bpm or 0.0, track.identifier), key=_entry_sort_key)]

    def neighbours(
        self,
        bpm: float,
        key: _CamelotKey,
        direction: str,
        tolerance_pct: float,
        skip: tuple[str, ...],
        per_side: int,
    ) -> list[_Move]:
        """Up to `per_side` unplaced, BPM-compatible tracks per compatible
        key and allowed side of `bpm`, closest BPM first. An equal BPM
        counts as "up" (and as "down" in "down" mode)."""
        found: list[_Move] = []
        for other_key in _compatible_keys(key):
            entries = self.by_key.get(other_key)
            if not entries:
                continue
            if direction in ("up", "flat"):
                taken = 0
                for index in range(bisect_left(entries, bpm, key=_entry_bpm), len(entries)):
                    other_bpm, identifier, track = entries[index]
                    if taken >= per_side or not is_bpm_compatible(bpm, other_bpm, tolerance_pct):
                        break
                    if identifier not in skip:
                        found.append((track, other_key))
                        taken += 1
            if direction in ("down", "flat"):
                taken = 0
                if direction == "down":
                    index = bisect_right(entries, bpm, key=_entry_bpm) - 1
                else:
                    index = bisect_left(entries, bpm, key=_entry_bpm) - 1
                while index >= 0 and taken < per_side:
                    other_bpm, identifier, track = entries[index]
                    if not is_bpm_compatible(bpm, other_bpm, tolerance_pct):
                        break
                    if identifier not in skip:
                        found.append((track, other_key))
                        taken += 1
                    index -= 1
        return found


def _step_cost(current: _Move, candidate: _Move) -> float:
    current_track, current_key = current
    track, key = candidate
    current_bpm = current_track.bpm or 1.0
    cost = abs((track.bpm or 0.0) - current_bpm) / current_bpm * 100.0
    cost += _KEY_STEP_COST[_key_step(current_key, key)]
    if current_track.category is None or track.category is None:
        cost += _CATEGORY_UNKNOWN_COST
    elif current_track.category != track.category:
        cost += _CATEGORY_CHANGE_COST
    return cost


def _best_next_move(
    index: _PathIndex,
    current: _Move,
    direction: str,
    tolerance_pct: float,
    beam_width: int,
    lookahead: int,
    per_side: int,
) -> _Move | None:
    """The first move of the cheapest `lookahead`-deep continuation, or
    None when no track can follow `current` at all."""
    # A beam state: (cost, identifiers placed so far -- also the tie-break
    # --, the moves themselves, whether it dead-ended).
    beam: list[tuple[float, tuple[str, ...], tuple[_Move, ...], bool]] = [(0.0, (), (), False)]
    for depth in range(lookahead):
        children: list[tuple[float, tuple[str, ...], tuple[_Move, ...], bool]] = []
        for state in beam:
            cost, ids, moves, dead = state
            if dead:
                children.append(state)
                continue
            last = moves[-1] if moves else current
            options = index.neighbours(last[0].bpm or 0.0, last[1], direction, tolerance_pct, ids, per_side)
            if not options:
                if moves:
                    # Dead end inside the window: penalized once for every
                    # step it can't take, so longer continuations win.
                    children.append((cost + _DEAD_END_COST * (lookahead - depth), ids, moves, True))
                continue
            for option in options:
                children.append((cost + _step_cost(last, option), (*ids, option[0].identifier), (*moves, option), False))
        if not children:
            return None
        children.sort(key=lambda child: (child[0], child[1]))
        beam = children[:beam_width]
        if all(state[3] for state in beam):
            break
    return beam[0][2][0]


def build_playlist_path(
    tracks: list[PlaylistTrack],
    start: str | None = None,
    *,
    tolerance_pct: float = 6.0,
    direction: str = "up",
    max_length: int | None = None,
    beam_width: int = 8,
    lookahead: int = 3,
) -> PathResult:
    """Issue #191's "path" mode: order `tracks` so each step is BPM- and
    Camelot-compatible with the previous one and the BPM never moves against
    `direction` ("up" = rising energy, "down", or "flat" = either way,
    smallest moves first). `start` is a track identifier; by default the path
    starts from the slowest track ("up"/"flat") or the fastest ("down").
    Deterministic: ties always break on the identifier. Tracks the path can't
    reach end up in `PathResult.leftovers`."""
    if direction not in PATH_DIRECTIONS:
        raise ValueError(f"Unknown direction {direction!r}; expected one of {PATH_DIRECTIONS}")
    unique: dict[str, PlaylistTrack] = {}
    for track in tracks:
        unique.setdefault(track.identifier, track)
    placeable: list[_Move] = []
    for track in unique.values():
        key = _parse_camelot(track.camelot_key) if track.camelot_key else None
        if track.bpm is not None and track.bpm > 0 and key is not None:
            placeable.append((track, key))

    first: _Move | None = None
    if start is not None:
        first = next((move for move in placeable if move[0].identifier == start), None)
        if first is None:
            raise ValueError(f"Start track is missing, or has no BPM/Camelot key: {start}")
    elif placeable:
        ordered = sorted(placeable, key=lambda move: (move[0].bpm or 0.0, move[0].identifier))
        first = ordered[-1] if direction == "down" else ordered[0]

    path: list[PlaylistTrack] = []
    if first is not None and (max_length is None or max_length > 0):
        index = _PathIndex(placeable)
        limit = max_length if max_length is not None else len(placeable)
        per_side = max(2, beam_width // 2)
        current: _Move | None = first
        while current is not None:
            index.remove(*current)
            path.append(current[0])
            if len(path) >= limit:
                break
            current = _best_next_move(index, current, direction, tolerance_pct, beam_width, lookahead, per_side)

    placed = {track.identifier for track in path}
    leftovers = [track for track in unique.values() if track.identifier not in placed]
    return PathResult(path=path, leftovers=build_playlist_draft(leftovers))
