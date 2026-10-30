"""Qt-free core of the full-screen Stage Mode (issue #230).

Stage Mode shows only a Controller Emulator and a compact Live Monitor,
large and high-contrast, for reading from a distance on stage. The window
itself lives in ``gui/stage_window.py``; this module holds the parts that
don't need a ``QApplication``: turning a live ``MidiEvent`` into one short,
readable line, the bounded list of recent lines the compact monitor
shows (newest first), and the prepared set's panel (:func:`stage_set_view`,
issue #366) with its next-track suggestions (:func:`suggest_next_tracks`),
so all can be tested without Qt.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from djmidi import catalog
from djmidi.i18n import QT_TRANSLATE_NOOP, Translate, untranslated
from djmidi.library.playlist import PlaylistTrack, find_compatible_tracks
from djmidi.library.set_prep import (
    DEFAULT_BPM_TOLERANCE_PCT,
    STATUS_OK,
    SetTrack,
    Transition,
)
from djmidi.midi_io import MidiEvent

# How many recent events the compact monitor keeps. Deliberately small: at
# stage font sizes only a handful of lines fit, and older traffic belongs in
# the full Live Monitor dock, not here.
DEFAULT_MAX_LINES = 6

_SEPARATOR = " · "

# English templates, translated by the caller (issue #337).
_ON = QT_TRANSLATE_NOOP("Stage", "ON")
_OFF = QT_TRANSLATE_NOOP("Stage", "OFF")
_RAW_TRIGGER = QT_TRANSLATE_NOOP("Stage", "Ch {channel} {event_type} {data1}")


def hits_for_port(hits: Iterable[catalog.ControlInfo], port: str) -> list[catalog.ControlInfo]:
    """Keep only the catalog hits whose controller name appears in the
    source port's name -- the same disambiguation the Live Monitor log
    applies, since ``catalog.lookup()`` is controller-agnostic and the same
    raw trigger often means something on several registered controllers.
    An unknown port (empty string) keeps every hit."""
    hits = list(hits)
    if not port:
        return hits
    source = port.casefold()
    return [hit for hit in hits if hit.controller.casefold() in source]


def _value_text(event: MidiEvent, translate: Translate) -> str:
    if event.event_type == "Note Off":
        return translate(_OFF)
    if event.event_type == "Note On":
        return translate(_ON) if event.data2 not in ("", "0") else translate(_OFF)
    return event.data2


def format_stage_line(
    event: MidiEvent, hits: Iterable[catalog.ControlInfo] = (), translate: Translate = untranslated
) -> str:
    """One short line for the compact stage monitor: direction, then the
    physical control's name(s) when the catalog knows it, else the raw
    trigger, then the value (ON/OFF for a note, the 0-127 value for a CC).
    The port is left out on purpose -- at stage font sizes it would push
    the control name off the line, and the full Live Monitor keeps it.
    `translate` turns ON/OFF and the raw-trigger wording into the interface
    language; the direction (IN/OUT) is shown as the Live Monitor shows it."""
    names: list[str] = []
    for hit in hits_for_port(hits, event.port):
        label = f"{hit.controller} {hit.name}"
        if label not in names:
            names.append(label)
    what = "; ".join(names) or translate(_RAW_TRIGGER).format(
        channel=event.channel, event_type=event.event_type, data1=event.data1
    )
    return _SEPARATOR.join((event.direction.upper(), what, _value_text(event, translate)))


class StageLog:
    """Bounded, newest-first list of stage monitor lines."""

    def __init__(self, max_lines: int = DEFAULT_MAX_LINES) -> None:
        if max_lines < 1:
            raise ValueError("max_lines must be at least 1")
        self._lines: deque[str] = deque(maxlen=max_lines)

    @property
    def max_lines(self) -> int:
        return self._lines.maxlen or 0

    def add(self, line: str) -> None:
        self._lines.appendleft(line)

    def lines(self) -> list[str]:
        return list(self._lines)

    def clear(self) -> None:
        self._lines.clear()


# --- the prepared set on stage (issue #366) ---------------------------------

_SET_POSITION = QT_TRANSLATE_NOOP("Stage", "Set {position}/{total}")
_NEXT = QT_TRANSLATE_NOOP("Stage", "Next: {track}")
_LAST = QT_TRANSLATE_NOOP("Stage", "Last track of the set")
_COMPATIBLE = QT_TRANSLATE_NOOP("Stage", "Transition OK")
_BPM_CHANGE = QT_TRANSLATE_NOOP("Stage", "BPM {change}")
_ENERGY = QT_TRANSLATE_NOOP("Stage", "energy {energy}")


@dataclass(frozen=True)
class StageSetView:
    """What the Stage Mode set panel shows for one position of the set."""

    position: str
    current: str
    current_details: str
    next: str
    transition: str
    status: str  # set_prep.STATUS_* of the next transition, "" for the last track
    current_note: str = ""
    next_note: str = ""


def _details(track: SetTrack, translate: Translate) -> str:
    parts = []
    if track.bpm:
        parts.append(f"{track.bpm:g} BPM")
    if track.camelot_key:
        parts.append(track.camelot_key)
    if track.energy is not None:
        parts.append(translate(_ENERGY).format(energy=track.energy))
    return _SEPARATOR.join(parts)


def stage_set_view(
    tracks: Sequence[SetTrack], transitions: Sequence[Transition], index: int, translate: Translate = untranslated
) -> StageSetView | None:
    """The set panel for track `index` (clamped), or None for an empty set.
    The transition line is the mix into the next track: "Transition OK" with
    its BPM change, or the set preparation's own notes on what clashes."""
    if not tracks:
        return None
    index = max(0, min(index, len(tracks) - 1))
    track = tracks[index]
    position = translate(_SET_POSITION).format(position=index + 1, total=len(tracks))
    if index + 1 >= len(tracks):
        return StageSetView(position, track.label, _details(track, translate), translate(_LAST), "", "",
                            track.note or "")  # fmt: skip
    following = tracks[index + 1]
    transition = transitions[index] if index < len(transitions) else None
    next_text = translate(_NEXT).format(track=following.label)
    next_details = _details(following, translate)
    if next_details:
        next_text = f"{next_text}{_SEPARATOR}{next_details}"
    notes = (track.note or "", following.note or "")
    if transition is None:
        return StageSetView(position, track.label, _details(track, translate), next_text, "", "", *notes)
    if transition.status == STATUS_OK:
        text = translate(_COMPATIBLE)
        if transition.bpm_change_pct is not None:
            change = translate(_BPM_CHANGE).format(change=f"{transition.bpm_change_pct:+.1f} %")
            text = f"{text}{_SEPARATOR}{change}"
    else:
        text = _SEPARATOR.join(transition.issues)
    return StageSetView(position, track.label, _details(track, translate), next_text, text, transition.status, *notes)


# How many library tracks the set panel suggests.
SUGGESTION_LIMIT = 5


def suggest_next_tracks(
    current: SetTrack,
    candidates: Iterable[SetTrack],
    exclude: Collection[str] = (),
    bpm_tolerance_pct: float = DEFAULT_BPM_TOLERANCE_PCT,
    limit: int = SUGGESTION_LIMIT,
) -> list[SetTrack]:
    """Library tracks that mix well after `current` -- BPM within the
    tolerance and a compatible Camelot key, closest BPM first -- for when
    the night leaves the prepared set. Empty when `current` lacks a BPM or a
    key; tracks in `exclude` (the set itself), missing files and tracks
    without BPM/key are never suggested."""
    if not current.bpm or not current.camelot_key:
        return []
    by_path: dict[str, SetTrack] = {}
    for track in candidates:
        if track.indexed and track.bpm and track.camelot_key and track.path not in exclude:
            by_path.setdefault(track.path, track)
    seed = PlaylistTrack(current.path, bpm=current.bpm, camelot_key=current.camelot_key)
    pool = [PlaylistTrack(path, bpm=track.bpm, camelot_key=track.camelot_key) for path, track in sorted(by_path.items())]
    matches = find_compatible_tracks(seed, pool, bpm_tolerance_pct)
    return [by_path[match.identifier] for match in matches[:limit]]


def suggestion_line(track: SetTrack, translate: Translate = untranslated) -> str:
    details = _details(track, translate)
    return f"{track.label}{_SEPARATOR}{details}" if details else track.label
