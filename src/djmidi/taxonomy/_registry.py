"""The plumbing behind taxonomy's plugin-style registry: a Category per
genre/subgenre, registered by importing its family module (see
taxonomy/__init__.py). Add a new family by writing one new module here, not
by editing this file or any resolution code -- see taxonomy/__init__.py's
module docstring for the steps."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from dataclasses import replace as dc_replace
from typing import Literal

from rapidfuzz import fuzz, process

_LOGGER = logging.getLogger(__name__)

Confidence = Literal["exact", "alias", "fuzzy", "none"]

FUZZY_THRESHOLD = 70.0


@dataclass(frozen=True)
class Category:
    family: str
    name: str
    aliases: frozenset[str] = field(default_factory=frozenset)

    @property
    def canonical(self) -> str:
        return f"{self.family}%%{self.name}"


@dataclass(frozen=True)
class CategoryMatch:
    """Conveys how confidently `resolve_category` matched a raw string.

    `category` is None only when `confidence == "none"`. A "fuzzy" match is
    a *suggestion* only -- callers must never treat it as authoritative
    without asking for confirmation first (the maintainer wants near-synonym
    federation, but always with confirmation, never guessed silently --
    issue #127)."""

    category: Category | None
    confidence: Confidence
    score: float
    matched_text: str | None = None
    source: str | None = None


_REGISTRY: dict[str, Category] = {}


def register(category: Category, *, replace: bool = False) -> None:
    key = category.canonical
    if key in _REGISTRY and not replace:
        _LOGGER.error("Refusing to register category %r: already registered", key)
        raise ValueError(f"Category already registered: {key}")
    _REGISTRY[key] = category
    _LOGGER.info(
        "%s taxonomy category: %s (%d alias(es))",
        "Replaced" if replace else "Registered",
        key,
        len(category.aliases),
    )


def unregister(canonical: str) -> None:
    _REGISTRY.pop(canonical, None)


def get_category(canonical: str) -> Category:
    try:
        return _REGISTRY[canonical]
    except KeyError:
        _LOGGER.warning("Unknown category requested: %r", canonical)
        raise ValueError(f"Unknown category: {canonical}") from None


def all_categories() -> list[Category]:
    return sorted(_REGISTRY.values(), key=lambda category: (category.family, category.name))


def families() -> list[str]:
    return sorted({category.family for category in _REGISTRY.values()})


def add_alias(canonical: str, alias: str) -> Category:
    category = get_category(canonical)
    updated = dc_replace(category, aliases=category.aliases | {alias})
    register(updated, replace=True)
    return updated


def merge_categories(keep: str, absorb: str) -> Category:
    """Merges `absorb` into `keep`: `absorb`'s own name and aliases become
    aliases of `keep`, and `absorb` is removed from the registry. `keep`
    survives under its own canonical name -- callers pick which side of a
    maintainer-confirmed duplicate should be the one everything resolves to."""
    keep_category = get_category(keep)
    absorb_category = get_category(absorb)
    merged = dc_replace(
        keep_category,
        aliases=keep_category.aliases | absorb_category.aliases | {absorb_category.name},
    )
    register(merged, replace=True)
    unregister(absorb_category.canonical)
    return merged


def _normalize(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _split_hierarchical(raw: str) -> tuple[str, str] | None:
    for separator in ("%%", "/", ">"):
        if separator in raw:
            parts = [part for part in raw.split(separator) if part.strip()]
            if len(parts) >= 2:
                return parts[0], parts[1]
    return None


def _match_bare(text: str) -> tuple[Category, Confidence] | None:
    normalized = _normalize(text)
    for category in _REGISTRY.values():
        if _normalize(category.name) == normalized:
            return category, "exact"
    for category in _REGISTRY.values():
        if normalized in {_normalize(alias) for alias in category.aliases}:
            return category, "alias"
    return None


def _match_hierarchical(family_part: str, name_part: str) -> tuple[Category, Confidence] | None:
    normalized_family = _normalize(family_part)
    normalized_name = _normalize(name_part)
    candidates = [category for category in _REGISTRY.values() if _normalize(category.family) == normalized_family]
    for category in candidates:
        if _normalize(category.name) == normalized_name:
            return category, "exact"
    for category in candidates:
        if normalized_name in {_normalize(alias) for alias in category.aliases}:
            return category, "alias"
    # Unknown family prefix (e.g. a folder like "Unsorted/PsyTrance") --
    # still resolve on the subcategory part alone rather than giving up.
    return _match_bare(name_part)


def _try_exact(raw: str, source: str) -> CategoryMatch | None:
    hierarchical = _split_hierarchical(raw)
    found = _match_hierarchical(*hierarchical) if hierarchical is not None else _match_bare(raw)
    if found is None:
        return None
    category, confidence = found
    return CategoryMatch(category=category, confidence=confidence, score=100.0, matched_text=raw, source=source)


def _fuzzy_choices() -> dict[str, Category]:
    choices: dict[str, Category] = {}
    for category in _REGISTRY.values():
        choices.setdefault(category.name, category)
        choices.setdefault(category.canonical, category)
        for alias in category.aliases:
            choices.setdefault(alias, category)
    return choices


def _try_fuzzy(raw: str, source: str) -> CategoryMatch | None:
    choices = _fuzzy_choices()
    if not choices:
        return None
    texts = list(choices.keys())
    result = process.extractOne(raw, texts, scorer=fuzz.WRatio)
    if result is None:
        return None
    matched_text, score, _ = result
    if score < FUZZY_THRESHOLD:
        return None
    return CategoryMatch(
        category=choices[matched_text],
        confidence="fuzzy",
        score=float(score),
        matched_text=matched_text,
        source=source,
    )


def resolve_category(
    raw_genre: str | None,
    folder_hint: str | None = None,
    crate_hint: str | None = None,
) -> CategoryMatch:
    """Resolves a track's category, weighing the crate/folder hierarchy the
    maintainer already curates by hand over the raw TCON tag, since real
    files show the tag alone is often unreliable (tracks filed under
    Tek/PsyTrance carrying TCON="House"/"Techno"/"Other" -- issue #127's
    investigation). Tries an exact/alias match against each hint in turn
    (crate, then folder, then the raw tag). Only once none of them match
    does it fall back to the single best fuzzy suggestion across all three
    -- confidence="fuzzy" -- which is a suggestion only and must never be
    applied without confirmation."""
    candidates = [
        (crate_hint, "crate"),
        (folder_hint, "folder"),
        (raw_genre, "genre"),
    ]
    candidates = [(text, source) for text, source in candidates if text]
    for text, source in candidates:
        match = _try_exact(text, source)
        if match is not None:
            return match
    best: CategoryMatch | None = None
    for text, source in candidates:
        candidate_match = _try_fuzzy(text, source)
        if candidate_match is not None and (best is None or candidate_match.score > best.score):
            best = candidate_match
    if best is not None:
        return best
    return CategoryMatch(category=None, confidence="none", score=0.0)
