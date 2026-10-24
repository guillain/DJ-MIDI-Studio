"""Command palette ranking (issue #222): one search over every menu action,
tab, mapping function and library track, so Cmd+K + a few letters + Enter
reaches anything without the mouse.

Qt-free on purpose (testable without a QApplication): the GUI side
(`gui/command_palette.py`) only collects entries -- walking the menu bar,
the tab bar, the loaded mapping's `function_search` index and the Music
Library's rows -- and runs whatever the chosen entry's `payload` stands for.

Ranking, per query token (every token must match, case-insensitive):

- an exact word of the entry's title or keywords beats a word prefix,
  which beats a substring, which beats an in-order subsequence of the
  title's letters (`cs` -> "Cheat Sheet", `opmap` -> "Open Mapping");
- the query as a whole phrase inside the title earns a bonus;
- kinds break ties: actions, then tabs, then functions, then tracks
  (a track title that happens to say "save" doesn't outrank Save).

Functions are not re-scored here: `function_search.search_functions`
already ranks them with the same exact/prefix/substring scale (and
understands `deck 2` / `slot 3` / `output`), so its results are merged in
as they come. Tracks only appear once the query has `TRACK_MIN_QUERY`
characters -- a real library has ~85k of them, which would drown actions
for a one-letter query and cost a full scan per keystroke.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from djmidi.function_search import FunctionResult, search_functions
from djmidi.i18n import QT_TRANSLATE_NOOP

_TOKEN_RE = re.compile(r"[a-z0-9]+")

KIND_ACTION = "action"
KIND_TAB = "tab"
KIND_FUNCTION = "function"
KIND_TRACK = "track"
_KIND_ORDER = {KIND_ACTION: 0, KIND_TAB: 1, KIND_FUNCTION: 2, KIND_TRACK: 3}
# English; the palette window shows them translated (issue #337).
KIND_LABELS = {
    KIND_ACTION: QT_TRANSLATE_NOOP("CommandPaletteDialog", "Action"),
    KIND_TAB: QT_TRANSLATE_NOOP("CommandPaletteDialog", "Tab"),
    KIND_FUNCTION: QT_TRANSLATE_NOOP("CommandPaletteDialog", "Function"),
    KIND_TRACK: QT_TRANSLATE_NOOP("CommandPaletteDialog", "Track"),
}

_EXACT_WORD = 3.0
_PREFIX_WORD = 2.0
_SUBSTRING = 1.0
_SUBSEQUENCE = 0.5
_PHRASE_BONUS = 2.0
# Keywords (a menu path, a track's album) match a little below the title.
_KEYWORD_FACTOR = 0.75

TRACK_MIN_QUERY = 2
DEFAULT_LIMIT = 60


@dataclass
class PaletteEntry:
    """One searchable thing. `payload` is opaque here: the GUI decides what
    running it means (trigger a QAction, switch tab, select a function or a
    track)."""

    kind: str
    title: str
    detail: str = ""
    keywords: str = ""
    payload: object = None
    score: float = 0.0
    _title_words: list[str] = field(default_factory=list, repr=False)
    _keyword_words: list[str] = field(default_factory=list, repr=False)
    _title_joined: str = field(default="", repr=False)
    _keyword_joined: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self._title_words = tokenize(self.title)
        self._keyword_words = tokenize(self.keywords)
        self._title_joined = " ".join(self._title_words)
        self._keyword_joined = " ".join(self._keyword_words)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def clean_menu_text(text: str) -> str:
    """A menu label as the user reads it: mnemonic `&` dropped (`&&` is a
    literal ampersand), a trailing ellipsis removed."""
    cleaned = text.replace("&&", "\0").replace("&", "").replace("\0", "&").strip()
    for suffix in ("...", "…"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].rstrip()
    return cleaned


def _is_subsequence(needle: str, haystack: str) -> bool:
    letters = iter(haystack)
    return all(char in letters for char in needle)


def _word_score(token: str, words: list[str], joined: str) -> float:
    if token in words:
        return _EXACT_WORD
    if any(word.startswith(token) for word in words):
        return _PREFIX_WORD
    if len(token) > 1 and token in joined:
        return _SUBSTRING
    return 0.0


def score_entry(entry: PaletteEntry, tokens: list[str], subsequence: bool = True) -> float | None:
    """`None` when a token matches nothing; otherwise higher is better.
    `subsequence=False` skips the in-order-letters fallback (used for
    tracks: noisy on long titles, and the slowest test over ~85k rows)."""
    if not tokens:
        return None
    total = 0.0
    compact_title = entry._title_joined.replace(" ", "")
    for token in tokens:
        score = _word_score(token, entry._title_words, entry._title_joined)
        if not score:
            score = _KEYWORD_FACTOR * _word_score(token, entry._keyword_words, entry._keyword_joined)
        if not score and subsequence and len(token) > 1 and _is_subsequence(token, compact_title):
            score = _SUBSEQUENCE
        if not score:
            return None
        total += score
    # Same rule as function_search's phrase bonus (one token included), so
    # an action and a function matching equally well tie on score.
    if " ".join(tokens) in entry._title_joined:
        total += _PHRASE_BONUS
    return total


def function_entry(result: FunctionResult) -> PaletteEntry:
    event = "" if result.event == "click" else f" [{result.event}]"
    triggers = ", ".join(trigger.describe() for trigger in result.triggers)
    return PaletteEntry(
        KIND_FUNCTION,
        f"{result.label}{event}",
        detail=f"{result.location()} · {triggers}",
        keywords=result.tag,
        payload=result,
    )


def track_entry(path: str, title: str | None, artist: str | None, album: str | None = None,
                detail: str = "", payload: object = None) -> PaletteEntry:
    """A library track, titled "Artist – Title" (or its file name when it
    has no tags); the album and file name stay searchable as keywords."""
    name = os.path.basename(path)
    shown = " – ".join(part for part in (artist, title) if part) or name
    return PaletteEntry(
        KIND_TRACK,
        shown,
        detail=detail or path,
        keywords=" ".join(part for part in (album, os.path.splitext(name)[0]) if part),
        payload=payload if payload is not None else path,
    )


class PaletteIndex:
    """Everything the palette can reach, built once when it opens and
    searched on every keystroke."""

    def __init__(
        self,
        entries: Iterable[PaletteEntry] = (),
        functions: list[FunctionResult] | None = None,
        tracks: Iterable[PaletteEntry] = (),
    ) -> None:
        self.entries = list(entries)
        self.functions = list(functions or [])
        self.tracks = list(tracks)

    def search(self, query: str, limit: int = DEFAULT_LIMIT) -> list[PaletteEntry]:
        """Best first. An empty query lists the actions and tabs (in their
        menu order) so the palette is browsable before typing."""
        tokens = tokenize(query)
        if not tokens:
            return self.entries[:limit]
        scored: list[PaletteEntry] = []
        for entry in self.entries:
            score = score_entry(entry, tokens)
            if score is not None:
                entry.score = score
                scored.append(entry)
        if self.functions:
            for result in search_functions(self.functions, query):
                entry = function_entry(result)
                entry.score = result.score
                scored.append(entry)
        if len(query.strip()) >= TRACK_MIN_QUERY:
            for entry in self.tracks:
                score = score_entry(entry, tokens, subsequence=False)
                if score is not None:
                    entry.score = score
                    scored.append(entry)
        # Stable sort: equal scores and kinds keep their collection order.
        scored.sort(key=lambda entry: (-entry.score, _KIND_ORDER.get(entry.kind, 9)))
        return scored[:limit]


__all__ = [
    "DEFAULT_LIMIT",
    "KIND_ACTION",
    "KIND_FUNCTION",
    "KIND_LABELS",
    "KIND_TAB",
    "KIND_TRACK",
    "TRACK_MIN_QUERY",
    "PaletteEntry",
    "PaletteIndex",
    "clean_menu_text",
    "function_entry",
    "score_entry",
    "tokenize",
    "track_entry",
]
