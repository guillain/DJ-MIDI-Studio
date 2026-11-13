# CLAUDE.md

Guidance for Claude Code (claude.ai/code) and contributors working in this repository: what the code is, where
things live, and the rules and pitfalls that aren't obvious from reading one file. **History** — which version
added what, measurement stories, per-PR detail — lives in `TODO.md` ("Recent evolution chapters", "Next phases")
and in git, not here. Keep this file a map: when a feature lands, add or adjust its few lines here and put the
story in TODO.md.

## What this project is

DJ MIDI Studio (`djmidi`): a PySide6 desktop app for DJs. It started as an editor for Serato DJ Pro MIDI mapping
XML (16,000+ lines in real files) and grew into:

- **Mappings**: parse, view (By Channel / By Deck / By Controller), edit with undo, validate, export (Serato
  byte-for-byte round trip; Traktor `.tsi`, rekordbox CSV and Mixxx XML read, some written).
- **Controllers**: a plugin catalog of controller profiles (MIDI triggers → physical control names), photos with
  measured control positions, a clickable emulator, live MIDI monitoring, sync sets (LED/init messages), macros,
  MIDI routing/remapping, the Atelier (controller features instead of raw MIDI).
- **Music library**: scan the DJ's collection, tags, genre taxonomy, BPM/key, playlists, set preparation, Stage
  Mode — strictly non-destructive towards the collection and other DJ software.

Audience: DJs, who get release builds, not source. Quality bar and the user's own rules are in the memory files;
the two that matter everywhere: **never fabricate controller MIDI data or DJ-software names** (only official
docs, real captures or real exported files), and **never write the user's real Serato / Traktor / rekordbox
files or audio collection** unless a feature exists exactly for that and the user triggers it.

## Commands

This project uses `uv` (build backend `uv_build`, Python `>=3.14`).

```bash
uv sync --group dev                 # dependencies (dev group: pytest, xdist, ruff, Ableton Link, ...)
uv sync --extra analysis            # optional librosa for BPM/key estimation and waveforms
uv run pytest -n auto               # full suite in parallel (pytest-xdist), ~20 s
uv run pytest tests/test_parser.py -k roundtrip   # one test
uv run ruff check src/ tests/       # lint (don't run `ruff format` on existing files: it reflows them)
uv run djmidi                       # launch the GUI
bash scripts/test.sh quick|all|quality            # what the pre-commit hook / CI run
bash scripts/update_translations.sh               # lupdate + lrelease (FR, DE)
```

`tests/conftest.py` creates a `QApplication` (`QT_QPA_PLATFORM=offscreen`), gives **every test its own
workspace and preferences file**, pins the library DB to `:memory:`, restores the controller / taxonomy /
geometry registries and the plugin-enablement filter after each test, deletes leftover top-level widgets, and
never installs a translator (the suite always sees English). Tests run in parallel: never share state through a
fixed file path; use `tmp_path`.

## Conventions every change follows

- **Translations**: every user-visible string goes through `self.tr(...)` (context = class name) or, in Qt-free
  modules, `djmidi.i18n.QT_TRANSLATE_NOOP(context, text)` plus an optional `translate: i18n.Translate` argument
  (English default; the GUI passes `gui.translation.translator(context)`). Use `self.tr("… {name} …").format(…)`,
  never an f-string inside `tr()`. A module that gains marks must be added to `SOURCES` in
  `scripts/update_translations.sh`. After `update_translations.sh`, fill every `type="unfinished"` entry in
  `src/djmidi/translations/djmidi_{fr,de}.ts` (same `{placeholders}`, tags, `&` mnemonics), re-run, commit the
  `.ts` and `.qm`. `tests/test_i18n.py` fails on untranslated or stale catalogues; `test_untranslated_strings.py`
  fails on a widget-text literal outside `tr()`. Code must never compare against translated text (use item data
  / indexes / English keys).
- **Help**: every tab/tool window has `?` buttons (`gui/help_button.py`, texts in `gui/help_texts.py`, marked
  `HelpTexts`). Bold labels in a translated help body must match that language's button labels
  (`tests/test_help_labels.py`). Each help entry links a `docs/enduser/features/*.md` page.
- **Small windows**: nothing clipped or squeezed at small sizes (issue #19). New dialogs use
  `gui/window_size.py` (`fit_to_screen`, `usable_minimum`, `keep_wrapped_text_visible`, `keep_tab_titles_whole`)
  and join `WINDOWS` in `tests/test_small_windows.py` (checked in EN/FR/DE, offscreen screen 800×800). Wide rows
  go in a `QScrollArea`. A `QSplitter` blocks height-for-width: avoid it around wrapped labels in dialogs. Action-button rows of more
  than ~4 buttons go in an `action_groups.FlowLayout` (they wrap) rather than a `QDialogButtonBox`. A question or report
  over a list that can grow (files, tracks, playlists) uses `gui/list_dialog.confirm_list` / `show_list` (every
  row in a table, Cancel default), never a `QMessageBox` with a joined list; any other long `QMessageBox` text is
  made scrollable app-wide by `gui/message_box_fit` (installed in `gui/app.py`).
- **Buttons**: a panel with several actions groups them with `gui/action_groups.action_section(title, [(button, role)])`
  (titled sections, a flow layout that wraps, the `chip` look and a role icon, a tooltip on each). Icons are the app's
  own line icons (`gui/icons.line_icon(role, theme.colors()["icon"])`, redrawn on a theme switch by
  `icons.recolour_buttons`), never `QStyle.standardIcon`; build custom QSS from `theme.colors()` and restyle on
  `theme.signals.themeChanged`, never hardcoded dark colours; every QPushButton has the pill look
  (theme.py). Empty lists/tables get a `gui/empty_state.EmptyState`. Every other text button gets
  its icon automatically (`gui/button_icons`, installed in `gui/app.py`: role from the English source text through the
  `.ts` catalogue, or the button box's standard button); extend `ROLE_KEYWORDS` rather than setting icons by hand.
- **Accessibility**: icon/glyph-only buttons get a tooltip (`gui/accessibility.name_icon_buttons` turns it into
  the accessible name); `tests/test_accessibility.py` checks names, Tab focus and contrast.
- **Docs**: `docs/enduser/` (features for DJs; one `features/<feature>.md` per feature, listed in the feature
  tables of the root `README.md`, `docs/enduser/README.md` and `docs/enduser/features/README.md`) and
  `docs/developer/` (services, design, CI). Every page follows one template (title, `>` summary, `📍` breadcrumb,
  `## Table of Contents`, content, `## Related` / `## In this section`); `tests/test_docs.py` enforces it and every
  relative link. Screenshots come from `scripts/capture_docs_screenshots.py` (throwaway preferences/library).
- **Delivery** (maintainer's workflow): branch → `feat:` (code + tests + translations) → `docs:` →
  `release: prepare vX.Y.Z` (`uv version` + `uv lock`) → annotated tag `vX.Y.Z-<slug>` pushed on its own → PR.
  Docs-only changes get no bump or tag. Merge only with the maintainer's OK.
- **Verify in the app**, not only in tests, for anything visual: render the real `MainWindow`/dialog offscreen to
  a PNG and look at it.

## Code map

### Serato mapping model (`model.py`, `parser.py`, `exporter.py`, `validator.py`)

- XML shape (reference fixture: `data/xdj_xz-ddj_xp2-4decks.xml`, the user's real config): root `<midi>`, a flat
  list of `<control channel event_type control>` (the raw trigger) holding `<userio event="click|output">`, whose
  children are mapping elements (tag = Serato function, attrs `deck_set`/`deck_id`/`slot_id`) with a
  `<translation action_on behaviour>` and optional `<alias name value>`.
- `<case><condition><modifier_N operator="equal" cmp_value/></condition><userio…/></case>` = SHIFT/modifier
  layers: `model.Case`/`Condition` on `Control.cases`, round-tripped byte for byte. **Read bindings with
  `model.iter_bindings(control)`** (yields `(UserIO, Case | None)`), never `control.userios` alone; a binding's
  layer is `condition_of(case)`. Layers are editable (#434): Qt-free `case_edit.py` returns new
  `(userios, cases)` lists for one control (`set_conditions`, `move_into_layer`, `remove_layer`; modifiers and
  operators offered come from the file, `known_modifiers`/`known_operators`), applied by
  `gui.commands.SetControlLayersCommand` (one undo step) → `MainWindow._on_layers_changed` (rebuild, reselect).
  The panel applies every layer edit to all identical copies of the control (#440,
  `case_edit.identical_copies` = same trigger and same exported XML; `*_everywhere` replay it by position).
  By Deck offers the same edits on a `MappingGroup` (#448, `EditPanel._build_group_layer_box`, reselected by
  `_select_deck_group_like`).
- `exporter.py` round-trips the sample byte for byte; keep it that way (`tests/test_parser.py` roundtrip).
- **The 10x duplication**: every unique trigger appears exactly 10 times in the real file, and deleting copies
  breaks the config in Serato. It's load-bearing: `validator.py` reports identical duplicates as `info` only;
  never turn that into an error or a "dedupe" suggestion. Views group copies (`gui/mapping_group.MappingGroup`)
  and edit them atomically.
- `validator.find_deck_conflicts`: triggers binding two distinct functions on one deck (per condition layer).
- Serato function names: only the four tags real exports contain are known (`function_names.py`, test-pinned);
  Play/Cue/Sync tag names are unknown (#194) — never invent them.

### Software plugins (`software/`)

Registry of DJ programs (`SoftwareDefinition`: parser, exporter, extensions, optional `signature` sniffer and
`change_summary`); `software.discover_plugins` imports every non-underscore module.

- `serato.py` — the XML above.
- `traktor.py` + `_tsi.py` + `binary_chunks.py` — real Traktor `.tsi` (`<NIXML>` holding a Base64 blob of nested
  "4-char tag + u32 BE size" chunks; `binary_chunks` is a generic codec for that framing). Export only re-labels
  changed bindings on a deep copy; adding/removing bindings raises `TsiError`. Unedited export is byte-identical.
  Format notes and verification: `software/traktor/README.md`. Serato ↔ Traktor conversion is research-only until
  Serato's tag names exist.
- `rekordbox.py` — rekordbox `.midi.csv` mappings, read-only (`software/rekordbox/README.md`).
- `mixxx.py` — Mixxx `.midi.xml`, read + in-place patch export (unedited export byte-identical on all 142 Mixxx
  2.5 mappings, read in place, never copied — GPL). `mixxx_export.py` builds a new Mixxx mapping from a profile.
- `_contract.py` / `check_software_plugin` + `scripts/check_software_plugin.py` + `examples/software-plugin/`:
  the plugin contract for contributors adding another DJ program.
- Saving any mapping goes through `safe_update.prepare_update` (diff preview, `.bak` next to the file).

### Controller catalog (`catalog/`)

- `_registry.py`: `ControllerDefinition`/`ControlInfo`, `register(definition, replace=False)`; one module per
  controller registers itself; `catalog/__init__.py` imports them. `CONTROLLER_NAMES`/`PAD_COUNTS` are computed
  live. `lookup()` checks every registered controller and can return several matches (the user's real setup mixes
  DDJ-XP2 and XDJ-XZ). `detect_controller(port)` matches port names (score 100 = exact `name`/`port_names`).
- Scope: discrete press/toggle controls (buttons, pad grids). Continuous controls (faders, knobs, jogs) are out of
  catalog scope; jogs are handled by `gui/jog.py` tables.
- **Adding a controller**: with official docs, write `catalog/<name>.py` (static entries + a pad lookup —
  `make_sequential_pad_lookup` or bespoke) and import it from `catalog/__init__.py`. Render PDFs at 300 DPI
  (`pdftoppm`) before trusting a reading; drop rows the document contradicts itself on. Without docs, use the
  Controller Setup tab (live learn or import an existing mapping) → it generates the module / installs a JSON
  profile.
- `codegen.py` (draft → `ControllerDefinition` / module source, `find_trigger_conflicts`, `definition_entries`),
  `profile.py` (JSON user profiles in the workspace's `Controllers/`, plugin id `user.<slug>`; built-in names are
  refused), `library.py` (optional profile library under `controllers/library/{rekordbox,mixxx,community}/`,
  installed on demand, never registered at startup), `community.py` / `community_ingest.py` (no-backend
  submission → GitHub issue → workflow → PR).
- Controller images: `controllers/hardware/<vendor>/<Model>/reference.png` (clean) and `reference-midi.png`
  (callouts); normalized by `scripts/process_controller_images.py` (process first, then measure). Pioneer images
  are copyrighted: personal/reference use only.

### Controller geometry (`gui/geometry.py`)

`CONTROL_GEOMETRY[controller][label] = ControlGeometry(x, y, w, h, shape, color)` — fractions of the **clean**
reference photo, measured by cropping/zooming the image (3–5x crops, saturated-component or luminance
analysis) and **verified on the running app's overlay**, not just a rendered check. Every registered controller
has geometry (tests needing one without use the `geometry_free_controller` fixture). Right-deck markers use a
`" (R)"` suffix. `resolve_geometry_label` maps a live hit's catalog name to a label (shift suffixes, pad numbers,
combined labels like `"PAD MODE 1/5"`). Keep `geometry._RIGHT_GRID_DECKS` and `layout._RIGHT_GRID_DECKS` in sync
(`test_right_grid_tables_stay_in_sync`). User profiles can carry their own markers (`gui/geometry_editor.py`,
mirrored by `sync_profile_geometry`).

### GUI shell (`gui/main_window.py` + `gui/main_window_parts/`)

`MainWindow` is split into mixins: `docks` (tool docks, emulator instances, the ☰ window menu), `mapping_views`
(trees, layouts, selection sync, edit panel, validation), `live_midi` (live event routing and batching), `files`
(open/save, recents, compare, backup, snapshots, deck copy), `macros`, `tools` (command palette, cheat sheet,
Layer Map); module constants/helpers in `_shared.py` (re-exported by `main_window`). Mixins use
`QCoreApplication.translate("MainWindow", …)` so their strings keep the `MainWindow` context. **Methods that use a
name tests monkeypatch on `djmidi.gui.main_window`** (`list_input_ports`, `list_output_ports`, `run_sync`,
`current_version`, dialog classes, …) stay in `main_window.py`, as do `__init__`, `_build_menu` and Qt event
overrides.

- `left_tabs` is a `gui/nav_tabs.NavTabs`: Dashboard · Controller (Setup, Images, Studio = the Atelier, By… →
  By Channel / By Deck / By Controller) · Music. It keeps a flat page API (`_tab_indexes[key]`,
  `setCurrentIndex`, `currentChanged(int)`, `tabText`) over the nested tabs; levels are styled by object name
  (`navTop` / `navSub` / `navPills`, theme.py). Tool docks: Live Monitor, MIDI Routing, MIDI Clock, Metronome, plus any
  number of Controller Emulator docks (`View → New Controller Emulator…`; only the set of open controllers
  survives a restart).
- Editing goes through `edit_panel.py` + `commands.py` (`QUndoStack`); the Music Library has its own undo stack.
- Selecting anything highlights matching cells in all three `ControllerLayoutView`s (`_update_layout_selection`);
  cross-tab navigation lands on the raw `Control` in By Channel.
- Toggles with real side effects go in Preferences (`PluginPreferences`), not the View menu. Session-only view
  toggles: Performance Mode, Stage Mode (`gui/stage_window.py`, fullscreen emulator + monitor + set panel).
- `_layout_settings()` returns QSettings in the real app and `None` in tests: anything persisting UI state or
  running only in the real app (startup sync, update check, first-run wizard, library suggestions) is gated on it.
- PySide6 gotcha: keep Python references to widgets set via `setCornerWidget` etc. (`self._preferences_button`),
  or they get garbage-collected.

### Layout views and the emulator

- `gui/layout.py` (Qt-free): `build_layout`, cell keys, `reverse_lookup(controller)` (every `ControlInfo` variant
  per cell, pad lookups brute-forced over their bounded domain), `pick_default_variant` / `resolve_side_aware_variant`
  (pad mode token, SHIFT), `PAD_BANK_RE`, `is_shift_variant` (a `KEY SHIFT` pad mode isn't SHIFT).
- `gui/layout_view.py`: `ControllerLayoutView` (By… tabs: card grid, or real-position mode on the photo when the
  controller has geometry), `draw_control_glyph`, `draw_reference_photo`. `gui/layer_toggles.py`: Controller /
  MIDI / Layout display layers (one photo at a time; Layout greyed on the MIDI picture, whose crop differs).
- `gui/controller_emulator.py`: `ControllerEmulatorView` / `EmulatorLayoutView` — click to dry-run resolve what the
  loaded mapping binds, optional live send (`gui/live_send.py`), drag knobs/faders (display only), pad-mode and
  SHIFT state (`gui/pad_mode.py`), radio-group output state (`gui/output_state.py`), pad colours for controllers
  with a documented palette (`pad_colours.py`, only Hercules Inpulse 500 — never add a palette without the table).
- `gui/controller_image_view.py`: the photo viewer with overlay, live flashes and jog notches.

### Live MIDI (`midi_io.py`, `gui/live_monitor.py`, `main_window_parts/live_midi.py`)

- `MidiMonitor.poll()` from a `QTimer` (never rtmidi callbacks); `MidiEvent` strings match `model.Control`
  (1-based channel, `"Note On"`/`"Control Change"`, decimal data1). Notes, CC and **pitch bend** are converted:
  `midi_io.PITCH_BEND` events have data1 `"0"` and a 14-bit data2 (0-16383, `PITCH_BEND_CENTRE` 8192); note/CC
  consumers ignore them, the live path returns before the layouts (no selection change), the log, MIDI export,
  Stage Mode and hardware-session captures keep them.
- `_on_live_midi_event` order: jog ticks (`gui/jog.py`, per-controller tables, early return) → selection, flash,
  held state, knob values → consumers in priority (● Rec, profile check, hardware session capture, remap Learn,
  macro editor Learn, edit-panel Learn, else macro triggers). Output-direction events (`direction == "out"`, from
  the virtual monitor port Serato must be told to send to) drive latched LED state only.
- **Bursts**: views redraw through `gui/deferred_rebuild.DeferredRebuild` — batch per poll
  (`begin_batch`/`end_batch`), hidden views redraw on show, one shared flash-expiry timer. Never redraw a whole
  scene per event. `gui/freeze_watchdog.py` logs the GUI thread's stack after 5 s without response;
  `logging_config.enable_crash_log` + `gui/click_trail.py` leave traces of native crashes.
- Live Monitor log filters (#447, Qt-free `live_filter.LogFilter`): port / direction / kind / hide jogs, applied
  with `setRowHidden` (the event is stored on each row's first item); display only, nothing else is filtered.
- MIDI Learn (`midi_learn.py`): opens no port, rides the Live Monitor via `_ensure_learn_listening`.
- `midi_latency.py`: round-trip probe (needs something that echoes).
- `midi_router.py` / `gui/midi_routing_view.py`: routes with value transforms and per-control `RemapRule`s;
  `replace_route` keeps a route's position; virtual remap port on macOS/Linux.

### Sync sets, scenes and macros

- `controller_sync.py` (Qt-free): `SyncMessage`, `ControllerSyncSet(controller, output_port, messages, scene)`,
  `resolve_output_port`, `run_sync` (one port open per set), `PlugInSyncTracker` (ports by identity; Windows'
  trailing index stripped only on Windows), `sets_for_scene` (active scene, else Default). Stored one JSON per
  (controller, scene) in the workspace's `Sync/` (`sync_store.py`), mirrored in preferences. Recorded via ● Rec or
  Controller Setup; edited in Preferences (`gui/sync_set_editor.py`).
- `midi_macros.py`: `MidiMacro` (steps with delays, triggers/sequences, toggle `alternate_steps`, scenes, wait
  steps, `simulates`), stored one JSON per macro in `Macros/`; `gui/macro_player.MacroPlayer` plays without
  blocking (shared ref-counted ports, released during long delays — Windows outputs take one client);
  `MacroTriggerMatcher` for controller-press triggers. Export/import bundles (`djmidi-macros/1`).

### Atelier (`atelier/`, `gui/atelier_view.py`)

Controller *features* instead of raw MIDI (epic #413). `features.features_for(controller)` → one `Feature` per
catalog entry and channel (stable id `section.name@channel`), with an LED output **assumed** (LED note = input
note, unverified) unless verified LED data exists (`led_data.py`, `Controllers/<slug>.leds.json`, recorded with
the LED probe). `actions.py` compiles/decompiles `FeatureAction`s (tap/press/release/value, LED on/off/value) to
`SyncMessage`s. `describe.macro_target(output_port, simulates)` is the single direction rule (controller port →
drive its LEDs; else `simulates` → imitate its presses). `scene.py`: LED state ↔ sync set (unknown messages kept
in place), `scene_coverage`. `remap.py`: remap rules from two features. `macro_edit.py`: macro steps from clicks (main or toggle `alternate_steps`, wait steps via `wait_step_for`).
The Atelier tab: scene designer (drafts per controller and scene, Save all / Send all), Remap tab over MIDI
Routing routes, Macros tab (clicks add steps; the scene's LED box hides). `gui/photo_picker.PhotoPicker` is the
shared click state machine (SHIFT, pad mode per side). Real LED probing and the Pioneer colour table are still
unverified on hardware; function assignment waits for Serato's tag names.

**Controller library** (#451): `atelier/captures.py` keeps the guided check's verdicts per controller
(`Controllers/<slug>.captures.json`, one per check item *and* DJ software — a DDJ-XP2 sends other notes, and
has pad modes 5-8 at all, only while Serato drives it), `atelier/library.py` merges catalog + captures + LED data
per `Feature` (`knowledge_for`) and audits per physical control (`audit_controls`, `audit_text`). The guided
check is `gui/profile_check.py` + `gui/profile_check_dialog.py` (tabs Check / Lights / Audit, photo frame via
`gui/control_photo.py`): a held SHIFT is never the asked control, presses are judged over a short window
(double / long press), MIDI-OUT sections are not asked, lights are asked one per address (plain layer, first
pad bank, decks 1-2). LED data only counts as verified once seen lit. The Feature card shows `library.knowledge_of` (cached
`knowledge_index`); `ProfileCheckDialog.libraryChanged` / `AtelierView.libraryChanged` →
`MainWindow._on_controller_library_changed` refresh the Atelier (`refresh_library`, draft kept), emulator cards
and the audit. `catalog/profile.py` skips these sidecar
files (`is_sidecar_file`). Nothing here edits a profile.

### Music library (`library/`, `taxonomy/`, `gui/music_library_view.py`)

Rules: **read-only towards the collection and other DJ software** except explicit, user-triggered writes, each
surgical and logged. Qt-free modules; the tab is a thin view over `library/workspace.py`.

- `db.py` `LibraryDB` (SQLite index beside preferences; `DJMIDI_LIBRARY_DB` overrides; opened lazily on first
  show): tracks (path/size/mtime/missing), `track_metadata` cache (re-read when mtime changes), playlists,
  settings, analysis suggestions, notes, play stats, change log, waveform cache. Schema upgrades in place.
- `scanner.py` (incremental, flags missing instead of deleting), `metadata.py` (mutagen; `MANAGED_FIELDS`
  allowlist; frame-level writes only — Serato `GEOB`/`serato_*` and Traktor `PRIV` frames stay byte-identical;
  `clean_noise_frames`), `cover_art.py` (front cover only), `analysis.py` (Camelot mapping; librosa estimates
  behind the optional `analysis` extra, gap-filling only, user-confirmed), `waveform.py`.
- Formats: `serato_library.py` (crates only, never `database V2`), `traktor_library.py` (`collection.nml`
  streamed with `iterparse`; standalone single-playlist `.nml` export), `rekordbox_library.py` (`export.pdb`,
  hand-written from the crate-digger spec), `history.py` (Serato/Traktor play history, read-only), `rekordbox_xml.py` (a playlist as
  Pioneer's published rekordbox XML import format, #441; new file only, untested in a running rekordbox;
  `read_playlists` reads one back, read-only, for Import / Compare, #446).
- Features: `playlist.py` (harmonic/BPM compatibility, simple draft order, receding-horizon mix path),
  `taxonomy/` (genre families, aliases, fuzzy suggestions never auto-applied), `smart_playlist.py`,
  `set_prep.py` (hand-ordered set, transitions, order proposal, generate from library, stage notes),
  `relink.py`, `duplicates.py` + `discard.py` (Trash only, via injectable trash function; never a hard delete),
  `health.py`, `stats.py`, `rename.py` / `organize.py` (inside library roots, never in protected DJ folders),
  `change_log.py` (every file write logged and revertible), `playlist_compare.py`, `gig_journal.py`.
- Performance at ~85k tracks matters: the table model sorts itself, the proxy only filters, no-op filter changes
  are skipped (`tests/test_library_perf_budget.py` counts operations, not seconds). Long work runs in `QTimer`
  slices or a worker thread; the SQLite connection stays on the GUI thread.

### Other services

- `user_paths.py`: the workspace (`~/Documents/DJ MIDI Studio`, `DJMIDI_WORKSPACE`) with `Controllers`, `Sync`,
  `Macros`, `Drafts`, `Logs`, `Exports`, `Snapshots`. `backup.py`: workspace backup/restore (validated, atomic).
- `file_locations.py`, `snapshots.py`, `mapping_diff.py` (semantic diff counting copies), `deck_copy.py`,
  `function_search.py` / `search_text.py` (accent-insensitive tokens), `command_palette.py`, `live_ready.py`,
  `first_run.py`, `hardware_session.py` (checklist of hardware-only checks, Help menu), `problem_report.py` and
  `catalog/community.py` (pre-filled GitHub issues, nothing sent by the app), `update_check.py` (silent offline,
  never downloads), `startup_timing.py`, `midi_export.py` (Live Monitor log as SMF).
- Cheat sheet: `gui/cheat_sheet.py` (Qt-free) → PDF (`cheat_sheet_pdf.py`) or self-contained HTML.
- Build: `scripts/build.sh` (PyInstaller; bundles `docs/`, `controllers/` and, when the `analysis` extra is installed as in CI, librosa — checked by `smoke_test_executable.py --require-analysis`), `scripts/macos_signing.sh`
  (skips cleanly without credentials), `scripts/smoke_test_executable.py --screenshot`.

## Known gaps waiting on hardware or the maintainer

Tracked in `TODO.md` (Phase 9 / "Waiting on hardware") and in the Hardware Session window: DDJ-XP2 1/2X / 2X
notes, CMD Micro / Studio 4a jogs (the Studio 4a's Traktor export binds one pitch bend per deck as an absolute
FaderOrKnob / Direct control, so probably its pitch fader, not its jog — #442), real LED probing and Pioneer colours, Serato
Play/Cue/Sync tag names (#194), Traktor Controller Manager exports (#233), a Traktor import of the `.nml` export,
macOS notarization (Apple Developer account).
