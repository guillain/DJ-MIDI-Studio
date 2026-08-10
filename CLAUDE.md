# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

All phases of the original plan are implemented and tested against the user's real config file: `model.py` (domain dataclasses), `parser.py` (XML → model), `exporter.py` (model → XML, byte-for-byte round-trip on the sample file), `validator.py` (structural + conflict checks), `catalog.py` (channel/NOTE-CC/data1 → physical control name, for DDJ-XP2 and XDJ-XZ — the user's real setup mixes both controllers in one config, so lookups always check both catalogs and can return ambiguous matches), `gui/` (PySide6 UI — tree view with search/filter, edit panel showing catalog matches, validation panel, undo/redo via `QUndoStack`, export). Root `main.py` is unrelated leftover PyCharm boilerplate, not part of the package.

`catalog.py`'s scope is intentionally limited to discrete press/toggle controls (buttons, the 16×8 DDJ-XP2 pad grid and 8×8 XDJ-XZ pad grid, both encoded as verified formulas rather than static tables) — continuous controls (faders, TRIM/EQ knobs, jog wheels, TIME/TOUCH STRIP encoders) are left out since they're rarely remapped in Serato configs and don't reduce to one readable name. Extend `_XP2_STATIC`/`_XZ_STATIC` the same way to add more entries. See `~/.claude/plans/sprightly-questing-bengio.md` for the full phased plan.

## What this project is

Serato MIDI Config Visualizer & Editor: a tool to simplify managing, visualizing, and modifying Serato DJ Pro MIDI configuration files (XML), which can run to 16,000+ lines. Planned capabilities (see README.md):

- **XML Parsing & Modeling**: parse Serato MIDI config XML into a structured object-oriented model (Decks, Channels, Notes, Slots, etc.)
- **Visual Mapping Editor**: GUI to visualize/modify MIDI mappings — object attributes (on/off values, colors) and associated events (Click, Output)
- **Validation**: catch mapping conflicts or invalid XML structure after edits
- **Export**: write a clean, valid XML file re-importable into Serato DJ Pro

## Domain model (Serato MIDI XML format)

`data/ddj-xp2-custom-4-decks.xml` is the user's real, current Serato config (DDJ-XP2, 4 decks) and the best reference for the XML shape — also used as the primary test fixture:

- Root `<midi app="...">` contains a flat list of `<control channel="..." event_type="..." control="...">` elements — these are the raw MIDI trigger (channel/note/control number).
- Each `<control>` holds `<userio event="click">` and/or `<userio event="output">` blocks.
- Inside a `userio` block, one or more mapping elements (tag name = the Serato function, e.g. `codfather_st`, `auto_loop_roll_specific_length`) carry `deck_set`, `deck_id`, `slot_id` attributes.
- Each mapping element contains a `<translation action_on="press|any|..." behaviour="toggle|explicit|...">`, optionally with `<alias name="on|off|selected" value="...">` children mapping logical states to raw MIDI values.

Any XML parsing/modeling code should be validated against this sample file's structure.

## Commands

This project uses `uv` (build backend is `uv_build`, Python `>=3.14`).

```bash
uv sync                  # install dependencies
uv run pytest            # run the test suite
uv run pytest tests/test_parser.py -k roundtrip  # run a single test
uv run ruff check src/ tests/  # lint
uv run seratomidiconf    # launch the PySide6 GUI
```
