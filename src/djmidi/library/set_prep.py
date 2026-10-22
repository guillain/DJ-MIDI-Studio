"""Set preparation (issue #221): a hand-ordered set draft and its transitions.

Qt-free core of the Music Library tab's *Set* panel. The DJ builds the draft
by hand (drag-and-drop order); this module only reports on it: one
`Transition` per adjacent pair, flagged with the same rules the playlist
generators use (`playlist.is_bpm_compatible` with a percentage tolerance,
`playlist.is_camelot_compatible`), plus the BPM/energy values the panel
draws as a curve. It never reorders anything on its own.

A transition is ``"incompatible"`` only when a known value breaks a rule;
a missing BPM or key makes it ``"unknown"`` instead, so an untagged track
isn't reported as a clash it may not be.

The draft itself is remembered in the library index (`library_settings`),
so it survives a restart; saving it as a real playlist goes through
`LibraryDB.create_playlist` with `SOURCE_SET`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

from .db import LibraryDB
from .playlist import is_bpm_compatible, is_camelot_compatible
from .workspace import LibraryRow

# Playlist `source` of a saved set draft.
SOURCE_SET = "set"

DEFAULT_BPM_TOLERANCE_PCT = 6.0
BPM_TOLERANCE_RANGE = (0.5, 20.0)
_DRAFT_SETTING = "set_draft"

# Mixed In Key's energy scale, the one `TrackMetadata.energy` comes from.
ENERGY_RANGE = (1, 10)
_FIRST_INTEGER = re.compile(r"\d+")

STATUS_OK = "ok"
STATUS_INCOMPATIBLE = "incompatible"
STATUS_UNKNOWN = "unknown"

# Transition notes and the summary line (issue #313): English templates the
# caller's `translate` turns into the interface language before filling in.
_BPM_JUMP = QT_TRANSLATE_NOOP("SetPreparationPanel", "BPM jump {change} (tolerance ±{tolerance} %)")
_BPM_UNKNOWN = QT_TRANSLATE_NOOP("SetPreparationPanel", "BPM unknown")
_KEY_CLASH = QT_TRANSLATE_NOOP("SetPreparationPanel", "Key clash {before} → {after}")
_KEY_UNKNOWN = QT_TRANSLATE_NOOP("SetPreparationPanel", "Key unknown")
_SUMMARY_TRACKS = QT_TRANSLATE_NOOP("SetPreparationPanel", "{count} track(s)")
_SUMMARY_INCOMPATIBLE = QT_TRANSLATE_NOOP("SetPreparationPanel", "{count} incompatible transition(s)")
_SUMMARY_UNKNOWN = QT_TRANSLATE_NOOP("SetPreparationPanel", "{count} unchecked (missing BPM/key)")


def parse_energy(text: str | None) -> int | None:
    """The energy level of a tag such as ``"6"`` or ``"Energy 6"``; `None`
    when there is no integer in `ENERGY_RANGE`."""
    if not text:
        return None
    match = _FIRST_INTEGER.search(text)
    if match is None:
        return None
    value = int(match.group())
    low, high = ENERGY_RANGE
    return value if low <= value <= high else None


@dataclass(frozen=True)
class SetTrack:
    """One entry of the draft. `indexed` is False for a path the library
    index doesn't know (moved, or from an imported playlist)."""

    path: str
    title: str | None = None
    artist: str | None = None
    bpm: float | None = None
    camelot_key: str | None = None
    energy: int | None = None
    indexed: bool = True

    @property
    def label(self) -> str:
        if not self.title:
            return Path(self.path).name
        return f"{self.artist} — {self.title}" if self.artist else self.title


def set_track_from_row(row: LibraryRow) -> SetTrack:
    metadata = row.metadata
    return SetTrack(
        path=row.path,
        title=metadata.title if metadata else None,
        artist=metadata.artist if metadata else None,
        bpm=row.bpm,
        camelot_key=row.camelot_key,
        energy=parse_energy(metadata.energy) if metadata else None,
        indexed=not row.missing,
    )


def resolve_set_tracks(paths: Iterable[str], rows: Mapping[str, LibraryRow]) -> list[SetTrack]:
    """The draft's paths as `SetTrack`s, looked up in `rows` (path -> row)."""
    tracks = []
    for path in paths:
        row = rows.get(path)
        tracks.append(set_track_from_row(row) if row is not None else SetTrack(path=path, indexed=False))
    return tracks


@dataclass(frozen=True)
class Transition:
    """The mix from `tracks[index]` into `tracks[index + 1]`.

    `bpm_ok` / `key_ok` are `None` when either side lacks that value."""

    index: int
    bpm_change_pct: float | None
    bpm_ok: bool | None
    key_ok: bool | None
    issues: tuple[str, ...] = field(default=())

    @property
    def status(self) -> str:
        if self.bpm_ok is False or self.key_ok is False:
            return STATUS_INCOMPATIBLE
        if self.bpm_ok is None or self.key_ok is None:
            return STATUS_UNKNOWN
        return STATUS_OK


def _format_pct(value: float) -> str:
    return f"{value:+.1f} %"


def analyze_transition(
    index: int,
    before: SetTrack,
    after: SetTrack,
    bpm_tolerance_pct: float = DEFAULT_BPM_TOLERANCE_PCT,
    translate: Translate = untranslated,
) -> Transition:
    """`translate` renders the `issues` notes in the interface language."""
    issues: list[str] = []
    bpm_change = bpm_ok = None
    if before.bpm and after.bpm and before.bpm > 0 and after.bpm > 0:
        bpm_change = (after.bpm - before.bpm) / before.bpm * 100.0
        bpm_ok = is_bpm_compatible(before.bpm, after.bpm, bpm_tolerance_pct)
        if not bpm_ok:
            issues.append(
                translate(_BPM_JUMP).format(change=_format_pct(bpm_change), tolerance=f"{bpm_tolerance_pct:g}")
            )
    else:
        issues.append(translate(_BPM_UNKNOWN))
    key_ok = None
    if before.camelot_key and after.camelot_key:
        key_ok = is_camelot_compatible(before.camelot_key, after.camelot_key)
        if not key_ok:
            issues.append(translate(_KEY_CLASH).format(before=before.camelot_key, after=after.camelot_key))
    else:
        issues.append(translate(_KEY_UNKNOWN))
    return Transition(index, bpm_change, bpm_ok, key_ok, tuple(issues))


def analyze_set(
    tracks: Sequence[SetTrack],
    bpm_tolerance_pct: float = DEFAULT_BPM_TOLERANCE_PCT,
    translate: Translate = untranslated,
) -> list[Transition]:
    """One `Transition` per adjacent pair, in play order."""
    return [
        analyze_transition(index, tracks[index], tracks[index + 1], bpm_tolerance_pct, translate)
        for index in range(len(tracks) - 1)
    ]


@dataclass(frozen=True)
class SetSummary:
    tracks: int
    incompatible: int
    unknown: int

    @property
    def text(self) -> str:
        return self.describe()

    def describe(self, translate: Translate = untranslated) -> str:
        """The panel's summary line, in the language `translate` gives."""
        parts = [translate(_SUMMARY_TRACKS).format(count=self.tracks)]
        if self.tracks > 1:
            parts.append(translate(_SUMMARY_INCOMPATIBLE).format(count=self.incompatible))
            if self.unknown:
                parts.append(translate(_SUMMARY_UNKNOWN).format(count=self.unknown))
        return " · ".join(parts)


def summarize(tracks: Sequence[SetTrack], transitions: Sequence[Transition]) -> SetSummary:
    statuses = [transition.status for transition in transitions]
    return SetSummary(len(tracks), statuses.count(STATUS_INCOMPATIBLE), statuses.count(STATUS_UNKNOWN))


# --- editing the order -------------------------------------------------


def insert_paths(current: Sequence[str], paths: Iterable[str], index: int | None = None) -> list[str]:
    """`current` with `paths` inserted at `index` (end by default). A set
    plays each track once: a path already in the draft, or repeated in
    `paths`, is skipped."""
    present = set(current)
    added: list[str] = []
    for path in paths:
        if path not in present:
            present.add(path)
            added.append(path)
    position = len(current) if index is None else max(0, min(index, len(current)))
    return [*current[:position], *added, *current[position:]]


def move_rows(current: Sequence[str], rows: Iterable[int], offset: int) -> tuple[list[str], list[int]]:
    """Moves the entries at `rows` by `offset` (-1 = up, +1 = down) as a
    block, clamped at either end. Returns the new order and the moved
    entries' new rows."""
    order = list(current)
    selected = sorted({row for row in rows if 0 <= row < len(order)})
    if not selected or offset == 0:
        return order, selected
    if offset < 0:
        offset = max(offset, -selected[0])
    else:
        offset = min(offset, len(order) - 1 - selected[-1])
    moving = [order[row] for row in selected]
    chosen = set(selected)
    remaining = [path for row, path in enumerate(order) if row not in chosen]
    start = selected[0] + offset
    order = [*remaining[:start], *moving, *remaining[start:]]
    return order, list(range(start, start + len(moving)))


def remove_rows(current: Sequence[str], rows: Iterable[int]) -> list[str]:
    drop = set(rows)
    return [path for row, path in enumerate(current) if row not in drop]


# --- persistence ---------------------------------------------------------


@dataclass(frozen=True)
class SetDraft:
    paths: tuple[str, ...] = ()
    bpm_tolerance_pct: float = DEFAULT_BPM_TOLERANCE_PCT


def _clamp_tolerance(value: object) -> float:
    try:
        tolerance = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_BPM_TOLERANCE_PCT
    low, high = BPM_TOLERANCE_RANGE
    return min(max(tolerance, low), high)


def load_set_draft(db: LibraryDB) -> SetDraft:
    """The remembered draft; anything unreadable falls back to empty."""
    stored = db.get_setting(_DRAFT_SETTING)
    if not isinstance(stored, dict):
        return SetDraft()
    paths = stored.get("paths")
    if not isinstance(paths, list):
        paths = []
    return SetDraft(
        paths=tuple(insert_paths([], (path for path in paths if isinstance(path, str) and path))),
        bpm_tolerance_pct=_clamp_tolerance(stored.get("bpm_tolerance_pct", DEFAULT_BPM_TOLERANCE_PCT)),
    )


def save_set_draft(db: LibraryDB, draft: SetDraft) -> None:
    db.set_setting(
        _DRAFT_SETTING,
        {"paths": list(draft.paths), "bpm_tolerance_pct": _clamp_tolerance(draft.bpm_tolerance_pct)},
    )
