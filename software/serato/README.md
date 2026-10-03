# Serato DJ mapping format

## What the format is

Serato DJ Pro's MIDI mapping files are a flat, custom XML dialect (no public
spec — understood entirely from a real exported file): a root `<midi
app="...">` holding a flat list of `<control channel="..." event_type="..."
control="...">` elements, each carrying `<userio event="click">` and/or
`<userio event="output">` blocks with one or more mapping elements (tag name
= the Serato function, e.g. `codfather_st`), which in turn carry a
`<translation>` with optional `<alias>` children. See `CLAUDE.md`'s "Domain
model (Serato MIDI XML format)" section for the authoritative, always-current
description — this file doesn't duplicate it, since that section is kept in
sync with `model.py`/`parser.py` directly.

## Grounding

`data/xdj_xz-ddj_xp2-4decks.xml` — a real, large (16,000+ line) config from
the maintainer's own working Serato setup (XDJ-XZ + DDJ-XP2, 4 decks). Used
as:

- the primary fixture for `parser.py`/`exporter.py`'s byte-for-byte
  round-trip tests;
- the source of the "Empirical finding: the 10x duplication" note in
  `CLAUDE.md` — every unique trigger repeated verbatim 10 times, confirmed
  load-bearing (deleting the "duplicates" breaks the config in real Serato).

## Additional real samples

The maintainer supplied two more real Serato exports (2026-09-19), zipped
individually in `data/serato/`:

- `cmd-lc1.xml.zip` — a Behringer CMD-LC1 mapping. No official MIDI docs
  exist; `catalog/behringer_cmd_lc_1.py` was captured on the real unit and
  `tests/test_catalog_cmd_lc1.py` checks this export against it. Each trigger
  repeats 9 times here (10 in the XDJ-XZ/DDJ-XP2 file).
- `ddj-xp2-custom.xml.zip` — a customized DDJ-XP2 mapping.

Not (yet) wired into the automated test suite the way the primary
`xdj_xz-ddj_xp2-4decks.xml` fixture is; useful for spot-checking the
parser/exporter/validator against real-world variety beyond the one
canonical fixture.

## Status

Well-grounded. This is the reference case the rest of `software/` is trying
to match for every other software plugin — real file, round-trip verified,
surprising quirks confirmed against the real application rather than
assumed from the XML shape alone.
