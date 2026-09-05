# ToDo

This file is the project roadmap and delivery record. It distinguishes
implemented features from work that still requires development or validation.

Status rules:

- A phase is `COMPLETE` only when every item in that phase is complete.
- Hardware-dependent validation remains open until it has been verified on the
  target operating system, software, controller, and MIDI ports.
- Completed work is retained under **Delivered** as a historical record.
- **Open backlog** contains only unchecked work. The next phases are left
  intentionally undefined until they are agreed together.

## Table of Contents

- [Current roadmap status](#current-roadmap-status)
  - [Phase 0 — baseline plugin architecture](#phase-0--baseline-plugin-architecture)
  - [Phase 1 — plugin contracts and declarative profiles](#phase-1--plugin-contracts-and-declarative-profiles)
  - [MIDI Foundation — normalized MIDI 1.0 API](#midi-foundation--normalized-midi-10-api)
  - [Phase 2 — assisted integration detection](#phase-2--assisted-integration-detection)
  - [Phase 3 — multi-device MIDI engine](#phase-3--multi-device-midi-engine)
  - [Phase 4 — safe software/controller operations](#phase-4--safe-softwarecontroller-operations)
- [Delivered](#delivered)
  - [Recent evolution chapters](#recent-evolution-chapters)
  - [Core mapping workflow](#core-mapping-workflow)
  - [Mapping views and navigation](#mapping-views-and-navigation)
  - [Controller catalogs](#controller-catalogs)
  - [MIDI tools and live workflows](#midi-tools-and-live-workflows)
  - [Testing, documentation, and delivery](#testing-documentation-and-delivery)
  - [Phase 3 hardware validation](#phase-3-hardware-validation)
- [Open backlog](#open-backlog)
  - [Candidate controller catalogues](#candidate-controller-catalogues)
  - [Future MIDI API extensions](#future-midi-api-extensions)
  - [External tester feedback (2026-08)](#external-tester-feedback-2026-08)
  - [Next phases to define](#next-phases-to-define)

## Current roadmap status

The implementation roadmap is complete through Phase 4, and Phase 3's
hardware validation is now also complete (2026-09-04) — see [Recent evolution
chapters](#recent-evolution-chapters) for the full story. In short: the direct
`Ableton Link (DJ MIDI Studio)` → CoreMIDI follower path is verified on real
hardware (Serato, XDJ-XZ, DDJ-XP2, MIDIface 4x4, Ableton Live 12 as the Link
Start Stop Sync peer). The root cause of the initial failures was a real bug,
not a hardware limitation: `AalinkStateProvider` enabled plain Link but never
opted the app's own session into Start Stop Sync, so no peer's Start/Stop —
Serato's or Live's — could ever reach the follower regardless of what that
peer did. Fixed by enabling `start_stop_sync_enabled` on the app's session.
Along the way, Serato's own Ableton Link integration was independently
confirmed (via a raw `aalink` protocol probe) to publish tempo only, never
transport, and to expose no Clock/MIDI-output configuration of its own — so
Serato alone can never drive this path; some other genuinely Start-Stop-Sync-
capable Link peer (Ableton Live here) is required.

The current release baseline is `v0.46.0`. The post-release evolution is
implemented on the active `feature/independent-midi-clock` line and is tracked
as focused chapters below. These chapters are software-validated; they do not
close the open physical Serato/CoreMIDI validation items.

### Phase 0 — baseline plugin architecture — COMPLETE

- [x] Controller and DJ software registries discover built-in modules and Python entry points.
- [x] Controller and software lists are consumed dynamically by the current GUI.
- [x] Serato and Traktor are exposed as software plugins.

### Phase 1 — plugin contracts and declarative profiles — COMPLETE

- [x] Define and validate a versioned JSON plugin manifest for controllers and DJ software.
- [x] Add plugin capabilities and permissions to the manifest.
- [x] Support controller profiles from JSON first; defer YAML until a concrete need exists.
- [x] Define schema validation, duplicate-ID handling, and useful diagnostics.
- [x] Add plugin enable/disable state and preferences.
- [x] Add profile fixtures and contract tests that require no MIDI hardware.
- [x] Add plugin lifecycle operations: discover, validate manifest, register, enable/disable, reload, and report compatibility errors.

### MIDI Foundation — normalized MIDI 1.0 API — COMPLETE

- [x] Define normalized port identity/state and raw MIDI message types aligned with Web MIDI concepts.
- [x] Expose available mido ports through the normalized port API while keeping native MIDI 1.0 transport.
- [x] Preserve raw bytes, timestamps, port identity, realtime messages, and SysEx in the normalized message contract.
- [x] Add deterministic hardware-free tests for ports, messages, SysEx, and plugin detection adapters.

### Phase 2 — assisted integration detection — COMPLETE

- [x] Detect mapping software from file signature and extension, with a reason and confirmation when ambiguous.
- [x] Detect controllers from MIDI port names and return ranked plugin candidates.
- [x] Show confidence and detection reason before enabling an integration.
- [x] Keep explicit user selection as the fallback for unknown or ambiguous hardware/software.
- [x] Add MIDI Identity Reply/SysEx parsing, identity metadata hooks, and capability scoring where hardware permits it.

### Phase 3 — multi-device MIDI engine — COMPLETE

Implemented contract, runtime, test, and documentation work:

- [x] Adopt the W3C Web MIDI API as the conceptual compatibility model without adding a browser runtime dependency.
- [x] Keep the native implementation on MIDI 1.0 byte messages through `mido`/`rtmidi`.
- [x] Define the normalized MIDI message/port API, including realtime messages, timestamps, and SysEx.
- [x] Specify MIDI 2.0/UMP as a future adapter instead of mixing it into the MIDI 1.0 router.
- [x] Add a one-way MIDI router with port/channel/message filters and loop prevention.
- [x] Add monitoring/status for routes, dropped messages, latency, and errors.
- [x] Add MIDI Clock mirroring with Start/Stop/Continue handling, 24 PPQN forwarding, source selection, and jitter safeguards.
- [x] Document Serato, Traktor, and Rekordbox clock-specific behavior before cross-software synchronization.
- [x] Add virtual-port integration tests and deterministic fake-clock tests.
- [x] Reject empty, duplicated, self-referential, and feedback-loop Clock configurations.
- [x] Reset Clock jitter measurement at Start/Continue/Stop boundaries.
- [x] Add live Clock states for configured, waiting, inactive, and actively receiving sources.
- [x] Distinguish unopened sources, open sources without ticks, and transport-only input in diagnostics.
- [x] Separate MIDI input and output selectors so an input cannot be configured as a Clock destination.
- [x] Add the direct Ableton Link follower that emits Start/Continue/Stop and 24 PPQN MIDI Clock without changing Link tempo.
- [x] Add deterministic Link scheduler tests and a clear missing-optional-binding diagnostic.
- [x] Make `aalink` a default dependency so Link support is installed reproducibly with the standard environment.
- [x] Bridge the asyncio-based `aalink` runtime to the Qt routing poller and report Link follower activity correctly.
- [x] Package the `aalink` binding as a default dependency in local, CI, release, and PyInstaller builds so Ableton Link is available in native artifacts.
- [x] Move MIDI Clock configuration and diagnostics into an independent closable/floating dock while retaining the shared routing safety session.
- [x] Enable Start Stop Sync opt-in (`start_stop_sync_enabled`) on the app's own Link session, without which no peer's real Start/Stop can ever reach the follower.
- [x] Add a Serato Clock → Link transport bridge that republishes an external Clock producer's real Start/Continue/Stop onto the app's Link session.
- [x] Diagnose each configured Clock route (a plain Clock mirror and a Link follower) independently in the Clock status banner, so one never hides an unrelated problem with the other.

### Phase 4 — safe software/controller operations — COMPLETE

- [x] Add read-only software status and configuration capability declarations.
- [x] Add configuration updates only through backup, preview/diff, validation, and rollback.
- [x] Add the hardware-free safe-update engine with backup, preview/diff, validation, atomic apply, and rollback primitives.
- [x] Route GUI Save and Save As through validation, backup, and atomic safe-update writes.
- [x] Add preferences for enabled plugins, detection policy, routing policy, and trust decisions.
- [x] Support unknown devices and unsupported mapping formats through a generic MIDI profile.
- [x] Document plugin installation, updates, compatibility, trust, and troubleshooting.
- [x] Add rotating execution logs with configurable levels and CLI path override.

## Delivered

### Recent evolution chapters

- [x] **Independent MIDI Clock tool** — move Clock configuration and diagnostics
  into a closable/floating dock while retaining shared routing safety and
  `Ableton Link (DJ MIDI Studio)` support. Commit `4e85483`, follow-up fixes
  `ea00a64`, `9fb8a7c`, and `f35fe3d`; milestone tag `v0.46.1-midi-clock-tool`.
- [x] **DJ performance visual language** — apply the dark theme across the
  application, style mapping trees/layouts, and preserve generic fallbacks.
  Commits `cd2bc72` and `454242c`; milestone tag
  `v0.46.2-dj-performance-theme`.
- [x] **Responsive controller workspace** — improve dashboard/controller setup
  composition, center pad layouts, keep MIDI output readable, and allow
  narrower windows. Commits `5c27d90` and `aed5aa9`; milestone tag
  `v0.46.3-responsive-workspace`.
- [x] **Helpful Notes onboarding** — provide a startup popup with persistent or
  session-only dismissal and a View-menu reopen action. Commit `2fdffc`;
  milestone tag `v0.46.4-helpful-notes`.
- [x] **Visual documentation refresh** — regenerate canonical dashboard,
  mapping, MIDI tool, docked, and floating screenshots from the offline fixture.
  Commit `fc9192f`; milestone tag `v0.46.5-visual-docs`.
- [x] **Evolution documentation** — record the architecture, user workflows,
  validation boundaries, screenshots, and chapter-to-commit mapping in
  [Recent Evolution Chapters](docs/development/evolution.md).
- [x] **Diagnostic logging overhaul** — apply the Preferences log level live,
  instrument Ableton Link, MIDI routing/Clock/router, MIDI I/O, safe-update,
  XML parse/export, validation, and the controller/software plugin
  registries with INFO/DEBUG/WARNING/ERROR logging, escalate sustained Clock
  inactivity to an ERROR log, and fix the Controller Setup Capture port list
  height and the MIDI Tools dock Float menu state after closing a floating
  window. Commits `aade77d` and `1a35c6e`; milestone tag
  `v0.47.1-diagnostics-logging`.
- [x] **Custom log path preference and Controller Setup UI fixes** — add a
  persisted log file path preference (with Browse… dialog) that a CLI
  `--log-file` flag still overrides, preserve the active log file when
  Preferences are saved without a custom path, restore visible text labels
  on Controller Setup's icon buttons, and remove hardcoded light-theme
  colors that fought the dark theme. Commit `4b64acf`; milestone tag
  `v0.47.2-log-path-and-setup-ui-fixes`.
- [x] **Controller Setup panel density and View menu flattening** — give
  Session/Capture/Import/Apply-Export compact icon-only title-bar actions,
  split Message and playback controls into a readable two-column layout,
  widen the PAD 1–8 buttons back to legible size, make the Capture
  status indicator a distinct badge, and flatten the View menu's MIDI
  Tools submenu (dropping the per-dock Float actions in favor of each
  dock's native float button) into top-level toggles. Commit `f9afe85`;
  milestone tag `v0.47.3-controller-setup-density`.
- [x] **On-demand help popups, minimal Session width, visible Dock/Undock,
  and a revived Metronome dock** — collapse Capture/Import/Apply-Export's
  always-visible description labels into a title-bar "?" button that
  pops the same text up on click, cap the Session panel to its icon
  column's minimum width instead of an equal grid share, replace each
  tool dock's tiny native float button with an explicit "Undock"/"Dock"
  title-bar button, and pull the loop-oriented Controller Setup session
  player back out of MIDI Routing's "Controller Setup playback" panel
  (merged there in `d1e1f1d`) into its own View-menu "Metronome" dock.
  Commit `8a43e12`; milestone tag `v0.47.4-help-popups-metronome-dock`.
- [x] **3-column Message and playback controls, fixed panel row height** —
  arrange Send message/Playback/Pad modes as three side-by-side columns
  instead of two columns plus a separate pad row, and fix the
  Session/Capture/Import/Apply-Export row rendering ~100px taller than
  any panel needed (QListWidget's `sizeHint()` ignores `setMinimumHeight`
  and was inflating the whole shared grid row; `setMaximumHeight` on the
  Capture port list pins it). Commit `959c768`; milestone tag
  `v0.47.5-three-column-output-compact-row`.
- [x] **Dashboard Metronome shortcut and optional per-route MIDI transforms** —
  add "Open Metronome" to the Dashboard's MIDI tools alongside the View
  menu entry, and let a MIDI Routing route carry an optional
  `MidiValueTransform` (channel override, note/CC offset, invert value)
  applied after filtering and before forwarding, edited via a new "Edit
  transform…" dialog and summarized in the routes table. Deliberately
  scoped down from general MIDI-translator tools (e.g. Bome MIDI
  Translator): value remaps only, no scripting/conditionals/non-MIDI
  triggers/message-type conversion. Commit `87decab`; milestone tag
  `v0.47.6-metronome-shortcut-route-transforms`.
- [x] **Taller Dock/Undock buttons and persisted MIDI Routing/Clock/Metronome
  view state** — grow each tool dock's title-bar `Dock`/`Undock` and close
  buttons from 22px to 28px so the label isn't cramped, and add
  `save_state()`/`restore_state()` on `MidiRoutingView` and `MetronomeView`,
  wired into `MainWindow`'s existing window geometry/state persistence.
  Previously only the window/dock arrangement was saved: routes, Clock mirror
  configuration (source/destination ports, Ableton Link followers, `Enable
  Clock mirror policy`, `Create virtual input for Serato Clock`), and
  Metronome's output port/value/Hz lived in memory only and reset on every
  restart. Commit `70dad89`; milestone tag
  `v0.47.7-dock-buttons-and-view-state-persistence`.
- [x] **Bulk Section/Name assignment in Controller Setup** — add `Set section
  for selected rows…` and `Set name for selected rows…` row-buttons so a whole
  pad grid can be labelled in one step instead of one row at a time. The Name
  action offers auto-numbering (`PAD 1`, `PAD 2`, …) across the selection.
  Both go through one `_apply_bulk_edit` helper that resyncs the table, marks
  the draft dirty, restores the selection, and re-runs `find_trigger_conflicts`
  so a colliding bulk edit is flagged immediately. Resolves
  [#15](https://github.com/guillain/DJ-MIDI-Studio/issues/15); milestone tag
  `v0.47.8-bulk-section-name`.
- [x] **Adaptive default window size** — replace the fixed first-run
  `resize(1100, 700)` with `_default_window_size()`, derived from
  `screen().availableGeometry()` (preferred `1280x820`, scaled down to fit
  smaller displays, never below `1100x720`), and center the window on first
  launch when there is no saved geometry to restore. The tiny absolute
  minimum size from `v0.47.7` is kept so the window can still be dragged
  narrower than the controller-selector content. Partially addresses
  [#19](https://github.com/guillain/DJ-MIDI-Studio/issues/19) (the "default
  size" half); a per-panel scroll-wrap pass waits on the reporter's
  screenshot. Milestone tag `v0.47.9-adaptive-window-size`.
- [x] **"Show all controllers" escape hatch and Preferences bulk toggles** —
  the mapping tabs, Dashboard, and Controller Images selector already honoured
  the per-controller Preferences enablement (`catalog.set_enabled_plugin_ids`,
  `CONTROLLER_NAMES` computed from `active_controller_names()`); add the parts
  [#18](https://github.com/guillain/DJ-MIDI-Studio/issues/18) still asked for:
  a persisted `View -> Show all controllers` toggle that bypasses the filter
  without discarding the checkboxes, `Enable all` / `Disable all controllers`
  buttons plus a hint in the Preferences dialog, and an autouse test fixture
  that resets the global enablement filter (and a stray frozen
  `catalog.CONTROLLER_NAMES`) between tests. Milestone tag
  `v0.47.10-enabled-controllers`.
- [x] **User-attached controller reference image** — `Attach reference
  image…` in Controller Setup's Import panel picks a local PNG/JPG and stores
  its absolute path in `self._reference_image`, persisted in the session JSON
  (`reference_image` key), threaded through `codegen.build_definition` and
  `generate_module_source` (basename only, so a bundled
  `assets/controllers/<basename>` resolves), and rendered by the Controller
  Images tab after `Apply now`. `controller_image_view._resolve_image_path`
  now accepts an absolute path as well as a bare bundled filename. Images are
  never copied into the repo — the export dialog points at
  `assets/controllers/` and flags the licensing responsibility. Resolves
  [#16](https://github.com/guillain/DJ-MIDI-Studio/issues/16); milestone tag
  `v0.47.11-reference-image`.
- [x] **Community catalog submission (minimal)** — `Submit to community
  catalog…` in Controller Setup's Apply / Export panel. `catalog/community.py`
  (Qt-free, tested) builds a versioned `controller-submission/1` JSON payload
  from the draft's `ControllerDefinition` plus optional contributor metadata
  (small dialog), then `submission_issue_url()` produces a pre-filled
  `github.com/<repo>/issues/new` link — payload inlined in the querystring
  when it fits under ~6 kB, otherwise a paste placeholder with the JSON put on
  the clipboard. The handler validates first (same gate as Apply/Export),
  always copies the JSON, opens the browser, and warns if it can't be opened.
  Reference images are deliberately excluded from the payload. Resolves
  [#17](https://github.com/guillain/DJ-MIDI-Studio/issues/17) (the minimal,
  no-backend option); milestone tag `v0.47.12-controller-submission`.
- [x] **Consistent Controller Setup panels and a context-aware edit column** —
  route the Session, Import, and Apply/Export panels through one shared
  `_icon_button_grid` helper so all three place their icon actions in a
  compact body grid (Import/Apply-Export previously crammed them into the
  panel title bar); only Capture keeps its buttons in the header and grows
  with the window. Hide the central edit/validation column
  (`MainWindow._right_splitter`) unless the active tab is By Channel / By
  Deck / By Controller, and drop EditPanel's "select a node…" prompt once an
  edit form is shown. Milestone tag `v0.47.13-setup-panels-and-edit-column`.
- [x] **Selectable Light / Dark / System theme** — one QSS template with two
  colour palettes plus a "follow the OS" mode, chosen in `Settings ->
  Preferences` (`theme` = `system` | `light` | `dark`, persisted). Applied on
  save and at startup, and re-applied live when the OS flips light/dark while
  in `system` mode. `apply_theme` also drives Qt's colour scheme
  (`setColorScheme` / `unsetColorScheme`) so native controls and `QStyle`
  standard icons match, and the dark theme's buttons got a lighter fill and a
  higher-contrast border so icon-only buttons stand out. A few MIDI-tool /
  Controller Setup panels still carry hard-coded dark inline styles that a
  follow-up will tokenise; the controller schematic canvas stays dark by
  design. Milestone tag `v0.47.14-theme-selector`.
- [x] **Controller Setup input/output row and merged Draft toolbar** — merge
  the separate `Session`, `Import`, and `Apply / Export` panels into one
  `Draft` panel: a single horizontal icon toolbar (`_toolbar_row`) with a
  caption in front of each group (`Session`, `Import`, `Apply / Export`) and
  the groups spread across the window width. Rename `Capture` to `MIDI input`
  and move it (unchanged: input port list, `Start learning`, status) to the
  start of the same row as `MIDI Output`, top-aligned so it stays as tall as
  its content. Milestone tag `v0.47.15-controller-setup-io-layout`.
- [x] **Per-controller schematic proportions and framed zones** (issue
  [#13](https://github.com/guillain/DJ-MIDI-Studio/issues/13), "DJ layout
  visual fidelity", part 1) — a `LayoutMetrics` per controller (cell width,
  margins, glyph sizes; default = unchanged for the six other controllers)
  gives DDJ-XP2 a compact pad-forward look and XDJ-XZ a wide airy one. Every
  physical zone is now drawn as a rounded, labelled panel behind its cells
  (`_draw_zone_frames`), replacing the free-floating section titles that
  collided with a neighbour's cells, and the `_PRO_LAYOUTS` anchors were
  re-placed to echo each device's real topology with a row gap between
  vertically-adjacent zones. Parts 2 (MIDI-value animation) and 3
  (performance mode) remain. Milestone tag `v0.47.16-controller-geometry`.
- [x] **Ableton Link Start Stop Sync fix and hardware validation** (closes
  [#10](https://github.com/guillain/DJ-MIDI-Studio/issues/10)) —
  `AalinkStateProvider` enabled plain Link but never opted the app's own
  session into Start Stop Sync (`start_stop_sync_enabled`), so no peer's real
  Start/Stop could ever reach the `LinkClockFollower`. Fixed, plus a Serato
  Clock → Link transport bridge (`AalinkStateProvider.publish_transport`,
  `MidiRoutingSession._bridge_serato_transport`) for relaying a genuine
  external Clock producer's Start/Stop onto Link, and a Clock status banner
  fix that diagnoses each configured route independently instead of letting
  a Link route mask an unrelated problem elsewhere. Verified end-to-end on
  real hardware (Serato, XDJ-XZ, DDJ-XP2, MIDIface 4x4, Ableton Live 12).
  Milestone tag `v0.47.19-link-start-stop-sync`.
- [x] **Controller Setup import clarity** — every help affordance in the tab
  (a new per-group help button plus a persistent hint under the "Draft"
  panel) now says explicitly that Controller Setup builds a *controller
  profile*, never a Serato mapping for editing (`File → Open` does that).
  Importing an existing Serato XML now offers, on success, to also open that
  same file as an editable mapping (`openMappingRequested` signal →
  `MainWindow._on_open_mapping_requested`, landing on `By Channel`) — the one
  deliberate exception to the tab staying otherwise self-contained. Milestone
  tag `v0.47.18-controller-setup-import-clarity`.
- [x] **Pad/button flash on a live MIDI hit** (issue
  [#13](https://github.com/guillain/DJ-MIDI-Studio/issues/13), "DJ layout
  visual fidelity", part 2, pads only) — `ControllerLayoutView.flash_key(key)`
  briefly (220ms) turns a discrete pad/button glyph white on a live MIDI hit,
  independent of the persistent red selection border already drawn by
  `set_selected_keys`, mimicking a real pad lighting up. Wired from
  `MainWindow._on_live_midi_event` alongside the existing selection update, on
  all three `ControllerLayoutView` instances. Continuous controls (knob/fader/
  jog/VU) don't react yet — animating an actual value, not just a discrete
  hit, is a separate follow-up. Visually verified with the app running
  (offscreen `QApplication` + `MainWindow.grab()`, same technique as
  `scripts/capture_docs_screenshots.py`) before delivery, per the "don't build
  visual-polish features blind" guidance. Milestone tag
  `v0.47.20-pad-flash-animation`.
- [x] **Knob rotation and fader thumb animation from live MIDI values** (issue
  [#13](https://github.com/guillain/DJ-MIDI-Studio/issues/13), "DJ layout
  visual fidelity", part 2 continued) — `ControllerLayoutView.set_value(key,
  value)` records the last known 7-bit MIDI value for a knob/fader glyph: a
  knob's marker rotates across a typical 270-degree pot sweep (-135 to +135
  degrees), a fader's thumb moves within its track. Unlike a flash, this is a
  level, not a pulse — it persists like a real control staying wherever it
  was left. Wired from `MainWindow._on_live_midi_event` (`event.data2`)
  alongside the existing flash/selection updates. Also fixes a pre-existing
  z-order bug where the knob's marker line was always painted but the dial's
  yellow ellipse, added after it, fully covered it — the marker was never
  actually visible even before this chapter. Jog wheels (rotation is
  relative, not an absolute position) and VU meters (no glyph exists yet) are
  out of scope. Visually verified with the app running before delivery, same
  technique as the pad-flash chapter above. Milestone tag
  `v0.47.21-knob-fader-animation`.
- [x] **Multi-output selection in Controller Setup's MIDI Output** — requested
  directly by the user, matching `MIDI input`'s existing multi-select. The
  "Available output ports" list is now a checkbox `QListWidget` (shared
  `port_list_utils.refresh_checked_port_list` helper, same as `MIDI input`)
  instead of a single-selection list; `_selected_output_ports()` returns
  every checked port, and "Send once", "Send double-click", "Play selected/
  all session row(s)", and "Replay recorded session" all loop over the full
  list instead of one `currentItem()`. Unlike a fresh `MIDI input` list
  (nothing pre-checked), `_refresh_output_ports()` auto-checks the first
  port whenever none are checked, preserving the old single-output
  convenience default. Milestone tag `v0.47.26-multi-output-selection`.
- [x] **Auto-start Live Monitor when a mapping is loaded** — requested
  directly by the user: pressing a controller button should update the
  `By Channel`/`By Deck`/`By Controller` layouts without a separate
  `Live Monitor` tab visit and manual `Start monitoring` click first.
  `LiveMonitorView.ensure_monitoring_started()` opens every currently
  available MIDI input and starts the poll timer, called from
  `MainWindow._load_tree()` on every mapping load. New
  `PluginPreferences.auto_start_live_monitor` (default `True`, a checkbox in
  `Settings -> Preferences...` per explicit user follow-up request, not a
  View-menu toggle) gates it off entirely for anyone who wants the old
  manual step back. Never overrides an already-running hand-picked Live
  Monitor session, and a port that fails to open is skipped and logged
  rather than blocking the rest or popping a dialog — this runs silently in
  the background, unlike the manual "Start monitoring" button. Milestone tag
  `v0.47.27-auto-start-live-monitor`.

### Core mapping workflow

- [x] Parse Serato MIDI XML into a typed domain model.
- [x] Export edited models back to Serato-compatible XML.
- [x] Validate required fields, supported values, duplicate triggers, and mapping conflicts.
- [x] Edit controls, UserIO entries, translations, aliases, and mapping associations from the GUI.
- [x] Add undo/redo support, tree search/filtering, Save, Save As, and reopen workflows.

### Mapping views and navigation

- [x] Add the Dashboard with loaded-file status, controller overview tabs, catalog statistics, MIDI availability indicators, and drill-down shortcuts.
- [x] Present one spacious Dashboard Controller Overview tab per controller, with an enlarged reference image and vertical drill-down actions.
- [x] Keep Dashboard Controller Overview drill-down buttons compact and readable beside the controller image.
- [x] Add By Channel, By Deck, and By Controller views with resizable trees and physical layout views.
- [x] Add clickable schematic controller layouts, catalog interpretations, Serato deck coloring, and mapped function labels.
- [x] Add DJ-oriented layout glyphs for pads, buttons, knobs, faders, and jog wheels while preserving the generic fallback.
- [x] Add a dark performance-oriented layout theme with deck colors, section labels, and high-contrast selection accents.
- [x] Add display-only mixer controls for XDJ-XZ and DDJ-XP2 so trim, EQ, volume, crossfader, and Slide FX surfaces are visible before continuous MIDI cataloging.
- [x] Arrange XDJ-XZ and DDJ-XP2 layouts into dedicated pads, deck, effects, mixer, browse, and pad-mode zones.
- [x] Center the Dashboard MIDI tools beside Known controllers and center the pad bank in the layout view's initial viewport.
- [x] Synchronize tree/layout selections, preserve the originating tab, and fade recent selection history.
- [x] Increase the Physical control panel height and make dynamic controller selectors horizontally scrollable.
- [x] Keep the Physical control field expanded with a splitter-safe minimum height for long multi-controller matches.
- [x] Add zoomable/pannable Controller Images diagrams with reset zoom.
- [x] Remove the obsolete Dashboard Go to section.

### Controller catalogs

- [x] Add DDJ-XP2, XDJ-XZ, DDJ-1000, DDJ-FLX4, DDJ-FLX10, DDJ-REV1, Numark Mixtrack Pro FX, and Hercules DJControl Inpulse 500 profiles.
- [x] Convert the catalog into a plugin-style dynamic registry.
- [x] Resolve static controls, pad grids, conflicts, and generated catalogs from learned/imported controls.
- [x] Apply generated catalogs immediately and refresh all controller-dependent views.
- [x] Add official reference images and archive available controller documentation locally with source URLs.
- [x] Document the distinction between MIDI message lists, user guides, product sheets, and physical reference images.

### MIDI tools and live workflows

- [x] Add Live Monitor with multiple input sources, port refresh, source-device resolution, Serato function lookup, CSV export, and a virtual monitoring destination.
- [x] Add Controller Setup with MIDI learning, Serato XML import, source/device tracking, and one-shot NOTE/CC sending.
- [x] Support DDJ-XP2 double-click commands and Pioneer PAD MODE 1–8 resolution, including shifted variants.
- [x] Move repeated Controller Setup playback into MIDI Routing and remove the standalone Metronome tab.
- [x] Add the `djmidi-send-midi` CLI command and `--double-click` helper.
- [x] Make Live Monitor and MIDI Routing independent closable dock panels with Dashboard and View-menu access.
- [x] Allow both docked and floating MIDI tool windows without changing the mapping workspace layout.
- [x] Apply the DJ performance theme consistently to the main window, dialogs, menus, tabs, docks, and mapping surfaces.
- [x] Move Helpful Notes into a startup popup accessible from the View menu, with persistent or session-only dismissal.
- [x] Rework Controller Setup into a readable responsive layout with a full-width MIDI Output panel.
- [x] Keep MIDI Output port selection, message fields, playback actions, and PAD MODE 1–8 controls visible without sacrificing functionality.
- [x] Allow the main and MIDI tool windows to shrink below controller-selector content width and preserve the user's window/dock arrangement between launches.
- [x] Persist MIDI Routing/Clock routes and configuration and Metronome's transport fields between launches, not just the window/dock arrangement.

### Testing, documentation, and delivery

- [x] Add unit and GUI coverage for parser, exporter, validator, catalogs, layouts, Controller Setup, MIDI I/O, routing, and session playback.
- [x] Add quick, full, lint, path, and quality test modes through `scripts/test.sh`.
- [x] Add the quality gate for coverage, code smells, duplication, and security findings.
- [x] Complete a runtime robustness review covering MIDI port cleanup, Clock destination isolation, restart-state reset, partial device-start recovery, and safe-update rollback semantics.
- [x] Add bootstrap, build, executable packaging, release artifact, CI, and provider-neutral GitHub/GitLab release scripts.
- [x] Run the multi-platform CI pipeline on every branch push and Pull Request, with a quality gate before Linux/macOS/Windows builds.
- [x] Migrate GitHub Actions setup steps from Node.js 20-era action versions to the Node.js 24-compatible releases.
- [x] Upgrade setup-uv, upload-artifact, and download-artifact to their Node.js 24-compatible major versions.
- [x] Use native PowerShell archive creation for Windows release artifacts when the Git Bash `zip` utility is unavailable.
- [x] Collect dynamically discovered catalog and software modules in PyInstaller builds and guard the empty-catalog startup path.
- [x] Collect the dynamic Mido/rtmidi backend required when the packaged Live Monitor enumerates MIDI ports.
- [x] Run a six-second functional startup smoke test for every native executable before artifact upload.
- [x] Isolate packaged startup smoke tests from unavailable host MIDI services with an explicit headless MIDI-disable mode.
- [x] Upload Python packages once per release and make GitHub release asset uploads safely repeatable.
- [x] Generate and publish SHA-256 checksums for every release artifact.
- [x] Fall back to a temporary log file when an existing per-user log cannot be opened by the packaged app.
- [x] Create a Pull Request automatically after successful multi-platform CI when a branch has no open PR.
- [x] Document Linux ALSA/Qt headless dependencies, Windows MSYS path handling, and the tag-only CD release flow.
- [x] Automate release preparation with version/lock bump, release commit, generated PR description, merge-to-tag automation, and tag-triggered multi-OS assets.
- [x] Publish the GitHub release automatically after the tag build completes, with no manual draft-release action.
- [x] Invoke the release build directly after merge-tag creation so GitHub's GITHUB_TOKEN event suppression cannot skip the asset pipeline.
- [x] Add the documentation portal, quickstart, user guide, architecture, testing, quality, build, release, controller PDFs, and visual layout documentation.
- [x] Generate and document canonical docked and floating MIDI-tool window compositions; arbitrary user arrangements remain persisted rather than exhaustively screenshoted.
- [x] Complete the Help menu with bundled project documentation, controller references, and official external links.
- [x] Update the Dashboard and Controller Setup visual documentation and screenshots after the layout redesign.
- [x] Record the post-`v0.46.0` evolution chapters with architecture diagrams,
  screenshot references, and reproducible capture instructions.
- [x] Keep a stable screenshot index for application views and dock/floating
  window compositions.
- [x] Restore the main window surface after native macOS full-screen transitions.
- [x] Translate the Dashboard UI and tests to English.
- [x] Rename the project to DJ MIDI Studio.

### Phase 3 hardware validation

All items complete as of 2026-09-04 — full setup: Serato with Link enabled,
XDJ-XZ, DDJ-XP2, MIDIface 4x4, Ableton Live 12. See
[#10](https://github.com/guillain/DJ-MIDI-Studio/issues/10).

- [x] Verify the direct Ableton Link → CoreMIDI output path with Serato,
  XDJ-XZ, DDJ-XP2, and a real MIDI destination on macOS.
  **Root cause of every earlier failure on this item:** `AalinkStateProvider`
  enabled plain Link but never opted the app's own session into Start Stop
  Sync (`start_stop_sync_enabled`). Without that opt-in, no peer's real
  Start/Stop — Serato's or Ableton Live's — could ever reach the follower,
  regardless of what that peer did; this was verified independently of the
  app with two standalone `aalink` processes (one publishing, one only
  reading) genuinely exchanging Start/Stop over the real network once both
  had the flag set. Fixed by enabling it in `AalinkStateProvider`. Verified
  end-to-end afterwards: with only the `Ableton Link (DJ MIDI Studio)` Clock
  route configured (no Serato-side involvement at all), a fresh Stop/Start in
  Ableton Live 12 (a genuine Start-Stop-Sync-capable Link peer) produced
  `Link transport started` in the app and `CLOCK ACTIVE` with real ticks
  delivered to the MIDIface.
  Separately (and confirmed independent of the above bug): Serato's own
  Ableton Link integration publishes tempo only, never transport — verified
  with a raw `aalink` protocol probe showing `start_stop_sync_enabled` and
  `playing` staying `False` even while a deck was actually playing in Serato.
  Serato also exposes no Clock/MIDI-output configuration of its own, so
  `SERATO_CLOCK_INPUT_NAME` never receives anything directly from Serato
  either. Serato alone can therefore never drive this path; some other
  genuinely Start-Stop-Sync-capable Link peer is required (Ableton Live here).
  A Serato Clock → Link transport bridge (`AalinkStateProvider.publish_transport`,
  wired through `MidiRoutingSession._bridge_serato_transport`) was built while
  chasing this, on the mistaken premise that Serato's real Start/Stop could be
  captured from its own MIDI Clock output the way the item below did — it
  cannot, since Serato never sends anything to that virtual port either. Kept
  as a real capability for its actual use case (relaying a genuine external
  Clock producer's Start/Stop onto Link), not as a Serato-specific workaround,
  along with a fix to the Clock status banner that was masking this diagnosis
  (it always blamed "no Link beats" whenever a Link follower was configured,
  even when the real problem was an unrelated, separately-configured route).
- [x] Verify the complete Serato → CoreMIDI virtual-port path on a real macOS/Serato setup, including port discovery, Clock output selection, Start/Stop, and sustained 24 PPQN ticks.
  Verified on macOS + Serato Pro with a physical controller (XDJ-XZ / DDJ-XP2)
  in the loop: virtual-port discovery and Clock source selection, Start /
  Stop / Continue relay, drift-free sustained 24 PPQN, and delivery to a real
  CoreMIDI destination. **Correction (2026-09-04):** re-validated attempts
  without Ableton Live running produced zero messages on
  `SERATO_CLOCK_INPUT_NAME`, and `docs/midi-clock-compatibility.md` already
  documented that this virtual port is an input meant to receive ticks from
  an external bridge, not from Serato directly. The original wording
  attributing this to "Serato transport" was imprecise: the actual producer
  in that session was Ableton Live's own native MIDI Clock output (Live +
  Link were running throughout), not Serato. The mechanics verified here
  (virtual-port discovery, relay, jitter-free 24 PPQN, real destination
  delivery) stand; only the attribution of *who produced the signal* is
  corrected.

## Open backlog

### Candidate controller catalogues

The following profiles are intentionally ordered by market reach, availability
of official MIDI documentation, and fit with the current catalog architecture.

#### Delivered profiles requiring field verification

- [x] **DDJ-FLX4** — conservative two-deck/eight-pad profile and official product image delivered.
- [x] **DDJ-FLX10** — conservative four-deck profile and official MIDI message list/artwork archived.
- [x] **DDJ-REV1** — official MIDI Message List E1, conservative Serato profile, and reference artwork delivered.
- [x] **Numark Mixtrack Pro FX** — initial discrete-control profile delivered.
- [x] **Hercules DJControl Inpulse 500** — initial discrete-control profile delivered.
- [ ] Verify the delivered FLX4, FLX10, REV1, Numark, and Hercules profiles against target hardware/firmware captures; continuous controls and missing vendor-specific evidence remain explicitly out of scope until verified.
- [x] **DDJ-1000** (not originally on this list, but the same class of problem): its catalog data was checked against the official bundled PDF (not hardware) and corrected in `v0.47.31-ddj-1000-catalog-fix` — see Recent evolution chapters. **DDJ-FLX10 had the same kind of problem, worse**: it had reused DDJ-1000's (wrong) values wholesale, and its real controls diverge substantially from DDJ-1000's (ACTIVE PART DRUMS/VOCAL/INST, MIX POINT SELECT/LINK, CUE/LOOP CALL <>/>>) — fully re-transcribed from FLX10's own PDF (not a value fix) in `v0.47.32-ddj-flx10-catalog-fix`, see Recent evolution chapters.

#### New candidates

- [ ] **DDJ-REV5** — two-deck battle controller with a distinct pad/deck layout.
- [ ] **DDJ-800** — established two-channel Rekordbox controller.
- [ ] **Native Instruments Traktor Kontrol S2 MK3** — representative non-Pioneer Traktor controller.
- [ ] **RANE FOUR** — four-channel Serato controller.
- [ ] **Denon DJ Prime 4+** — four-deck Engine DJ system and Serato comparison point.

For every new controller: obtain and archive an official MIDI message list or
capture the hardware, add the profile and layout metadata, add tests, document
software/firmware assumptions and limitations, and update the controller
documentation index.

### Future MIDI API extensions

- [ ] Add MIDI 2.0/UMP support through a separate adapter after the MIDI 1.0 routing and Clock validation is complete.
- [ ] Revisit external YAML profile support only if JSON profiles cannot express an agreed requirement.
- [ ] Define a future plugin API for advanced DJ software features such as multi-deck, multi-controller, and multi-software operations.

### DJ layout visual fidelity

- [ ] Add controller-specific geometry and proportions for XDJ-XZ and DDJ-XP2.
  Started in `v0.47.23-transport-overlay`: `gui/geometry.py` records real,
  hand-measured per-control geometry (position + shape + a semantic color) as
  fractions of the official reference photo (`assets/controllers/*.png`), and
  the Controller Images tab gained a "Show real layout" checkbox that
  overlays it directly on the real photo — sidestepping the schematic
  Layout tabs' uniform fixed-size cards, which can't represent a giant jog
  wheel and a small button at their true relative scale without overlapping.
  XDJ-XZ's transport cluster (PLAY/PAUSE, CUE, SYNC, jog wheel, tempo fader)
  was modeled first. Extended in `v0.47.24-ddj-xp2-geometry` to DDJ-XP2's pad
  cluster: the 16-pad grid, the 4 PAD MODE buttons (one marker per physical
  button, since each is shared by two logical modes via single/double-click —
  see `catalog/ddj_xp2.py`), and the SLIDE FX bank (EFFECT 1/2/3, FX LEVEL,
  TOUCH STRIP HOLD). DDJ-XP2 has no deck transport section at all (it's a
  pad/FX companion controller: BEAT SYNC/SILENT CUE/QUANTIZE/KEY, not
  PLAY/CUE/SYNC), so it has no transport entries. Each entry was verified by
  cropping the region of the real image it claims to describe and
  screenshotting the rendered overlay against it (not guessed from the PDF
  callout numbers alone) — this caught one real mistake (TOUCH STRIP HOLD's
  first-pass Y coordinate landed below the actual button). Completed for
  DDJ-XP2 in `v0.47.25-ddj-xp2-deck-geometry`, covering its remaining
  DECK/BROWSE/OTHER controls: LOOP (4 BEAT LOOP, 1/2X, 2X), QUANTIZE, BEAT
  SYNC, SILENT CUE, KEY -/+, the central Rotary Selector, the two LOAD
  buttons (one marker per physical button for "LOAD DECK 1/3" and
  "LOAD DECK 2/4", disambiguated by SHIFT the same way the pad channels
  are), and SHIFT — every DDJ-XP2 catalog section now has real geometry
  except MIDI-OUT (four output-only LEDs, not a user control). Live-wired in
  `v0.47.28-live-flash-real-layout`: requested directly by the user
  ("refléter l'état des contrôleurs... si on appuie sur une touche, on doit
  voir son état changé") — `ControllerImageView.flash_key(label)` briefly
  turns a marker white on a live MIDI hit, mirroring
  `ControllerLayoutView.flash_key` on the schematic tabs. New
  `geometry.resolve_geometry_label(controller, hit_name)` maps a live
  catalog hit's raw name to the geometry label it should flash — stripping
  shift suffixes, extracting a pad number from DDJ-XP2's
  `"Deck 1 Pad 3 (PAD MODE 2)"`-style names, and expanding a combined label
  like `"PAD MODE 1/5"` back to the logical names it answers to — and only
  flashes when the hit's controller matches the one currently shown in
  Controller Images. XDJ-XZ's hot cue pad cluster (the 8-pad grid and the
  HOT CUE/BEAT LOOP/SLIP LOOP/BEAT JUMP mode buttons) modeled in
  `v0.47.29-xdj-xz-hotcue-geometry` — XDJ-XZ's mixer strip has no catalog
  entries at all (continuous controls are out of catalog scope entirely),
  so there is nothing discrete left to model there; a mixer overlay would
  have to be display-only, like Jog wheel/Tempo. Extending this to
  continuous values (knob/fader rotation on the real photo, not just a
  flash) and to the schematic Layout tabs' own remaining gaps (jog wheels,
  VU meters) is future work. Also being extended, one branch per controller,
  to the app's other registered controllers with real reference photos and
  catalog data (DDJ-1000, DDJ-REV1, DDJ-FLX4, DDJ-FLX10, Numark Mixtrack Pro
  FX, Hercules DJControl Inpulse 500) — see the version history below for
  progress; each batch is gated on `scripts/quality_gate.sh` (coverage,
  code smell, duplication, bandit, pip-audit) passing, not just `pytest`/
  `ruff`. DDJ-REV1 completed in `v0.47.30-ddj-rev1-geometry`: PLAY/PAUSE,
  CUE, AUTO LOOP, 1/2X, 2X, SYNC, and its 8-pad grid — every entry in
  `catalog/ddj_rev1.py`. Required replacing `assets/controllers/ddj-rev1.png`
  first: it was an angled marketing photo, and this overlay's flat
  `x/y/w/h` fraction boxes aren't reliable against perspective (a control
  further from the camera renders smaller and shifted in ways a flat box
  can't correct for) — the official MIDI Message List PDF already bundled
  in `docs/controllers/` turned out to have the same style of flat top-down
  diagram used for DDJ-XP2/XDJ-XZ, rendered at 300 DPI with `pdftoppm` and
  cropped the same way. Numark Mixtrack Pro FX completed in
  `v0.47.33-numark-mixtrack-pro-fx-geometry`: PLAY/PAUSE, CUE, SYNC, LOOP,
  and its 8-pad grid — every entry in `catalog/numark_mixtrack_pro_fx.py`.
  Same asset-fix pattern as DDJ-REV1: `assets/controllers/numark-mixtrack-pro-fx.png`
  was an angled marketing photo, replaced with a flat top-down diagram
  cropped from page 3 (the "Top Panel" figure) of the bundled
  `docs/controllers/numark-mixtrack-pro-fx-user-guide-v1.2.pdf`, rendered at
  300 DPI. That PDF is a general user guide, not a MIDI message list like
  the Pioneer PDFs, so unlike DDJ-1000 there was no data table to
  cross-check the catalog's trigger values against — only the geometry came
  from it; the catalog's own values are unchanged from the pre-existing,
  self-disclosed "conservative community profile" in its module docstring.
  DDJ-1000 completed in `v0.47.34-ddj-1000-geometry`: PLAY/PAUSE, CUE,
  MASTER TEMPO, BEAT SYNC, KEY SYNC, KEY RESET, LOOP IN, LOOP OUT, 4 BEAT
  LOOP/EXIT, QUANTIZE, SLIP, SLIP REVERSE, and its 8-pad grid — every entry
  in `catalog/ddj_1000.py` (already fixed to real MIDI values in
  `v0.47.31-ddj-1000-catalog-fix` above). `assets/controllers/ddj-1000.png`
  needed a different fix than DDJ-REV1's: not an angled photo, but a
  low-DPI dump of the *entire* PDF page (title, full device diagram, and the
  MIDI table below it) — unusably imprecise for fraction-based measurement,
  with the actual device occupying a small fraction of the image. Replaced
  with a tight 300 DPI crop of just the top-view device diagram from
  `docs/controllers/ddj-1000-midi-message-list-e1.pdf` page 1 (the same PDF
  the catalog fix used), which conveniently carries the manufacturer's own
  Fig./UI-name callouts (D1-L, D7-L, ...) — each geometry entry's position
  was tied to its catalog name by cross-referencing this PDF's own MIDI
  assignment table (e.g. "D7-L ... BEAT SYNC ... NOTE 88"), not guessed from
  the drawing's layout alone. DDJ-FLX10 completed in
  `v0.47.35-ddj-flx10-geometry`: PLAY/PAUSE, CUE, BEAT SYNC, TEMPO RESET,
  KEY SYNC, ACTIVE PART DRUMS/VOCAL/INST, CUE/LOOP CALL `<`/`>`, LOOP IN,
  LOOP OUT, 4 BEAT/EXIT, MIX POINT SELECT `<`/`>`, MIX POINT LINK, SLIP
  REVERSE, QUANTIZE, SLIP, 4 BEAT JUMP `<`/`>`, SHIFT, and its 8-pad grid —
  every entry in `catalog/ddj_flx10.py` (fully re-transcribed to real MIDI
  values in `v0.47.32-ddj-flx10-catalog-fix` above). Unlike
  DDJ-1000/DDJ-REV1/Numark, `assets/controllers/ddj-flx10.png` needed no
  asset fix at all — it already was a tight, flat, high-DPI top-view crop,
  so this batch went straight to measuring. Every entry's position was tied
  to its catalog name by cross-referencing DDJ-FLX10's own MIDI Message
  List PDF's Fig./UI-name callouts against its assignment table (e.g. PDF
  row "D6 ... BEAT SYNC ... press ... NOTE 88" confirms the button drawn at
  D6 is the catalog's `BEAT SYNC` entry, Data1 88) — the same rigor used for
  DDJ-1000's fix, not assumed from the diagram alone. Some other bundled
  controllers (DDJ-FLX4, Hercules DJControl Inpulse 500) have no such PDF
  available and only an angled photo, so their geometry is deferred until a
  flat diagram source exists — forcing the fraction-box technique onto a
  perspective photo would produce overlay markers that don't actually sit
  on the real button.
- [x] **DDJ-1000 catalog data correction** (`catalog/ddj_1000.py`, related to
  issue [#11](https://github.com/guillain/DJ-MIDI-Studio/issues/11)) —
  discovered while cross-checking DECK section names against the official
  MIDI Message List PDF for the geometry chantier above: PLAY/PAUSE, CUE,
  and every other DECK entry used placeholder sequential Data1 values
  (0-13) instead of the PDF's real numbers, several UI names didn't match
  the real control they described (e.g. `SYNC` → the real button is
  `BEAT SYNC`; `RELOOP/EXIT` → `4 BEAT LOOP/EXIT`; `REVERSE` →
  `SLIP REVERSE`), `KEYLOCK`/`TEMPO RANGE` corresponded to no real discrete
  control and were removed, and the pad grid's channel-to-deck map and note
  formula were both wrong (real channels are 8/9/10/11/12/13/14/15 for
  deck 1-4 plain/+SHIFT, not 6/7/8/9; the grid has 16 real pad-mode banks
  in 8-note blocks, not 8 modes in 16-note blocks). Every corrected value
  was re-verified against the PDF at 300 DPI (`pdftoppm`), not guessed.
  Milestone tag `v0.47.31-ddj-1000-catalog-fix`.
- [x] **DDJ-FLX10 catalog full re-transcription** (`catalog/ddj_flx10.py`,
  issue [#11](https://github.com/guillain/DJ-MIDI-Studio/issues/11)) — its
  catalog had reused DDJ-1000's (equally wrong) values wholesale and only
  covered 12 controls, but DDJ-FLX10 is a materially different, richer
  controller with 22 real DECK controls: it has no separate MASTER TEMPO or
  KEYLOCK button at all, and adds ACTIVE PART DRUMS/VOCAL/INST (rekordbox
  stem control), CUE/LOOP CALL `<`/`>`, MIX POINT SELECT `<`/`>` + MIX
  POINT LINK, and 4 BEAT JUMP `<`/`>`, none of which exist on DDJ-1000.
  Every DECK value was independently re-verified against DDJ-FLX10's own
  PDF at 300 DPI, not carried over from DDJ-1000's (corrected) catalog. The
  8-pad grid's channel map and 16-real-pad-mode-bank formula turned out
  identical to DDJ-1000's once independently checked against DDJ-FLX10's
  own PAD table. `pad_count` corrected from 16 to 8, matching the real
  8-pad grid. Milestone tag `v0.47.32-ddj-flx10-catalog-fix`.
- [ ] Add MIDI-value animation for knobs, faders, pads, jog wheels, and VU meters.
  Partially addressed in `v0.47.20-pad-flash-animation`: a discrete pad/button
  glyph now briefly flashes white on a live MIDI hit (`ControllerLayoutView.flash_key`),
  independent of the persistent red selection border. Further addressed in
  `v0.47.21-knob-fader-animation`: a knob's marker now rotates (-135 to +135
  degrees) and a fader's thumb now moves within its track from the live 7-bit
  MIDI value (`ControllerLayoutView.set_value`), persisting like a real
  control staying wherever it was left. Jog wheels (rotation is relative, not
  an absolute position) and VU meters (no glyph exists yet — an
  output-direction feature) remain open.
- [ ] Add an optional performance mode with larger controls and reduced mapping detail.

### MIDI controller emulation

- [ ] Add a virtual controller emulator with MIDI input/output, mapping, and routing.
- [ ] Add the capability to emulate a real controller's MIDI messages and layout for testing, training, and demonstration purposes.
- [ ] Add a virtual controller with a configurable layout and MIDI message set for testing, training, and demonstration purposes.
- [ ] Add the list of existing controllers to the virtual controller emulator for testing, training, and demonstration purposes.

### External tester feedback (2026-08)

Raised by an external tester (@padi_04) against a pre-`v0.47` build; reviewed
against the current tree and confirmed still open. Tracked as GitHub issues.

- [x] **Controller Setup — bulk-assign Section/Name to selected rows**
  ([#15](https://github.com/guillain/DJ-MIDI-Studio/issues/15)). Delivered in
  `v0.47.8-bulk-section-name`: `Set section for selected rows…` and `Set name
  for selected rows…` (with optional auto-numbering) act on the table
  selection and re-run the conflict check.
- [x] **Controller Setup — attach/upload a reference image from the UI**
  ([#16](https://github.com/guillain/DJ-MIDI-Studio/issues/16)). Delivered in
  `v0.47.11-reference-image`: `Attach reference image…` stores an absolute
  path (not copied into the repo), persisted in the session JSON, carried
  through `build_definition`/`generate_module_source`, and rendered by the
  Controller Images tab after `Apply now` (the viewer now resolves absolute
  paths as well as bundled filenames).
- [x] **Submit manually-created controller profiles to a community catalog**
  ([#17](https://github.com/guillain/DJ-MIDI-Studio/issues/17)). Delivered
  (minimal option) in `v0.47.12-controller-submission`: `Submit to community
  catalog…` in Controller Setup validates the draft, packages it as a
  versioned JSON profile (`catalog/community.py`, Qt-free), copies it to the
  clipboard, and opens a pre-filled `controller-submission`-labelled GitHub
  issue (payload inlined in the URL when short enough, else pasted from the
  clipboard). Contributor metadata via a small dialog; reference images are
  not submitted. A hosted endpoint, moderation pipeline, dedup, and a
  dedicated community-profile repo remain future work.
- [x] **Show only user-enabled controllers in the mapping tabs**
  ([#18](https://github.com/guillain/DJ-MIDI-Studio/issues/18)). Delivered in
  `v0.47.10-enabled-controllers`. The per-controller enable/disable already
  existed (Preferences → *Enabled plugins*, `catalog.set_enabled_plugin_ids`,
  `CONTROLLER_NAMES` served filtered); this adds the missing pieces —
  `View -> Show all controllers` escape hatch (persisted), `Enable/Disable all
  controllers` buttons in Preferences, a usage hint, and test isolation so the
  global filter no longer leaks between tests.
- [ ] **Elements cut off at the default window size on macOS**
  ([#19](https://github.com/guillain/DJ-MIDI-Studio/issues/19)). Partially
  addressed in `v0.47.9-adaptive-window-size`: the first-run size is now
  derived from `screen().availableGeometry()` (preferred `1280x820`, scaled
  down for smaller screens, centered) instead of a fixed `1100x700`. Further
  addressed in `v0.47.22-controller-setup-scroll`: screenshotting the app at
  1100x700 (macOS, `QT_QPA_PLATFORM=cocoa`) found a concrete repro on
  **Controller Setup** — the "MIDI Output" panel's three columns (Send
  message / Playback / Pad modes) compressed below their contents' minimum
  size and overlapped, and the pad-mode grid clipped at the bottom. Fixed by
  wrapping the "MIDI input" + "MIDI Output" row in a `QScrollArea`, which
  enforces the row's real minimum size and shows a scrollbar instead of
  letting it overlap. Still open in case another view/macOS version clips
  differently — the reporter's affected view + macOS version + screenshot
  would confirm whether this was the same one or a second panel remains.

### Next phases to define

No new phase is committed yet. After the Phase 3 hardware validation review,
define the next phase together, including its scope, acceptance criteria,
documentation deliverables, tests, release tag, and any required hardware.

## Tracking rules

- Every phase produces a focused commit and annotated tag.
- A phase is complete only when its contract tests, documentation, diagnostics, and any required external validation are complete.
- Features that are implemented but hardware-unverified stay unchecked in the relevant validation backlog.
- Automatic detection and physical Clock/routing execution remain opt-in and safety-gated.
