"""Live jog-wheel rotation resolution.

Continuous jog turn is deliberately **out of catalog scope** (see
``catalog/__init__.py`` -- the catalog only carries discrete press/toggle
controls), so a live jog CC does *not* resolve through ``catalog.lookup()``
the way a pad or button hit does. This module carries the minimal
per-controller data needed to still animate the jog glyph from live MIDI:
which ``(channel, CC data1)`` pairs a controller's jog turn uses, and how to
turn its relative value into a signed tick delta.

Data source: the official **MIDI Message List** PDF bundled in
``controllers/hardware/<vendor>/<Model>/``, read from the *rendered table* (not ``pdftotext``,
whose column order scrambles multi-column rows). Only controllers with a
``"Jog wheel"`` entry in ``gui/geometry.CONTROL_GEOMETRY`` -- i.e. a jog
glyph actually drawn somewhere -- are worth listing here.

Every controller so far uses the **0x40-centred relative** encoding: a
value above 0x40 is a forward (clockwise) step, below 0x40 is backward, the
magnitude is the distance from 0x40 (``decode_jog_delta``). The MIDI
channel is always the deck channel (DECK 1..4 = channel "1".."4").

===========  ===========================================  ==================
Controller   Jog-turn CC data1 (hex)                       Source
===========  ===========================================  ==================
XDJ-XZ       platter 0x22 / 0x29(+SHIFT);                   MIDI Message
             wheel-side 0x21 / 0x26(+SHIFT)                 List E3, Fig 1
DDJ-1000     platter 0x21 / 0x29(+SEARCH) / 0x1F(+SHIFT)    MIDI Message
                                                            List E1
DDJ-FLX10    platter 0x22(Vinyl on) / 0x23(Vinyl off) /     MIDI Message
             0x29(+4 BEAT JUMP) / 0x1F(+SHIFT);             List E1, Fig D3
             wheel-side 0x21 / 0x26(+SHIFT)
DDJ-REV1     platter 0x22(Vinyl on) / 0x23(Vinyl off) /     MIDI Message
             0x1F(+SHIFT); wheel-side 0x21 / 0x26(+SHIFT)   List E1, Fig D3
DDJ-REV5     platter 0x22(Vinyl on) / 0x23(Vinyl off) /     MIDI Message
             0x1F(+SHIFT); wheel-side 0x21 / 0x26(+SHIFT)   List E1, Fig D3
DDJ-FLX4     platter 0x22 / 0x23 / 0x29(+SHIFT);            MIDI Message
             wheel-side 0x21                                List E1, Fig 1-4
DDJ-800      platter 0x22 / 0x23 / 0x29(+SEARCH) /          MIDI Message
             0x1F(+SHIFT); wheel-side 0x21 / 0x26(+SHIFT)   List E3, Fig D3
===========  ===========================================  ==================

**Hercules DJControl Inpulse 500** (issue #347) is the exception, read from
its "MIDI COMMANDS" sheet (pages 2 and 11, D1-16 / D2-16 "Jog-wheel",
300 DPI render): CC 0x09 (Vinyl off) / 0x0A (Vinyl on) on status 0xB1 / 0xB4
(+Shift) for deck 1 and 0xB2 / 0xB5 for deck 2 -- the sheet's 0-based
channel column says 1/4 and 2/5, so channels "2"/"5" are the left jog and
"3"/"6" the right one. Its encoding is **two's complement**, not
0x40-centred: "01 > 3F: CC Slow->Fast" (clockwise, +1..+63) and "7F > 40:
CCW Slow->Fast" (-1..-64) -- ``decode_twos_complement_delta``. The jog
*touch* (CC 0x08 on the same channels) is not a turn and isn't listed.

DDJ-FLX4 and DDJ-800 also draw both jogs (``"Jog wheel"`` / ``"Jog wheel
(R)"``) and resolve side-aware by deck channel: deck 2 (and 4 on the
DDJ-800) is the right jog.

XDJ-XZ has two physical jogs -- decks 1/3 on the left, 2/4 on the right
tray (the same split ``layout.py``'s ``_RIGHT_GRID_DECKS`` uses for the pad
grids) -- so it resolves side-aware to ``"Jog wheel"`` / ``"Jog wheel
(R)"``. DDJ-REV5 (issue #339) is the same: its jogs print "1/3" and "2/4". DDJ-1000, DDJ-FLX10 and DDJ-REV1 are also 2-deck, but their
schematics draw only the left deck, so every deck channel resolves to
their single ``"Jog wheel"`` marker.

Several of these CCs collide (e.g. 0x21 is used by all four on the deck
channel). ``jog_cell_keys_for_event`` returns *every* matching marker, and
each view spins only its own controller's -- the schematic shows one
controller, the emulator self-filters, the images overlay checks
``key[0]``.
"""

from __future__ import annotations

CellKey = tuple[str, str, str]

_JOG_CENTRE = 0x40

# Degrees a jog notch turns per relative MIDI tick. A jog turn is a stream
# of small +/-1..few deltas; this gain is cosmetic -- big enough that a
# flick of the wheel visibly spins the glyph, not a faithful reproduction
# of the platter's real angular resolution (~1440 ticks/rev). Lives here
# (not in gui/layout_view) so both layout_view and controller_image_view
# can read it without a circular import.
DEGREES_PER_TICK = 6.0

_DECK_CHANNELS = frozenset({"1", "2", "3", "4"})
_RIGHT_DECK_CHANNELS = frozenset({"2", "4"})  # XDJ-XZ right-tray decks

# Jog-turn CC data1 values (decimal strings, matching model.Control's
# convention) per controller. XDJ-XZ is the only one with two physical jogs
# to tell apart by deck channel.
_XDJ_XZ_JOG_DATA1 = frozenset({"33", "34", "38", "41"})  # 0x21/0x22/0x26/0x29
_DDJ_1000_JOG_DATA1 = frozenset({"31", "33", "41"})  # 0x1F/0x21/0x29
_DDJ_FLX10_JOG_DATA1 = frozenset({"31", "33", "34", "35", "38", "41"})
#                                  0x1F 0x21 0x22 0x23 0x26 0x29
_DDJ_REV1_JOG_DATA1 = frozenset({"31", "33", "34", "35", "38"})  # FLX10 minus 0x29
_DDJ_REV5_JOG_DATA1 = _DDJ_REV1_JOG_DATA1  # the same five CCs (its MIDI Message List, D3)

# Single-jog controllers: (data1 set, its one marker key).
_SINGLE_JOG_RULES: tuple[tuple[frozenset[str], CellKey], ...] = (
    (_DDJ_1000_JOG_DATA1, ("DDJ-1000", "DISPLAY", "Jog wheel")),
    (_DDJ_FLX10_JOG_DATA1, ("DDJ-FLX10", "DISPLAY", "Jog wheel")),
    (_DDJ_REV1_JOG_DATA1, ("DDJ-REV1", "DISPLAY", "Jog wheel")),
)

_XDJ_XZ_LEFT_KEY: CellKey = ("XDJ-XZ", "DISPLAY", "Jog wheel")
# The right-tray jog's schematic key carries layout._RIGHT_GRID_SUFFIX, the
# same way real_position_markers() keys the mirrored pad grid / DECK cluster.
_XDJ_XZ_RIGHT_KEY: CellKey = ("XDJ-XZ", "DISPLAY", "Jog wheel (R)")

# Two-jog controllers: (data1 set, left key for decks 1/3, right key for 2/4).
_TWO_JOG_RULES: tuple[tuple[frozenset[str], CellKey, CellKey], ...] = (
    (_XDJ_XZ_JOG_DATA1, _XDJ_XZ_LEFT_KEY, _XDJ_XZ_RIGHT_KEY),
    (
        _DDJ_REV5_JOG_DATA1,
        ("DDJ-REV5", "DISPLAY", "Jog wheel"),
        ("DDJ-REV5", "DISPLAY", "Jog wheel (R)"),
    ),
    # issue #338, DDJ-800 (MIDI Message List E3, Fig. D3): platter
    # 0x22 / 0x23 / 0x29(+SEARCH) / 0x1F(+SHIFT), wheel side 0x21 /
    # 0x26(+SHIFT); decks 1/3 left, 2/4 right.
    (
        frozenset({"31", "33", "34", "35", "38", "41"}),
        ("DDJ-800", "DISPLAY", "Jog wheel"),
        ("DDJ-800", "DISPLAY", "Jog wheel (R)"),
    ),
)

# issue #338, DDJ-FLX4 (MIDI Message List E1, Fig. 1-4): platter
# 0x22(Vinyl on) / 0x23(Vinyl off) / 0x29(+SHIFT), wheel side 0x21
# (+SHIFT too). Only two deck channels: 1 = left jog, 2 = right.
_DDJ_FLX4_JOG_DATA1 = frozenset({"33", "34", "35", "41"})
_DDJ_FLX4_JOG_KEYS: dict[str, CellKey] = {
    "1": ("DDJ-FLX4", "DISPLAY", "Jog wheel"),
    "2": ("DDJ-FLX4", "DISPLAY", "Jog wheel (R)"),
}


# issue #347, Hercules DJControl Inpulse 500 (MIDI COMMANDS sheet, D1-16 /
# D2-16): CC 0x09 / 0x0A, deck channel or its SHIFT channel, two's
# complement. Its own channels, so its own rule: channel 2 is the *left* jog
# here, unlike the 1-4 deck-channel controllers above.
_INPULSE_500 = "Hercules DJControl Inpulse 500"
_INPULSE_500_JOG_DATA1 = frozenset({"9", "10"})
_INPULSE_500_JOG_KEYS: dict[str, CellKey] = {
    "2": (_INPULSE_500, "DISPLAY", "Jog wheel"),
    "5": (_INPULSE_500, "DISPLAY", "Jog wheel"),
    "3": (_INPULSE_500, "DISPLAY", "Jog wheel (R)"),
    "6": (_INPULSE_500, "DISPLAY", "Jog wheel (R)"),
}


def decode_twos_complement_delta(value: object) -> int:
    """Signed tick delta for a 7-bit two's-complement relative jog value
    (``0x01..0x3F`` = +1..+63 clockwise, ``0x7F..0x40`` = -1..-64), ``0``
    for 0 or an unparseable / out-of-range value."""
    try:
        raw = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if not 0 <= raw <= 0x7F:
        return 0
    return raw - 0x80 if raw >= 0x40 else raw


def decode_jog_delta_for_key(key: CellKey, value: object) -> int:
    """Signed tick delta of ``value`` in the encoding of the controller
    owning ``key`` (two's complement for the Inpulse 500, else 0x40-centred)."""
    if key[0] == _INPULSE_500:
        return decode_twos_complement_delta(value)
    return decode_jog_delta(value)


def decode_jog_delta(value: object) -> int:
    """Signed tick delta for a 0x40-centred relative jog value: positive =
    forward/clockwise, negative = backward, ``0`` for the centre value or an
    unparseable one. Values are clamped to +/-63 (0x00..0x7F around 0x40)."""
    try:
        raw = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    delta = raw - _JOG_CENTRE
    return max(-63, min(63, delta))


def jog_cell_keys_for_event(
    channel: str | None, event_type: str | None, data1: str | None
) -> list[CellKey]:
    """Schematic ``CellKey``\\ s a live jog-turn event should spin, or ``[]``
    when the event isn't a known jog turn. A jog turn is always a Control
    Change; anything else (including the jog *touch* Note) returns ``[]``.
    More than one key comes back when controllers share a jog CC/channel --
    each view spins only the one it's showing."""
    if event_type != "Control Change":
        return []
    keys: list[CellKey] = []
    if data1 in _INPULSE_500_JOG_DATA1 and channel in _INPULSE_500_JOG_KEYS:
        keys.append(_INPULSE_500_JOG_KEYS[channel])
    if channel not in _DECK_CHANNELS:
        return keys
    for data1_set, left_key, right_key in _TWO_JOG_RULES:
        if data1 in data1_set:
            keys.append(right_key if channel in _RIGHT_DECK_CHANNELS else left_key)
    for data1_set, key in _SINGLE_JOG_RULES:
        if data1 in data1_set:
            keys.append(key)
    if data1 in _DDJ_FLX4_JOG_DATA1 and channel in _DDJ_FLX4_JOG_KEYS:
        keys.append(_DDJ_FLX4_JOG_KEYS[channel])
    return keys


__all__ = [
    "DEGREES_PER_TICK",
    "decode_jog_delta",
    "decode_jog_delta_for_key",
    "decode_twos_complement_delta",
    "jog_cell_keys_for_event",
]
