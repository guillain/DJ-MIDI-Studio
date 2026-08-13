# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

All phases of the original plan are implemented and tested against the user's real config file: `model.py` (domain dataclasses), `parser.py` (XML → model), `exporter.py` (model → XML, byte-for-byte round-trip on the sample file), `validator.py` (structural + conflict checks), `catalog.py` (channel/NOTE-CC/data1 → physical control name, for DDJ-XP2 and XDJ-XZ — the user's real setup mixes both controllers in one config, so lookups always check both catalogs and can return ambiguous matches), `gui/` (PySide6 UI, see below). Root `main.py` is unrelated leftover PyCharm boilerplate, not part of the package.

`catalog.py`'s scope is intentionally limited to discrete press/toggle controls (buttons, the 16×8 DDJ-XP2 pad grid and 8×8 XDJ-XZ pad grid, both encoded as verified formulas rather than static tables) — continuous controls (faders, TRIM/EQ knobs, jog wheels, TIME/TOUCH STRIP encoders) are left out since they're rarely remapped in Serato configs and don't reduce to one readable name. Extend `_XP2_STATIC`/`_XZ_STATIC` the same way to add more entries. See `~/.claude/plans/sprightly-questing-bengio.md` for the full phased plan.

### Empirical finding: the 10x duplication

In the user's real file, every unique `(channel, event_type, control)` trigger is repeated verbatim 10 times (64 unique triggers × 10 = 640 total `<control>` elements — confirmed via `build_mapping_groups`/`_check_duplicate_triggers`). This is **not** export bloat: the user confirmed deleting the "duplicates" breaks the config in Serato. The reason for exactly 10 is still unconfirmed (best guess: some internal Serato state not represented in this XML format, e.g. auto-loop length presets), but treat it as load-bearing. `validator.py` flags identical-content duplicates as `info`, explicitly saying not to deduplicate — never change that to `error`/cleanup advice without new evidence.

### GUI structure (`gui/`)

`left_tabs` has four tabs. The first three pair a tree (one resizable column per channel/deck/controller — implemented via `QSplitter(Horizontal)`, not a single nested tree) with a `layout_view.py` `ControllerLayoutView` schematic of the same underlying data:
- **By Channel**: `tree_model.build_channel_columns()` (one column per MIDI channel, each Note/Control → Control → UserIO → Mapping) + a plain `ControllerLayoutView` colored by which Serato deck(s) use each control.
- **By Deck**: `deck_tree.build_deck_columns()` (one column per Serato deck, each Slot → function) + `ControllerLayoutView(show_deck_filter=True)`, whose combo narrows the coloring to one selected deck.
- **By Controller**: `controller_tree.build_controller_columns()` (one column per controller — DDJ-XP2, XDJ-XZ — grouped by catalog section; sections with no used entries stay collapsed) + a third plain `ControllerLayoutView`. A leaf here can represent dozens of real `<control>` elements at once (a whole pad-mode grid cell), so clicking one reuses `MainWindow._on_layout_cell_activated` rather than feeding the edit panel directly.
- **Controller Images**: `controller_image_view.ControllerImageView` — a static, zoomable/pannable viewer (no data binding) for the official Pioneer controller diagrams, cropped from the MIDI Message List PDFs into `assets/controllers/*.png` (committed to the repo for personal/reference use only — these are Pioneer/AlphaTheta's copyrighted images, not to be assumed clear for redistribution beyond that).

All editing goes through `edit_panel.py` + `commands.py` (`QUndoStack`-based). Raw nodes (Control/UserIO/MappingElement) edit individually; the "By Deck" columns instead surface `MappingGroup` (`mapping_group.py`) — the set of duplicate Control/MappingElement instances sharing the same trigger and deck/slot/tag/event (i.e. the 10x duplicates) — and edits apply to every member atomically via `SetGroupAttrCommand`/`Add-`/`RemoveGroupAliasCommand`, so it's structurally impossible to edit one duplicate out of sync with its siblings through that view.

Selecting anything in any tab highlights the matching cell(s) (red border) in all three `ControllerLayoutView` instances via `MainWindow._update_layout_selection`, and cross-tab navigation (layout cell click, deck/controller-tree leaf click) always lands on the underlying raw `Control` in the **By Channel** tab, resolved through `MainWindow.node_to_item` + `_channel_model_owner` (maps a source model id to its `(QTreeView, QSortFilterProxyModel)` since each channel is now a separate model/view pair).

`Help` menu links to the source docs (Serato's MIDI mapping guide is Cloudflare-protected and can't be fetched programmatically — `WebFetch`/`curl` both get a bot-challenge page, not the article).

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
                          # tests/conftest.py auto-creates a QApplication (QT_QPA_PLATFORM=offscreen by default)
uv run ruff check src/ tests/  # lint
uv run seratomidiconf    # launch the PySide6 GUI
```
