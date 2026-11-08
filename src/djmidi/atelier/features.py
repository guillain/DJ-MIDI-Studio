"""One `Feature` per physical control, channel and layer of a registered
controller, derived from its catalog profile (static entries plus every
pad-bank variant).

A feature carries what the raw messages don't say: a stable, readable id
(``deck.play-pause@1``), a kind (button, pad, knob, fader, jog -- the same
vocabulary the layout views draw), the deck it belongs to, its SHIFT layer
and pad bank, the message it sends (`FeatureInput`) and, for a note, the
message that drives its LED (`LedOutput`).

LED data: no catalog records LED addresses, so a note's LED is *assumed*
to answer on the same channel and note it sends -- Serato's own convention
for nearly every mapping -- and marked ``verified=False`` with its source,
so the GUI can say so (decision 6 of issue #413). Values are on 127 / off
0; colour palettes are a later step.

The id leaves the note number out on purpose: a catalog fix to a control's
note must not orphan the macros and scenes that name it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from djmidi import catalog
from djmidi.catalog.codegen import definition_entries
from djmidi.gui.layout import PAD_BANK_RE, is_shift_variant, visual_kind_for

NOTE = "NOTE"
CC = "CC"
ASSUMED_LED_SOURCE = "assumed: LED note = input note"

_DECK_IN_NAME = re.compile(r"\bDeck\s+([1-4A-D])\b", re.IGNORECASE)
_DECK_LETTERS = {"A": 1, "B": 2, "C": 3, "D": 4}
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class FeatureInput:
    """The message the control sends: a note (Note On / Off) or a CC."""

    kind: str  # NOTE or CC
    channel: int  # 1-16
    number: int  # 0-127


@dataclass(frozen=True)
class LedOutput:
    """The message that lights the control's LED (a Note On whose velocity
    is the LED value)."""

    channel: int
    note: int
    on_value: int = 127
    off_value: int = 0
    verified: bool = False
    source: str = ASSUMED_LED_SOURCE
    # (value, colour name) pairs seen on the hardware (`atelier.led_data`).
    colours: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class Feature:
    id: str
    controller: str
    section: str
    name: str
    kind: str  # button / pad / knob / fader / jog
    deck: int | None
    shift: bool
    bank: str | None  # the pad bank, e.g. "PAD MODE 2", or None
    input: FeatureInput
    led: LedOutput | None

    @property
    def label(self) -> str:
        """The catalog name, plus the channel when it says no deck."""
        return self.name if self.deck is not None else f"{self.name} (ch {self.input.channel})"


# Symbols some catalogs name controls with ("<", ">", "1/2X", "+SHIFT"),
# spelled out so their ids stay readable and distinct.
_SYMBOLS = {"<": " lt ", ">": " gt ", "+": " plus ", "/": " slash ", "&": " and ", "#": " number "}


def _slug(text: str) -> str:
    for symbol, word in _SYMBOLS.items():
        text = text.replace(symbol, word)
    return _SLUG.sub("-", text.casefold()).strip("-") or "control"


def feature_id(section: str, name: str, channel: int) -> str:
    return f"{_slug(section)}.{_slug(name)}@{channel}"


def _deck(name: str, channel: str, channels: tuple[str, ...]) -> int | None:
    match = _DECK_IN_NAME.search(name)
    if match:
        token = match.group(1).upper()
        return _DECK_LETTERS.get(token) or int(token)
    if len(channels) > 1:
        ordered = sorted(channels, key=lambda text: int(text) if text.isdigit() else 0)
        return ordered.index(channel) + 1 if ordered.index(channel) < 4 else None
    return None


def _bank(name: str) -> str | None:
    match = PAD_BANK_RE.search(name)
    return match.group(1).strip("()") if match else None


# controller -> (the definition object it was built from and the LED data
# file's mtime, its features): a re-registered controller (Controller Setup,
# an installed profile) or a new LED probe result rebuilds the entry.
_CACHE: dict[str, tuple[object, tuple[Feature, ...]]] = {}


def features_for(controller: str) -> tuple[Feature, ...]:
    """Every feature of a registered controller, in catalog order; the same
    raw trigger is listed once (first entry wins). Cached per definition."""
    definition = catalog.get_definition(controller)
    stamp = (definition, _led_data_stamp(controller))
    cached = _CACHE.get(controller)
    if cached is not None and cached[0][0] is definition and cached[0][1] == stamp[1]:
        return cached[1]
    features = _build_features(controller, definition)
    _CACHE[controller] = (stamp, features)
    return features


def _led_data_stamp(controller: str) -> float | None:
    from djmidi.atelier.led_data import led_file

    try:
        return led_file(controller).stat().st_mtime
    except OSError:
        return None


def _led_output(record, channel: int, number: int) -> LedOutput:
    if record is None:
        return LedOutput(channel=channel, note=number)
    return LedOutput(
        channel=record.channel,
        note=record.note,
        on_value=record.on_value,
        off_value=record.off_value,
        verified=True,
        source=record.source or "LED probe",
        colours=tuple(sorted(record.colours.items())),
    )


def _build_features(controller: str, definition) -> tuple[Feature, ...]:
    from djmidi.atelier.led_data import load_led_data

    probed = load_led_data(controller)
    features: list[Feature] = []
    seen_triggers: set[tuple[str, int, int]] = set()
    seen_ids: set[str] = set()
    for entry in definition_entries(definition):
        if entry.section.upper().startswith("MIDI-OUT") or not entry.data1.isdigit():
            continue
        number = int(entry.data1)
        for channel_text in entry.channels:
            if not channel_text.isdigit():
                continue
            channel = int(channel_text)
            trigger = (entry.note_or_cc, channel, number)
            if trigger in seen_triggers:
                continue
            seen_triggers.add(trigger)
            identifier = feature_id(entry.section, entry.name, channel)
            suffix = 2
            while identifier in seen_ids:  # same name on two numbers of one channel
                identifier = f"{feature_id(entry.section, entry.name, channel)}#{suffix}"
                suffix += 1
            seen_ids.add(identifier)
            is_note = entry.note_or_cc == NOTE
            features.append(
                Feature(
                    id=identifier,
                    controller=controller,
                    section=entry.section,
                    name=entry.name,
                    kind=visual_kind_for(entry.section, entry.name),
                    deck=_deck(entry.name, channel_text, entry.channels),
                    shift=is_shift_variant(entry),
                    bank=_bank(entry.name),
                    input=FeatureInput(kind=entry.note_or_cc, channel=channel, number=number),
                    led=_led_output(probed.get(identifier), channel, number) if is_note else None,
                )
            )
    return tuple(features)


def feature_by_id(controller: str, identifier: str) -> Feature | None:
    return next((feature for feature in features_for(controller) if feature.id == identifier), None)


def feature_for_message(controller: str, event_type: str, channel: int, number: int) -> Feature | None:
    """The feature a raw message belongs to: a Note On / Off to a NOTE
    feature, a Control Change to a CC one."""
    kind = CC if event_type == "Control Change" else NOTE if event_type in ("Note On", "Note Off") else None
    if kind is None:
        return None
    return next(
        (
            feature
            for feature in features_for(controller)
            if feature.input.kind == kind and feature.input.channel == channel and feature.input.number == number
        ),
        None,
    )


__all__ = [
    "ASSUMED_LED_SOURCE",
    "CC",
    "NOTE",
    "Feature",
    "FeatureInput",
    "LedOutput",
    "feature_by_id",
    "feature_for_message",
    "feature_id",
    "features_for",
]
