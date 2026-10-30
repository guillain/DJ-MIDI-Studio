"""Generate a Mixxx MIDI mapping from a controller profile (Qt-free).

The other direction of ``software/mixxx.py``: given a profile's buttons
and pads (what this app knows about a controller) and a Mixxx function
picked for each, write a ``.midi.xml`` Mixxx loads as is.

**Vocabulary.** Only Mixxx deck controls that Mixxx's own mappings bind to a
Note On button, without a script, in at least four of the 142 mappings
bundled with Mixxx 2.5 (counted read-only, nothing copied). The number of
mappings using each one is in :data:`FUNCTIONS`, as the evidence. Every
binding gets ``<options><normal/></options>``, the form most of those
mappings use for each key.

**Releases.** Pioneer-style controllers release a button with a Note On at
velocity 0, which reaches the same binding. A controller that sends a real
Note Off needs ``note_off=True``: each Note On binding then gets its
``0x8n`` twin, as some Mixxx mappings do. The profile can't tell which.

:func:`suggest_function` offers a function for a control from its name
(PLAY/PAUSE → ``play``, ``Pad 3 (HOT CUE)`` → ``hotcue_3_activate``…);
the user reviews every suggestion before saving.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from xml.sax.saxutils import escape

from djmidi import catalog
from djmidi.catalog.codegen import definition_entries
from djmidi.gui.layout import is_shift_variant
from djmidi.i18n import QT_TRANSLATE_NOOP

MAX_DECKS = 4
GENERATOR = "DJ MIDI Studio"


@dataclass(frozen=True)
class MixxxFunction:
    key: str
    label: str
    mappings: int  # how many of Mixxx 2.5's 142 bundled mappings bind it this way


_HOT_CUE = QT_TRANSLATE_NOOP("MixxxExport", "Hot cue {number}")
_HOT_CUE_CLEAR = QT_TRANSLATE_NOOP("MixxxExport", "Hot cue {number}: clear")


def function_label(function: MixxxFunction, translate=None) -> str:
    """'Play / pause (play)': the label (translated when `translate` is
    given) and the Mixxx key, which stays as Mixxx spells it."""
    label = function.label
    if translate is not None:
        number = re.search(r"\d+", function.key)
        if function.key.startswith("hotcue_") and number:
            template = _HOT_CUE_CLEAR if function.key.endswith("_clear") else _HOT_CUE
            label = translate(template).format(number=number.group())
        else:
            label = translate(label)
    return f"{label} ({function.key})"


def _hotcues() -> list[MixxxFunction]:
    activate = {1: 27, 2: 27, 3: 25, 4: 23, 5: 9, 6: 7, 7: 6, 8: 6}
    clear = {1: 20, 2: 20, 3: 18, 4: 17, 5: 8, 6: 7, 7: 6, 8: 6}
    functions = []
    for number in range(1, 9):
        functions.append(MixxxFunction(f"hotcue_{number}_activate", _HOT_CUE.format(number=number), activate[number]))
    for number in range(1, 9):
        functions.append(MixxxFunction(f"hotcue_{number}_clear", _HOT_CUE_CLEAR.format(number=number), clear[number]))
    return functions


FUNCTIONS: tuple[MixxxFunction, ...] = (
    MixxxFunction("play", QT_TRANSLATE_NOOP("MixxxExport", "Play / pause"), 61),
    MixxxFunction("cue_default", QT_TRANSLATE_NOOP("MixxxExport", "Cue"), 56),
    MixxxFunction("cue_gotoandplay", QT_TRANSLATE_NOOP("MixxxExport", "Cue: go to and play"), 7),
    MixxxFunction("start_stop", QT_TRANSLATE_NOOP("MixxxExport", "Start / stop"), 5),
    MixxxFunction("sync_enabled", QT_TRANSLATE_NOOP("MixxxExport", "Sync (lock)"), 23),
    MixxxFunction("beatsync", QT_TRANSLATE_NOOP("MixxxExport", "Beat sync (one shot)"), 32),
    MixxxFunction("keylock", QT_TRANSLATE_NOOP("MixxxExport", "Key lock"), 29),
    MixxxFunction("quantize", QT_TRANSLATE_NOOP("MixxxExport", "Quantize"), 14),
    MixxxFunction("slip_enabled", QT_TRANSLATE_NOOP("MixxxExport", "Slip"), 5),
    MixxxFunction("reverse", QT_TRANSLATE_NOOP("MixxxExport", "Reverse"), 18),
    MixxxFunction("pfl", QT_TRANSLATE_NOOP("MixxxExport", "Headphone cue (PFL)"), 56),
    MixxxFunction("LoadSelectedTrack", QT_TRANSLATE_NOOP("MixxxExport", "Load selected track"), 42),
    MixxxFunction("eject", QT_TRANSLATE_NOOP("MixxxExport", "Eject"), 4),
    MixxxFunction("loop_in", QT_TRANSLATE_NOOP("MixxxExport", "Loop in"), 26),
    MixxxFunction("loop_out", QT_TRANSLATE_NOOP("MixxxExport", "Loop out"), 26),
    MixxxFunction("reloop_toggle", QT_TRANSLATE_NOOP("MixxxExport", "Reloop / exit"), 8),
    MixxxFunction("reloop_exit", QT_TRANSLATE_NOOP("MixxxExport", "Reloop exit"), 24),
    MixxxFunction("beatloop_4_toggle", QT_TRANSLATE_NOOP("MixxxExport", "4-beat loop"), 9),
    MixxxFunction("loop_halve", QT_TRANSLATE_NOOP("MixxxExport", "Loop ½"), 21),
    MixxxFunction("loop_double", QT_TRANSLATE_NOOP("MixxxExport", "Loop ×2"), 20),
    MixxxFunction("back", QT_TRANSLATE_NOOP("MixxxExport", "Rewind (hold)"), 32),
    MixxxFunction("fwd", QT_TRANSLATE_NOOP("MixxxExport", "Fast forward (hold)"), 32),
    MixxxFunction("rate_temp_down", QT_TRANSLATE_NOOP("MixxxExport", "Pitch bend −"), 31),
    MixxxFunction("rate_temp_up", QT_TRANSLATE_NOOP("MixxxExport", "Pitch bend +"), 30),
    *_hotcues(),
)
_BY_KEY = {function.key: function for function in FUNCTIONS}


@dataclass(frozen=True)
class ProfileButton:
    """One raw trigger of a profile: a button or pad on one channel."""

    section: str
    name: str
    kind: str  # "NOTE" / "CC"
    channel: int  # 1-based
    data1: int
    deck: int  # suggested deck, 1..MAX_DECKS

    @property
    def label(self) -> str:
        return f"{self.name}"


@dataclass(frozen=True)
class Assignment:
    button: ProfileButton
    key: str
    deck: int


_DECK_IN_NAME = re.compile(r"\bDeck\s+(\d)\b", re.IGNORECASE)
_PAD = re.compile(r"\bPad\s+(\d+)\b", re.IGNORECASE)
_SECOND_GESTURE = re.compile(r"LONG PRESS|DOUBLE[- ]?CLICK")


def _deck_guess(name: str, channel: str, channels: Sequence[str]) -> int:
    match = _DECK_IN_NAME.search(name)
    if match:
        return max(1, min(int(match.group(1)), MAX_DECKS))
    ordered = sorted(channels, key=lambda text: int(text) if text.isdigit() else 0)
    position = ordered.index(channel) if channel in ordered else 0
    return min(position + 1, MAX_DECKS)


def profile_buttons(controller: str, include_shift: bool = False) -> list[ProfileButton]:
    """Every button/pad trigger of a registered profile (pad grids expanded),
    one per channel, SHIFT layers left out unless asked."""
    definition = catalog.get_definition(controller)
    buttons: list[ProfileButton] = []
    seen: set[tuple[int, str, int]] = set()
    for entry in definition_entries(definition):
        if not include_shift and is_shift_variant(entry):
            continue
        if entry.section.upper().startswith("MIDI-OUT"):
            continue
        for channel in entry.channels:
            if not channel.isdigit() or not entry.data1.isdigit():
                continue
            key = (int(channel), entry.note_or_cc, int(entry.data1))
            if key in seen:
                continue
            seen.add(key)
            buttons.append(
                ProfileButton(
                    section=entry.section,
                    name=entry.name,
                    kind=entry.note_or_cc,
                    channel=int(channel),
                    data1=int(entry.data1),
                    deck=_deck_guess(entry.name, channel, entry.channels),
                )
            )
    return buttons


_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), key)
    for pattern, key in (
        (r"^PLAY", "play"),
        (r"^CUE$|^CUE\b(?!/)", "cue_default"),
        (r"^(BEAT )?SYNC$", "sync_enabled"),
        (r"^(KEY ?LOCK|MASTER TEMPO)$", "keylock"),
        (r"^QUANTIZE$", "quantize"),
        (r"^SLIP$", "slip_enabled"),
        (r"^(HEADPHONE )?CUE \(PFL\)$|^PFL$", "pfl"),
        (r"^LOAD\b", "LoadSelectedTrack"),
        (r"^LOOP IN\b", "loop_in"),
        (r"^LOOP OUT\b", "loop_out"),
        (r"^RELOOP", "reloop_toggle"),
        (r"^4 ?BEAT( LOOP)?\b", "beatloop_4_toggle"),
        (r"^(1/2X|LOOP HALF|LOOP 1/2)$", "loop_halve"),
        (r"^(2X|LOOP DOUBLE|LOOP X2)$", "loop_double"),
        (r"^REVERSE$", "reverse"),
    )
)


def suggest_function(button: ProfileButton) -> str | None:
    """A Mixxx key for a control, from its name; None when unsure."""
    name = button.name.upper().strip()
    if _SECOND_GESTURE.search(name):
        return None  # a long press / double click shares the button's note
    pad = _PAD.search(button.name)
    if pad is not None:
        number = int(pad.group(1))
        if ("HOT CUE" in name or "HOTCUE" in name) and 1 <= number <= 8:
            return f"hotcue_{number}_activate"
        return None
    for pattern, key in _RULES:
        if pattern.search(name):
            return key
    return None


def _status(kind: str, channel: int, note_off: bool = False) -> str:
    base = 0xB0 if kind == "CC" else (0x80 if note_off else 0x90)
    return f"0x{base + channel - 1:02X}"


def build_mixxx_mapping(
    name: str,
    assignments: Iterable[Assignment],
    *,
    note_off: bool = False,
    author: str = GENERATOR,
) -> str:
    """The ``.midi.xml`` text for `assignments` (in order)."""
    lines = [
        "<?xml version='1.0' encoding='utf-8'?>",
        '<MixxxControllerPreset schemaVersion="1" mixxxVersion="2.4.0+">',
        "  <info>",
        f"    <name>{escape(name)}</name>",
        f"    <author>{escape(author)}</author>",
        f"    <description>Generated by {GENERATOR} from its {escape(name)} controller profile.</description>",
        "  </info>",
        f'  <controller id="{escape(re.sub(r"[^A-Za-z0-9]+", "", name) or "Controller")}">',
        "    <scriptfiles/>",
        "    <controls>",
    ]
    for assignment in assignments:
        if assignment.key not in _BY_KEY:
            raise ValueError(f"Not a Mixxx function this app writes: {assignment.key}")
        if not 1 <= assignment.deck <= MAX_DECKS:
            raise ValueError(f"Deck {assignment.deck} is out of range")
        button = assignment.button
        statuses = [_status(button.kind, button.channel)]
        if note_off and button.kind == "NOTE":
            statuses.append(_status(button.kind, button.channel, note_off=True))
        for status in statuses:
            lines += [
                f"      <!-- {escape(button.section)}: {escape(button.name).replace('--', '- -')} -->",
                "      <control>",
                f"        <group>[Channel{assignment.deck}]</group>",
                f"        <key>{assignment.key}</key>",
                f"        <status>{status}</status>",
                f"        <midino>0x{button.data1:02X}</midino>",
                "        <options>",
                "          <normal/>",
                "        </options>",
                "      </control>",
            ]
    lines += ["    </controls>", "    <outputs/>", "  </controller>", "</MixxxControllerPreset>", ""]
    return "\n".join(lines)


__all__ = [
    "FUNCTIONS",
    "MAX_DECKS",
    "Assignment",
    "MixxxFunction",
    "ProfileButton",
    "build_mixxx_mapping",
    "function_label",
    "profile_buttons",
    "suggest_function",
]
