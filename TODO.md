# ToDo

This file is the project backlog. Completed work is kept below as a historical
delivery record so that the backlog remains useful after each release.

## Delivered

### Core mapping workflow

- [x] Parse Serato MIDI XML into a typed domain model.
- [x] Export the edited model back to Serato-compatible XML.
- [x] Validate required fields, supported values, duplicate triggers, and mapping conflicts.
- [x] Edit controls, UserIO entries, translations, aliases, and mapping associations from the GUI.
- [x] Add undo/redo support for GUI edits.
- [x] Add tree search/filtering.
- [x] Save, Save As, and reopen mapping files.

### Mapping views and navigation

- [x] Add the `Introduction` dashboard with loaded-file status, controller cards, catalog statistics, and drill-down shortcuts.
- [x] Add the `By Channel` view with one resizable column per MIDI channel.
- [x] Add the `By Deck` view with one resizable column per Serato deck and slot-oriented mapping groups.
- [x] Add the `By Controller` view with one column per controller and grouped catalog sections.
- [x] Pair the channel, deck, and controller trees with physical layout views.
- [x] Add clickable schematic controller layouts.
- [x] Show each controller's interpretation of a physical layout cell.
- [x] Color layout cells according to the Serato deck using the control.
- [x] Display mapped Serato functions inside layout cells.
- [x] Highlight matching layout cells from tree selections and matching tree entries from layout selections.
- [x] Navigate from layout/controller selections back to the underlying raw control.
- [x] Keep layout views synchronized across tabs.
- [x] Add zoomable/pannable `Controller Images` diagrams with reset zoom.
- [x] Remove the obsolete `Go to` section from the Introduction layout.

### Controller catalogs

- [x] Add the DDJ-XP2 catalog.
- [x] Add the XDJ-XZ catalog.
- [x] Add the DDJ-1000 catalog.
- [x] Convert the catalog into a plugin-style dynamic registry.
- [x] Resolve catalog entries for static controls and pad grids.
- [x] Generate catalog module source from learned/imported controls.
- [x] Detect conflicts before applying or exporting a generated catalog.
- [x] Apply a generated controller catalog immediately for the current session.
- [x] Refresh controller-dependent views after applying a catalog.
- [x] Add DDJ-1000 reference mapping artwork to the controller image assets.

### MIDI tools and live workflows

- [x] Add the `Live Monitor` tab for real-time MIDI input/output monitoring.
- [x] Monitor several MIDI input sources at once.
- [x] Add `Select all sources` and port refresh controls.
- [x] Display the source device in a dedicated Live Monitor column.
- [x] Resolve physical controls using the source device to avoid cross-controller false matches.
- [x] Display associated Serato functions in the Live Monitor.
- [x] Save Live Monitor events as CSV.
- [x] Add a virtual MIDI destination for monitoring Serato output, with setup guidance.
- [x] Add the `Controller Setup` workflow for MIDI learning and Serato XML import.
- [x] Record the source and device for learned/imported Controller Setup rows.
- [x] Send one-shot MIDI NOTE/CC commands from Controller Setup.
- [x] Send DDJ-XP2 pad-mode double-click commands.
- [x] Replay selected or all Controller Setup rows once.
- [x] Add the `Metronome` tab for configurable repeated session playback.
- [x] Add the `djmidi-send-midi` CLI command and `--double-click` helper.

### Testing, documentation, and delivery

- [x] Add unit and GUI tests for the parser, exporter, validator, catalogs, layouts, controller setup, MIDI I/O, and session playback.
- [x] Add quick, full, lint, path, and quality test modes through `scripts/test.sh`.
- [x] Add the quality gate for coverage, code smells, duplication, and security findings.
- [x] Add bootstrap, build, executable packaging, and release artifact scripts.
- [x] Add CI workflows for cross-platform executable builds and draft releases.
- [x] Add provider-neutral SCM release orchestration for GitHub/GitLab.
- [x] Add the documentation portal, quickstart, user guide, architecture, testing, quality, build, and release documentation.
- [x] Add the visual [Screens and Layouts](docs/screens-and-layouts.md) documentation with application screenshots.
- [x] Translate the Introduction UI and its tests to English.
- [x] Rename the project to DJ MIDI Studio.

## Open backlog

Ordered by current priority:

- [x] Add the first non-Pioneer controller plugins: Numark Mixtrack Pro FX and Hercules DJControl Inpulse 500. Their initial discrete-control profiles are conservative and must be verified against specific hardware/firmware captures before production use.
- [ ] Continue adding controller models beyond DDJ-XP2, XDJ-XZ, DDJ-1000, Numark Mixtrack Pro FX, and Hercules DJControl Inpulse 500. The shortlist below is ordered by a combination of market reach, availability of official MIDI documentation, and fit with the current catalog architecture.
- [ ] Add support for additional DJ software vendors, such as Traktor, Rekordbox, and VirtualDJ.
- [ ] Automatically detect the connected controller and enable the correct catalog module.
- [ ] Add automatic detection of the DJ software and enable the correct mapping parser.
- [ ] Add Clock mirror and MIDI routing support for multi-device setups.
- [ ] Add more end-to-end examples and use cases to the documentation.
- [ ] Extend the advanced user guide with deeper vendor-specific workflows and troubleshooting.

### Plugin-based integrations and dynamic registries

The controller catalog already has a dynamic in-process registry. The next
step is to make both hardware and DJ software integrations discoverable
plugins, so adding an integration does not require editing a central hardcoded
list or the GUI.

- [ ] Define a stable plugin contract for MIDI controller integrations, including identifier, display name, manufacturer, supported software, MIDI capabilities, catalog definition, layout metadata, reference images, and documentation links.
- [ ] Define a stable plugin contract for DJ software integrations, including identifier, display name, mapping-file format, parser, exporter, validation rules, and supported mapping features.
- [ ] Split the current controller registry API from the future software registry API while sharing common plugin metadata and discovery mechanisms.
- [ ] Move controller and software lists to registry-backed/dynamically discovered sources throughout the GUI, Introduction dashboard, filters, and documentation helpers.
- [ ] Support explicit plugin discovery from built-in modules and external Python package entry points.
- [ ] Add plugin lifecycle operations: discover, validate manifest, register, enable/disable, reload, and report compatibility errors.
- [ ] Add a plugin manifest/version format with API compatibility, plugin version, vendor, license, and required application version.
- [ ] Add a preferences/settings surface for choosing enabled controller and software plugins.
- [ ] Resolve the active controller/software integration from a connected MIDI device, imported mapping file, or explicit user selection.
- [ ] Keep unknown devices and unsupported mapping formats usable through a generic MIDI profile instead of failing application startup.
- [ ] Add isolation and trust checks before loading third-party plugins, with clear diagnostics for rejected or unavailable plugins.
- [ ] Add plugin contract tests and discovery tests that run without MIDI hardware.
- [ ] Document how to create, install, update, and troubleshoot a third-party controller or software plugin.

### Candidate controller catalogues

#### Priority 1 — Pioneer DJ ecosystem

- [ ] **DDJ-FLX4** — highly widespread entry-level Rekordbox/Serato controller; strong first addition for broad user coverage.
- [ ] **DDJ-FLX10** — current four-deck professional controller; an official MIDI message list is already present in `docs/controllers/`.
- [ ] **DDJ-REV1** — popular Serato-oriented entry-level battle controller with a layout distinct from the DDJ-FLX range.
- [ ] **DDJ-REV5** — current two-deck battle controller with substantial Serato usage and a distinct pad/deck layout.
- [ ] **DDJ-800** — established two-channel Rekordbox controller, useful for users between entry-level and flagship hardware.

#### Priority 2 — other widely used ecosystems

- [ ] **Native Instruments Traktor Kontrol S2 MK3** — common Traktor entry point and a representative non-Pioneer catalog.
- [x] **Numark Mixtrack Pro FX** — initial discrete-control plugin profile added; verify against the target firmware/software combination.
- [x] **Hercules DJControl Inpulse 500** — initial discrete-control plugin profile added; verify against the target firmware/software combination.
- [ ] **RANE FOUR** — established four-channel Serato controller with a distinct professional layout.
- [ ] **Denon DJ Prime 4+** — widely used standalone four-deck system and a useful Engine DJ/Serato comparison point.

#### Integration checklist for each candidate

- [ ] Obtain and archive the manufacturer's official MIDI message list or verify the mapping from hardware capture.
- [ ] Add the controller module and registration entry with static controls, pad lookup, section order, and layout metadata.
- [ ] Add the reference mapping image and a representative fixture/configuration.
- [ ] Add catalog lookup, layout, image-view, and Live Monitor tests.
- [ ] Document the supported software, firmware assumptions, MIDI channels, and known limitations.

#### Innovations

- [ ] Add MIDI API support for:
  - [ ] MIDI controller configuration updates, monitoring/status, and advanced features (e.g., mirroring, routing, clock/sync).
  - [ ] DJ software configuration updates, monitoring/status, and advanced features (e.g., multi-deck, multi-controller, and multi-software setups).
- [ ] Add a plugin-based architecture for controller and software integrations, with dynamic discovery, registration, and versioning.
- [ ] Add automatic detection of the DJ software and enable the correct mapping parser.
- [ ] Add Clock mirror and MIDI routing support for multi-device setups (/!\ Serato & Rekordbox clock! /!\).