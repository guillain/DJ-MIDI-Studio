"""Live jog-wheel rotation resolution.

Continuous jog turn is deliberately **out of catalog scope** (see
``catalog/__init__.py`` -- the catalog only carries discrete press/toggle
controls), so a live jog CC does *not* resolve through ``catalog.lookup()``
the way a pad or button hit does. This module carries the minimal
per-controller data needed to still animate the jog glyph from live MIDI:
which ``(channel, CC data1)`` pairs a controller's jog turn uses, and how to
turn its relative value into a signed tick delta.

Data source: the official **MIDI Message List** PDF bundled in
``docs/controllers/``, read from the *rendered table* (not ``pdftotext``,
whose column order scrambles multi-column rows). Only controllers with a
``"Jog wheel"`` entry in ``gui/geometry.CONTROL_GEOMETRY`` -- i.e. a jog
glyph actually drawn somewhere -- are worth listing here.

**XDJ-XZ** (MIDI Message List E3, group "1. DECK", Fig ``1[L,R]``):

===========================  ======  =============  ===================
UI name                      Msg     data1          Encoding
===========================  ======  =============  ===================
Jog dial (Platter) rotate    CC      0x22 / 0x29*   "increases from 0x41"
Jog dial (Wheel side) rotate CC      0x21 / 0x26*   clockwise, "decreases
                                                    from 0x3F" counter-cw
===========================  ======  =============  ===================

**DDJ-1000** (MIDI Message List E1, "JOG (Platter) rotate"):

===========================  ======  ==================  ================
UI name                      Msg     data1               Encoding
===========================  ======  ==================  ================
JOG (Platter) rotate         CC      0x21 / 0x29(+SEARCH) same 0x40-centred
                                     / 0x1F(+SHIFT)       relative encoding
===========================  ======  ==================  ================

``*`` (XDJ-XZ) = the ``+SHIFT`` variant of the same physical turn. On both
controllers the MIDI channel is the deck channel (DECK 1..4 = channel
"1".."4"). On XDJ-XZ decks 1/3 sit on the left jog and 2/4 on the right
tray jog, the same split ``layout.py``'s ``_RIGHT_GRID_DECKS`` uses for the
pad grids; DDJ-1000's schematic only draws the left deck, so every deck
channel there resolves to its single ``"Jog wheel"`` marker.

XDJ-XZ 0x21 and DDJ-1000 0x21 collide (both jog CCs on the deck channel);
``jog_cell_keys_for_event`` returns *both* markers, and each view spins
only its own controller's (the schematic shows one controller, the
emulator self-filters, the images overlay checks ``key[0]``).

The encoding is **0x40-centred relative**: a value above 0x40 is a forward
(clockwise) step, below 0x40 is backward, and the magnitude is the distance
from 0x40. ``decode_jog_delta`` returns that signed distance.
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

# XDJ-XZ jog-turn CC numbers (decimal strings, matching model.Control's
# convention): 0x21/0x22 plain + 0x26/0x29 with SHIFT, platter and wheel
# side. All four spin the same jog glyph.
_XDJ_XZ_JOG_DATA1 = frozenset({"33", "34", "38", "41"})
_XDJ_XZ_LEFT_DECK_CH = frozenset({"1", "3"})
_XDJ_XZ_RIGHT_DECK_CH = frozenset({"2", "4"})
_XDJ_XZ_LEFT_KEY: CellKey = ("XDJ-XZ", "DISPLAY", "Jog wheel")
# The right-tray jog's schematic key carries layout._RIGHT_GRID_SUFFIX, the
# same way real_position_markers() keys the mirrored pad grid / DECK cluster.
_XDJ_XZ_RIGHT_KEY: CellKey = ("XDJ-XZ", "DISPLAY", "Jog wheel (R)")

# DDJ-1000 platter rotate: 0x21 plain, 0x29 (+SEARCH), 0x1F (+SHIFT). Its
# schematic draws only the left deck, so any deck channel -> the one marker.
_DDJ_1000_JOG_DATA1 = frozenset({"33", "41", "31"})
_DDJ_1000_KEY: CellKey = ("DDJ-1000", "DISPLAY", "Jog wheel")


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
    if event_type != "Control Change" or channel not in _DECK_CHANNELS:
        return []
    keys: list[CellKey] = []
    if data1 in _XDJ_XZ_JOG_DATA1:
        keys.append(
            _XDJ_XZ_RIGHT_KEY if channel in _XDJ_XZ_RIGHT_DECK_CH else _XDJ_XZ_LEFT_KEY
        )
    if data1 in _DDJ_1000_JOG_DATA1:
        keys.append(_DDJ_1000_KEY)
    return keys


__all__ = ["DEGREES_PER_TICK", "decode_jog_delta", "jog_cell_keys_for_event"]
