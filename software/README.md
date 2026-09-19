# DJ software format documentation

> 📖 Reference material for the mapping *file formats* this app reads and
> writes, one subdirectory per supported (or candidate) DJ software —
> mirrors `controllers/`'s "one common directory, one subdirectory per
> controller" layout, but for the software side of the plugin architecture
> (`src/djmidi/software/`).

## Layout

```
software/
  README.md          (this file)
  <slug>/
    README.md         format notes: what the format actually is, sources,
                       what our plugin currently supports vs. doesn't, and
                       any real sample files archived for validation
    <sample files>     real exports, when a maintainer/user supplies one
```

## Why this exists

Serato's format was understood in detail from day one — `data/xdj_xz-ddj_xp2-4decks.xml`
is a real, large, maintainer-supplied config, and its quirks are documented
directly in `CLAUDE.md` (e.g. the "Empirical finding: the 10x duplication").
Traktor's support (`src/djmidi/software/traktor.py`) was built on an
untested assumption instead — see `traktor/README.md` for how that turned
out to be wrong (issue #122) — with no real sample file to check against at
all. This directory exists so every software plugin gets the same
evidence-based treatment as controllers already do: real files or real
specs archived here, with an honest account of what's actually verified
versus assumed, rather than that understanding living only in a PDF
someone read once or a docstring's claims.

## Index

| Software | Plugin | Status |
| --- | --- | --- |
| [Serato DJ](serato/README.md) | `src/djmidi/software/serato.py` (thin wrapper around `parser.py`/`exporter.py`) | Well-grounded — real fixture, byte-for-byte round-trip tested |
| [Native Instruments Traktor](traktor/README.md) | `src/djmidi/software/traktor.py` | Being rewritten (issue #122) — the original plugin targeted the wrong file structure entirely |
| [Pioneer/AlphaTheta rekordbox](rekordbox/README.md) | — none yet | Candidate — real format researched (CSV), no plugin, blocked on a real sample file |
| [VirtualDJ](virtualdj/README.md) | — none yet | Candidate — real format researched (two XML files, officially documented), no plugin, blocked on a real sample file pair |

## How to extend this index

When adding support for a new DJ software, or fixing an existing one: create
`software/<slug>/`, record what the real file format actually is (with
sources — official docs when they exist, otherwise clearly-labeled
community/reverse-engineered documentation), archive a real sample export
when one becomes available, and add a row above. Never invent format
details that aren't backed by a real spec or a real file — see the
`djmidi-audience-and-quality-bar` project convention (the same "no
fabricated data" rule this project already applies to controller MIDI
catalogs).
