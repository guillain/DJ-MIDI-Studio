# Pioneer/AlphaTheta rekordbox mapping format

## Status: read-only plugin

`src/djmidi/software/rekordbox.py` (`v0.48.144`) reads these files: each
decoded address becomes a `Control` (`click` for input, `output` for LED
feedback), the command is `MappingElement.tag`, the deck 1-4 its `deck_id`
(none for a global row), and the control name / type / option / comment /
row number go in its `extra_attrs`. Disabled rows and `Fx` internal
parameters are skipped. A file is detected by its `@file,` first line
(`SoftwareDefinition.signature`). All 67 bundled files parse (37,880
controls) with no validation issue. Saving raises a clear error, see
below.

## Real files: the bundled official mappings

rekordbox 7 ships one CSV per supported Pioneer/AlphaTheta device in
`rekordbox.app/Contents/Resources/MidiMappings/` (67 files on the
maintainer's install, e.g. `DDJ-XP2.midi.csv`, `DDJ-1000.midi.csv`,
`XDJ-XZ (1).midi.csv` + `XDJ-XZ (2).midi.csv`). They are AlphaTheta's
copyrighted files: read in place, never copied into this repo. Tests must
use synthetic CSVs in the same shape.

All 67 were parsed (13,332 data rows) on 2026-10-25. Findings:

- **Encoding**: UTF-8, five of them with a BOM — read with `utf-8-sig`.
- **First line** `@file,1,<device name>` (format version 1), then a
  `#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment`
  header, then rows. Blank rows (`,,,,,…`) separate groups and `# Browser`,
  `# Deck`… rows title them.
- **15 fields per row** (one irregular row in all 67 files has 19).
- **Column 1 is the rekordbox command, column 2 the physical control.** The
  community description below had them the other way round. Example from
  `DDJ-REV7.midi.csv`: `Master,Sync+Shift,Button,905C,…` assigns the command
  `Master` to the `Sync` button pressed with SHIFT. A `+Shift` suffix on
  column 2 is the SHIFT layer.
- **Disabled rows** start with `#` in column 1: `#,TempoSlider+Shift,…,No
  function assigned here`, or a commented command (`#MasterCue,MasterCue,…`).
- **Type** (column 3): `Pad` 5,752, `Button` 5,141, `KnobSliderHiRes` 898,
  `Indicator` 380, `Rotary` 267, `KnobSlider` 221, `Value` 214, `JogRotate`
  150, `Parameter` 139, `JogTouch` 76, then a long tail (`Difference`,
  `JogIndicator`, `Slider`, `IndicatorHiRes`, `RotaryAsKnob`, `RawValue`,
  `JogRotateAbsPos`, `JogTimestamp`…).
- **MIDI addresses**, two encodings:
  - `input` holds four hex digits, the status byte then data1 (`9058` =
    Note On, channel 1, note 88; the status's low nibble is the base
    channel), and `deck1`-`deck4` hold decimal **0-based channel offsets**
    added to it (`0,1,2,3` = channels 1-4; pads use `7,9,11,13`
    and `8,10,12,14` for SHIFT on the DDJ-XP2).
  - or `input` is empty and each deck column holds a full hex address
    (`Load,Load,Button,,9646,9647,9648,9649,…` = channel 7, notes 70-73).
  - A row with no deck columns is global, on the status's own channel
    (`Browse,Browse,Rotary,B640,…` = CC 64 on channel 7).
- `output` and its deck columns use the same encodings for LED feedback.
- **Option** (column 14), semicolon-separated: `Fast` 7,428, `RO` 1,462,
  `Dual` 907, `Priority=N` 519, `Value` 151, `Blink=N` 73, `Max`, `Min`.

### Cross-check against this project's catalogs

Every `catalog/` controller with a bundled rekordbox file was compared
trigger by trigger (channel, Note/CC, data1) — the catalogs come from the
official MIDI Message List PDFs:

| Controller | Catalog triggers found in the CSV | Not found |
|---|---|---|
| DDJ-1000 | 1,072 | 0 |
| DDJ-FLX10 | 1,112 | 0 |
| DDJ-800 | 1,131 | 2 |
| DDJ-XP2 | 1,123 | 54 |
| DDJ-REV5 | 593 | 18 |
| DDJ-FLX4 | 254 | 41 |
| XDJ-XZ | 612 | 89 |

The decoding above is therefore confirmed. A "not found" is almost always a
control rekordbox's default mapping simply doesn't use (XDJ-XZ's channel-5
BEAT FX, DDJ-REV5's BPM TRANSITION, DDJ-FLX4's SHIFT pad layers). One real
disagreement: the DDJ-XP2 CSV puts `LoopHalf`/`LoopDouble` (the 1/2X and 2X
buttons) on notes 18/19 (`9012`/`9013`), while the official PDF and
`catalog/ddj_xp2.py` say 16/17 (their SHIFT layer, 76/77, agrees). No real
Serato mapping uses either pair, so pressing the buttons with the Live
Monitor open decides; the catalog stays on the PDF until then.

## Community description (2026-09, superseded where it disagrees)

rekordbox's custom MIDI mappings are **plain CSV files** (not XML) —
confirmed by AlphaTheta's own official support article, *"How to customize
rekordbox MIDI mapping"* (bot-protected, readable from a browser, not
fetchable by this tooling). Community documentation
([alexrster/rekordbox-dj](https://github.com/alexrster/rekordbox-dj))
describes the same CSV shape: 15 fields, hex MIDI codes, 0-based channels,
`#` comments. It names column 1 "Name" (free-form) and column 2
"Function"; the bundled files show column 1 is the command rekordbox runs
and column 2 the physical control.

## What's still needed before writing

- A **user-customized** CSV (exported from rekordbox's MIDI settings) to see
  how a user's own edits are saved next to these defaults.
- How rekordbox treats the per-deck `output` columns and `Option` values
  when a binding moves — only matters for writing, not for reading.

## Sources

- The bundled `rekordbox.app/Contents/Resources/MidiMappings/*.midi.csv` (rekordbox 7, read in place)
- [AlphaTheta — How to customize rekordbox MIDI mapping](https://support.alphatheta.com/en-us/articles/40182116223257) (official; bot-protected, not machine-fetchable)
- [alexrster/rekordbox-dj](https://github.com/alexrster/rekordbox-dj) — community documentation of the CSV shape
