"""Which copy of a duplicate group to keep, and why (issue #458).

For each copy the facts that matter to a DJ are read once (stream header
and tags, never the audio): lossless or not, bitrate, sample rate, how many
of the managed tags are filled, whether it lies inside the library's roots,
and which DJ software stored its own data in it (cue points, loops,
analysis). :func:`suggest_keep` ranks them -- audio quality first, then
DJ-software data, location and tags -- and says, in words, why the
suggested copy wins, and which other copy carries DJ-software data the
suggested one lacks (dropping it would lose cue points). The DJ confirms
or picks another copy: nothing here moves, deletes or writes a file.
Qt-free.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated

LOSSLESS_SUFFIXES = frozenset({".flac", ".wav", ".wave", ".aif", ".aiff", ".alac"})
_TAG_FIELDS = ("title", "artist", "album", "genre", "bpm", "key", "comment", "rating", "energy")


@dataclass(frozen=True)
class CopyFacts:
    path: str
    lossless: bool = False
    bitrate: int | None = None  # bits/s
    sample_rate: int | None = None
    duration: float | None = None
    filled_tags: int = 0
    in_roots: bool = False
    dj_data: tuple[str, ...] = ()  # e.g. ("Serato", "Traktor")


@dataclass(frozen=True)
class KeepSuggestion:
    keep: str  # the path to keep
    reasons: tuple[str, ...]  # why it wins, translated
    # path -> DJ software whose data that copy carries and the kept one lacks
    losses: dict[str, tuple[str, ...]]


def _inside(path: str, roots: Iterable[str]) -> bool:
    resolved = Path(path)
    for root in roots:
        try:
            resolved.relative_to(Path(root))
        except ValueError:
            continue
        return True
    return False


def read_copy_facts(path: str, roots: Iterable[str] = (), opener: Callable | None = None) -> CopyFacts:
    """Facts of one file; an unreadable file gets only its path facts."""
    import mutagen

    from djmidi.library.metadata import dj_software_data, metadata_from_audio

    lossless = Path(path).suffix.lower() in LOSSLESS_SUFFIXES
    in_roots = _inside(path, roots)
    try:
        audio = (opener or mutagen.File)(path)
    except (mutagen.MutagenError, OSError, ValueError):
        audio = None
    if audio is None:
        return CopyFacts(path, lossless=lossless, in_roots=in_roots)
    info = getattr(audio, "info", None)
    meta = metadata_from_audio(audio)
    return CopyFacts(
        path=path,
        lossless=lossless,
        bitrate=int(getattr(info, "bitrate", 0) or 0) or None,
        sample_rate=int(getattr(info, "sample_rate", 0) or 0) or None,
        duration=getattr(info, "length", None) or None,
        filled_tags=sum(getattr(meta, field) not in (None, "") for field in _TAG_FIELDS),
        in_roots=in_roots,
        dj_data=dj_software_data(audio),
    )


def _rank(facts: CopyFacts) -> tuple:
    return (
        facts.lossless,
        facts.bitrate or 0,
        facts.sample_rate or 0,
        len(facts.dj_data),
        facts.in_roots,
        facts.filled_tags,
    )


def _kbps(bitrate: int | None) -> str:
    return f"{round(bitrate / 1000)} kbps" if bitrate else "?"


def suggest_keep(copies: Sequence[CopyFacts], translate: Translate = untranslated) -> KeepSuggestion | None:
    """The best copy, or None for fewer than two. Ties keep the first one
    (the group's order)."""
    if len(copies) < 2:
        return None
    best = max(copies, key=_rank)  # max keeps the first of equals
    others = [facts for facts in copies if facts is not best]
    reasons: list[str] = []
    if best.lossless and not all(other.lossless for other in others):
        reasons.append(translate(QT_TRANSLATE_NOOP("KeepCopy", "lossless")))
    elif best.bitrate and any((other.bitrate or 0) < best.bitrate for other in others):
        worst = min((other.bitrate or 0) for other in others)
        reasons.append(
            translate(QT_TRANSLATE_NOOP("KeepCopy", "higher bitrate ({best} vs {other})")).format(
                best=_kbps(best.bitrate), other=_kbps(worst or None)
            )
        )
    elif best.sample_rate and any((other.sample_rate or 0) < best.sample_rate for other in others):
        reasons.append(translate(QT_TRANSLATE_NOOP("KeepCopy", "higher sample rate")))
    if best.dj_data and any(len(other.dj_data) < len(best.dj_data) for other in others):
        reasons.append(
            translate(QT_TRANSLATE_NOOP("KeepCopy", "holds {software} data (cue points, analysis)")).format(
                software=" + ".join(best.dj_data)
            )
        )
    if best.in_roots and not all(other.in_roots for other in others):
        reasons.append(translate(QT_TRANSLATE_NOOP("KeepCopy", "inside your library folders")))
    if any(other.filled_tags < best.filled_tags for other in others):
        reasons.append(
            translate(QT_TRANSLATE_NOOP("KeepCopy", "more tags filled ({count})")).format(count=best.filled_tags)
        )
    if not reasons:
        reasons.append(translate(QT_TRANSLATE_NOOP("KeepCopy", "the copies are equivalent: the first one")))
    losses = {
        other.path: missing
        for other in others
        if (missing := tuple(software for software in other.dj_data if software not in best.dj_data))
    }
    return KeepSuggestion(best.path, tuple(reasons), losses)


__all__ = ["LOSSLESS_SUFFIXES", "CopyFacts", "KeepSuggestion", "read_copy_facts", "suggest_keep"]
