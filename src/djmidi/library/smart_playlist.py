"""Smart playlists (issue #259): saved rules re-evaluated against the library.

A smart playlist is an ordinary `playlists` row of this app's `LibraryDB`
(source ``"smart"``) plus its `SmartRules`, stored as JSON in the
``smart_playlists`` table. Evaluating the rules writes the matching paths into
the playlist's `playlist_tracks`, so everything that works on a playlist --
the track list, export as a Serato crate or Traktor playlist, compare --
works on a smart one unchanged; it just reflects the last evaluation. The
Music Library tab re-evaluates every smart playlist after a scan and on
demand.

Rules are AND-ed, and an unset rule matches everything:

- ``category``: a taxonomy family (``Tek`` matches every ``Tek%%…``
  category) or one category (``Tek%%PsyTrance``); only a confirmed category
  counts, never a fuzzy suggestion;
- ``genre`` / ``text``: case-insensitive substring of the genre tag, or of
  title, artist, album or file path;
- ``bpm_min`` / ``bpm_max``: inclusive range; a track with no BPM fails it;
- ``camelot_key``: same Camelot key, or (``key_compatible``) any key that
  mixes harmonically with it (`playlist.is_camelot_compatible`);
- ``not_played_days``: never played, or last played more than that many days
  ago, according to the play counts stored from the last loaded DJ history
  (`LibraryDB.play_stats`). A play with no recorded time can't be proven
  old, so it fails the rule.

Missing files never match. Qt-free, like the rest of `djmidi.library`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

from .analysis import to_camelot
from .db import LibraryDB
from .history import TrackPlays
from .playlist import build_playlist_draft, is_camelot_compatible
from .workspace import LibraryRow, consolidate, to_playlist_tracks

SOURCE_SMART = "smart"

SORT_MIX = "mix"
SORT_BPM = "bpm"
SORT_PATH = "path"
# English labels, marked for the interface catalogue (issue #313): the
# dialog shows `QCoreApplication.translate("SmartPlaylistDialog", label)`.
SORT_LABELS = {
    SORT_MIX: QT_TRANSLATE_NOOP("SmartPlaylistDialog", "Category, BPM range, then key"),
    SORT_BPM: QT_TRANSLATE_NOOP("SmartPlaylistDialog", "BPM (slowest first)"),
    SORT_PATH: QT_TRANSLATE_NOOP("SmartPlaylistDialog", "File path"),
}

# Rule summary parts (issue #313): English templates `describe` passes
# through the caller's `translate` before filling in.
_RULE_CATEGORY = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "category {category}")
_RULE_GENRE = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "genre contains “{genre}”")
_RULE_TEXT = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "text contains “{text}”")
_RULE_BPM_RANGE = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "BPM {low}–{high}")
_RULE_BPM_MIN = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "BPM ≥ {low}")
_RULE_BPM_MAX = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "BPM ≤ {high}")
_RULE_KEY_COMPATIBLE = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "key compatible with {key}")
_RULE_KEY = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "key {key}")
_RULE_NOT_PLAYED = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "not played for {days} days")
_RULE_EVERY_TRACK = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "every track")
_RULE_LIMIT = QT_TRANSLATE_NOOP("SmartPlaylistDialog", "first {limit}")

_FORMAT_VERSION = 1


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_category(value: str) -> tuple[str, str | None]:
    """``Tek`` -> (``tek``, None); ``Tek%%PsyTrance`` or ``Tek / PsyTrance``
    -> (``tek``, ``psytrance``), lower-cased for comparison."""
    for separator in ("%%", "/"):
        if separator in value:
            family, name = value.split(separator, 1)
            return family.strip().lower(), name.strip().lower() or None
    return value.strip().lower(), None


@dataclass(frozen=True)
class SmartRules:
    category: str | None = None
    genre: str | None = None
    text: str | None = None
    bpm_min: float | None = None
    bpm_max: float | None = None
    camelot_key: str | None = None
    key_compatible: bool = True
    not_played_days: int | None = None
    sort: str = SORT_MIX
    limit: int | None = None

    def normalized(self) -> SmartRules:
        """Empty strings and zero/negative limits dropped, a reversed BPM range
        swapped, the key turned into a Camelot code. Raises `ValueError` for a
        key no notation recognizes or an unknown sort."""
        bpm_min = float(self.bpm_min) if self.bpm_min is not None else None
        bpm_max = float(self.bpm_max) if self.bpm_max is not None else None
        if bpm_min is not None and bpm_max is not None and bpm_min > bpm_max:
            bpm_min, bpm_max = bpm_max, bpm_min
        key_text = _clean_text(self.camelot_key)
        camelot = to_camelot(key_text) if key_text is not None else None
        if key_text is not None and camelot is None:
            raise ValueError(f"Not a musical key: {key_text}")
        if self.sort not in SORT_LABELS:
            raise ValueError(f"Unknown sort: {self.sort}")
        days = int(self.not_played_days) if self.not_played_days is not None else None
        limit = int(self.limit) if self.limit is not None else None
        return replace(
            self,
            category=_clean_text(self.category),
            genre=_clean_text(self.genre),
            text=_clean_text(self.text),
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            camelot_key=camelot,
            key_compatible=bool(self.key_compatible),
            not_played_days=days if days is not None and days > 0 else None,
            limit=limit if limit is not None and limit > 0 else None,
        )

    def to_json(self) -> str:
        return json.dumps({"version": _FORMAT_VERSION, **asdict(self)}, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> SmartRules:
        """Rules saved by `to_json`; unknown keys (a newer version) are
        ignored. Raises `ValueError` for anything that isn't a rules object."""
        try:
            data = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unreadable smart playlist rules: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Smart playlist rules must be a JSON object")  # noqa: TRY004 -- one error type for callers
        known = {f.name for f in fields(cls)}
        try:
            return cls(**{k: v for k, v in data.items() if k in known}).normalized()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid smart playlist rules: {exc}") from exc

    def describe(self, translate: Translate = untranslated) -> str:
        """One line for the playlist list's tooltip, e.g. ``category Tek ·
        BPM 170–180 · key compatible with 8A · not played for 90 days``, in
        the language `translate` gives (English by default)."""
        parts: list[str] = []
        if self.category:
            parts.append(translate(_RULE_CATEGORY).format(category=self.category.replace("%%", " / ")))
        if self.genre:
            parts.append(translate(_RULE_GENRE).format(genre=self.genre))
        if self.text:
            parts.append(translate(_RULE_TEXT).format(text=self.text))
        low = None if self.bpm_min is None else f"{self.bpm_min:g}"
        high = None if self.bpm_max is None else f"{self.bpm_max:g}"
        if low is not None and high is not None:
            parts.append(translate(_RULE_BPM_RANGE).format(low=low, high=high))
        elif low is not None:
            parts.append(translate(_RULE_BPM_MIN).format(low=low))
        elif high is not None:
            parts.append(translate(_RULE_BPM_MAX).format(high=high))
        if self.camelot_key:
            template = _RULE_KEY_COMPATIBLE if self.key_compatible else _RULE_KEY
            parts.append(translate(template).format(key=self.camelot_key))
        if self.not_played_days:
            parts.append(translate(_RULE_NOT_PLAYED).format(days=self.not_played_days))
        text = " · ".join(parts) or translate(_RULE_EVERY_TRACK)
        if self.limit:
            text += " · " + translate(_RULE_LIMIT).format(limit=self.limit)
        return text


# --- play history -----------------------------------------------------------


def play_stats_rows(plays: Mapping[str, TrackPlays]) -> list[tuple[str, int, str | None]]:
    """`history.summarize_plays` output as `LibraryDB.set_play_stats` rows."""
    return [
        (path, p.play_count, p.last_played.isoformat() if p.last_played is not None else None)
        for path, p in plays.items()
    ]


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A naive time is read in the computer's local zone, like history's.
    return parsed if parsed.tzinfo is not None else parsed.astimezone()


def last_played_map(stats: Mapping[str, tuple[int, str | None]]) -> dict[str, datetime | None]:
    """Path -> last play time (None when played at an unknown time), for the
    paths `LibraryDB.play_stats` lists with at least one play."""
    return {path: _parse_time(last) for path, (count, last) in stats.items() if count > 0}


# --- evaluation ---------------------------------------------------------------


def _category_matches(wanted: str, category: str | None) -> bool:
    if category is None:
        return False
    family, name = _split_category(wanted)
    row_family, row_name = _split_category(category)
    return family == row_family and (name is None or name == row_name)


def _contains(needle: str, *haystack: str | None) -> bool:
    needle = needle.casefold()
    return any(value is not None and needle in value.casefold() for value in haystack)


def matches(
    rules: SmartRules,
    row: LibraryRow,
    last_played: Mapping[str, datetime | None],
    now: datetime,
) -> bool:
    """Whether `row` satisfies every rule (`rules` already normalized)."""
    if row.missing:
        return False
    metadata = row.metadata
    if rules.category is not None and not _category_matches(rules.category, row.category):
        return False
    if rules.genre is not None and not _contains(rules.genre, metadata.genre if metadata else None):
        return False
    if rules.text is not None:
        tags = (metadata.title, metadata.artist, metadata.album) if metadata else ()
        if not _contains(rules.text, row.path, *tags):
            return False
    if rules.bpm_min is not None or rules.bpm_max is not None:
        bpm = row.bpm
        if bpm is None:
            return False
        if rules.bpm_min is not None and bpm < rules.bpm_min:
            return False
        if rules.bpm_max is not None and bpm > rules.bpm_max:
            return False
    if rules.camelot_key is not None:
        if row.camelot_key is None:
            return False
        if rules.key_compatible:
            if not is_camelot_compatible(rules.camelot_key, row.camelot_key):
                return False
        elif row.camelot_key.upper() != rules.camelot_key:
            return False
    if rules.not_played_days is not None and row.path in last_played:
        played_at = last_played[row.path]
        if played_at is None or played_at > now - timedelta(days=rules.not_played_days):
            return False
    return True


def evaluate(
    rules: SmartRules,
    rows: Iterable[LibraryRow],
    last_played: Mapping[str, datetime | None] | None = None,
    now: datetime | None = None,
) -> list[str]:
    """The paths of `rows` matching `rules`, in the rules' order, cut to their
    limit."""
    rules = rules.normalized()
    when = now if now is not None else datetime.now(UTC)
    played = last_played or {}
    matched = [row for row in rows if matches(rules, row, played, when)]
    if rules.sort == SORT_MIX:
        paths = [track.identifier for track in build_playlist_draft(to_playlist_tracks(matched))]
    elif rules.sort == SORT_BPM:
        paths = [row.path for row in sorted(matched, key=lambda r: (r.bpm is None, r.bpm or 0.0, r.path))]
    else:
        paths = sorted(row.path for row in matched)
    return paths[: rules.limit] if rules.limit else paths


# --- storage ----------------------------------------------------------------


def _evaluate_stored(
    db: LibraryDB, rules: SmartRules, rows: list[LibraryRow] | None, now: datetime | None
) -> list[str]:
    if rows is None:
        rows = consolidate(db)
    return evaluate(rules, rows, last_played_map(db.play_stats()), now)


def create_smart_playlist(
    db: LibraryDB,
    name: str,
    rules: SmartRules,
    rows: list[LibraryRow] | None = None,
    now: datetime | None = None,
) -> int:
    """Save `rules` as a new smart playlist, already evaluated; returns its id."""
    rules = rules.normalized()
    playlist_id = db.create_playlist(name, _evaluate_stored(db, rules, rows, now), SOURCE_SMART)
    db.set_smart_rules(playlist_id, rules.to_json())
    return playlist_id


def load_rules(db: LibraryDB, playlist_id: int) -> SmartRules | None:
    """The playlist's rules, or None for an ordinary playlist."""
    text = db.smart_rules(playlist_id)
    return SmartRules.from_json(text) if text is not None else None


def update_smart_playlist(
    db: LibraryDB,
    playlist_id: int,
    rules: SmartRules,
    rows: list[LibraryRow] | None = None,
    now: datetime | None = None,
) -> int:
    """Replace a smart playlist's rules and re-evaluate it; returns its size."""
    rules = rules.normalized()
    paths = _evaluate_stored(db, rules, rows, now)
    db.set_smart_rules(playlist_id, rules.to_json())
    db.set_playlist_paths(playlist_id, paths)
    return len(paths)


def refresh_smart_playlists(
    db: LibraryDB, rows: list[LibraryRow] | None = None, now: datetime | None = None
) -> dict[int, int]:
    """Re-evaluate every smart playlist; returns playlist id -> track count.
    A playlist whose saved rules can't be read is left as it was."""
    stored = db.list_smart_rules()
    if not stored:
        return {}
    if rows is None:
        rows = consolidate(db)
    last_played = last_played_map(db.play_stats())
    counts: dict[int, int] = {}
    for playlist_id, text in stored.items():
        try:
            rules = SmartRules.from_json(text)
        except ValueError:
            continue
        paths = evaluate(rules, rows, last_played, now)
        db.set_playlist_paths(playlist_id, paths)
        counts[playlist_id] = len(paths)
    return counts
