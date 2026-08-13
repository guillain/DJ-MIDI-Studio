# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

All phases of the original plan are implemented and tested against the user's real config file: `model.py` (domain dataclasses), `parser.py` (XML → model), `exporter.py` (model → XML, byte-for-byte round-trip on the sample file), `validator.py` (structural + conflict checks), `catalog/` (channel/NOTE-CC/data1 → physical control name, see below — the user's real setup mixes DDJ-XP2 and XDJ-XZ in one config, so lookups always check every registered controller and can return ambiguous matches), `gui/` (PySide6 UI, see below). Root `main.py` is unrelated leftover PyCharm boilerplate, not part of the package.

### `catalog/` — plugin-style controller registry

`catalog.py` was split into a package: `catalog/_registry.py` (the `ControllerDefinition`/`ControlInfo` dataclasses and a plain-dict registry), one module per controller (`ddj_xp2.py`, `xdj_xz.py`), and `catalog/__init__.py` (imports each controller module for its registration side effect, re-exports the public API). Scope per controller is intentionally limited to discrete press/toggle controls (buttons, pad grids) — continuous controls (faders, TRIM/EQ knobs, jog wheels, touch strips/encoders) are left out since they're rarely remapped in Serato configs and don't reduce to one readable name.

**To add a new controller** (the user has a Behringer CMD LC-1 and a "miniPad" waiting on real MIDI docs before they can be added): write one new `catalog/<name>.py` module (static entries + a pad-grid function — use `_registry.make_sequential_pad_lookup(...)` if the note layout is simply `(pad-1) + mode_index*16`, otherwise write a bespoke one like `ddj_xp2.py`'s), end it with `register(ControllerDefinition(...))`, and import that module from `catalog/__init__.py`. Nothing else needs to change: `catalog.CONTROLLER_NAMES`/`PAD_COUNTS` are computed live from the registry on every access (module-level `__getattr__`, not a snapshot — a controller registered after the package is imported, e.g. interactively, is picked up immediately), and the Layout/By-Controller/Controller-Images tabs' combos all read from `CONTROLLER_NAMES` rather than a hardcoded list. Full docstring/steps in `catalog/__init__.py`; `tests/test_catalog_registry.py` exercises this end-to-end by registering a throwaway controller and checking it shows up in `lookup()` and `gui.layout.build_layout()`. See `~/.claude/plans/sprightly-questing-bengio.md` for the original phased plan (predates this package split).

### Empirical finding: the 10x duplication

In the user's real file, every unique `(channel, event_type, control)` trigger is repeated verbatim 10 times (64 unique triggers × 10 = 640 total `<control>` elements — confirmed via `build_mapping_groups`/`_check_duplicate_triggers`). This is **not** export bloat: the user confirmed deleting the "duplicates" breaks the config in Serato. The reason for exactly 10 is still unconfirmed (best guess: some internal Serato state not represented in this XML format, e.g. auto-loop length presets), but treat it as load-bearing. `validator.py` flags identical-content duplicates as `info`, explicitly saying not to deduplicate — never change that to `error`/cleanup advice without new evidence.

### GUI structure (`gui/`)

`left_tabs` has four tabs. The first three pair a tree (one resizable column per channel/deck/controller — implemented via `QSplitter(Horizontal)`, not a single nested tree) with a `layout_view.py` `ControllerLayoutView` schematic of the same underlying data:
- **By Channel**: `tree_model.build_channel_columns()` (one column per MIDI channel, each Note/Control → Control → UserIO → Mapping) + a plain `ControllerLayoutView` colored by which Serato deck(s) use each control.
- **By Deck**: `deck_tree.build_deck_columns()` (one column per Serato deck, each Slot → function) + `ControllerLayoutView(show_deck_filter=True)`, whose combo narrows the coloring to one selected deck.
- **By Controller**: `controller_tree.build_controller_columns()` (one column per controller — DDJ-XP2, XDJ-XZ — grouped by catalog section; sections with no used entries stay collapsed) + a third plain `ControllerLayoutView`. A leaf here can represent dozens of real `<control>` elements at once (a whole pad-mode grid cell), so clicking one reuses `MainWindow._on_layout_cell_activated` rather than feeding the edit panel directly.
- **Controller Images**: `controller_image_view.ControllerImageView` — a static, zoomable/pannable viewer (no data binding) for the official Pioneer controller diagrams, cropped from the MIDI Message List PDFs into `assets/controllers/*.png` (committed to the repo for personal/reference use only — these are Pioneer/AlphaTheta's copyrighted images, not to be assumed clear for redistribution beyond that).
- **Live Monitor**: `live_monitor.LiveMonitorView`, backed by `midi_io.py`. Watches real MIDI traffic and drives the same three `ControllerLayoutView`s via `MainWindow._on_live_midi_event` → `_update_layout_selection` — no separate highlight mechanism. Polled from a `QTimer` (`MidiMonitor.poll()`), not callback-based, specifically to avoid marshalling rtmidi's background-thread callbacks onto the Qt main thread. `MidiEvent.channel/event_type/data1` are pre-formatted to match `model.Control`'s string convention (1-indexed channel, `"Note On"`/`"Control Change"`, decimal `data1`) so they feed `catalog.lookup()` unchanged. Input-direction monitoring (controller → computer) works on any port; output-direction (Serato → controller) requires the user to manually add this app's self-created virtual destination (`MidiMonitor.VIRTUAL_MONITOR_NAME`) as an *extra* MIDI output in Serato — CoreMIDI does not let a third app silently see what another app sends to a real hardware destination, there is no way around this without that manual step. No physical controller was available while building this: verified end-to-end via macOS's built-in **IAC Driver** virtual ports (already enabled on this machine — `mido.get_input_names()` shows `IAC Driver Bus 1/2`), sending synthetic `mido.Message`s into one and confirming they appear in the log and highlight the correct Layout cell.

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
