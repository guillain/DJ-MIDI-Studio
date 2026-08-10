# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Core pipeline and GUI v1 are implemented and tested against the user's real config file: `model.py` (domain dataclasses), `parser.py` (XML → model), `exporter.py` (model → XML, byte-for-byte round-trip on the sample file), `validator.py` (structural + conflict checks), `gui/` (PySide6 tree/edit/validate/export UI, launched via `seratomidiconf` entry point). The controller reference catalog (`catalog.py`, mapping raw channel/control numbers to physical control names for XDJ-XZ/DDJ-XP2) is not started yet — it needs an XDJ-XZ sample file the user hasn't provided. Root `main.py` is unrelated leftover PyCharm boilerplate, not part of the package. See `~/.claude/plans/sprightly-questing-bengio.md` for the full phased plan.

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
