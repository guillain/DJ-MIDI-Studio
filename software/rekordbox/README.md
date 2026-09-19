# Pioneer/AlphaTheta rekordbox mapping format

## Status: candidate, not yet integrated

No `src/djmidi/software/rekordbox.py` plugin exists yet. This file records
what's known about the real format so a future integration starts from
evidence, not a guess.

## What the format is

rekordbox's custom MIDI mappings are **plain CSV files** (not XML) —
confirmed by AlphaTheta's own official support article, *"How to customize
rekordbox MIDI mapping"* (the article itself returns HTTP 403 to automated
fetches, likely bot-protected the same way CLAUDE.md already notes for
Serato's own MIDI mapping guide — readable from a browser, not fetchable by
this tooling). Community documentation
([alexrster/rekordbox-dj](https://github.com/alexrster/rekordbox-dj))
independently describes the same CSV shape from real exported files:

- One row per mappable control, **14 comma-separated fields** (a row must
  always have exactly 14 commas, even when several fields are empty):
  1. **Name** — free-form label, no functional effect
  2. **Function** — the rekordbox function name (may contain dots, e.g. a
     namespaced command)
  3. **Type** — control type: `Button`, `Rotary`, `KnobSlider`, `KnobSliderHiRes`
  4. **Input** — the MIDI code received, in hex
  5–8. **Deck 1–4 Input** — per-deck MIDI channel overrides (optional)
  9. **Output** — the MIDI code rekordbox sends back (LED/indicator feedback)
  10–13. **Deck 1–4 Output** — per-deck output channel overrides (optional)
  14. **Option** — function-specific settings, semicolon-separated
  15. **Comment** — free-form notes (yes, 15 fields for "14 commas" — the
      comment is effectively an unbounded trailing field)
- **MIDI channels are zero-based**: channel 1 is written as `0`.
- Lines starting with `#` are comments.
- Official Pioneer mapping files for real controllers ship inside the
  rekordbox application bundle itself (macOS: right-click the app → *Show
  Package Contents* → `Contents/Resources`) — a legitimate, already-licensed
  source of real example files without needing external requests, if the
  app is installed locally.

## What's needed before building a plugin

- A **real exported CSV** (either from the maintainer's own rekordbox setup,
  or one of the bundled official per-controller files above) to validate
  the column semantics above against, the same "real file, not just a
  spec" bar every other software/controller integration in this project
  already meets.
- Confirmation of the full `Function` name vocabulary actually used (this
  research pass found the column's existence and shape, not an exhaustive
  list of values).

## Sources

- [AlphaTheta — How to customize rekordbox MIDI mapping](https://support.alphatheta.com/en-us/articles/40182116223257) (official; bot-protected, not machine-fetchable)
- [alexrster/rekordbox-dj](https://github.com/alexrster/rekordbox-dj) — community documentation of the real CSV shape
