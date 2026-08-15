# ToDo

This file is the project backlog. Completed work is kept below as a historical
delivery record so that the backlog remains useful after each release.

## Table of Contents

- [Active innovation program](#active-innovation-program)
- [Delivered](#delivered)
  - [Core mapping workflow](#core-mapping-workflow)
  - [Mapping views and navigation](#mapping-views-and-navigation)
  - [Controller catalogs](#controller-catalogs)
  - [MIDI tools and live workflows](#midi-tools-and-live-workflows)
  - [Testing, documentation, and delivery](#testing-documentation-and-delivery)
- [Open backlog](#open-backlog)
  - [Plugin-based integrations and dynamic registries](#plugin-based-integrations-and-dynamic-registries)
  - [MIDI API standards decision](#midi-api-standards-decision)
  - [Candidate controller catalogues](#candidate-controller-catalogues)

## Active innovation program

The following program is now the active roadmap. Work is deliberately ordered
by dependency: plugin contracts and declarative profiles first, detection
second, then real-time routing and clock synchronization.

### Phase 0 — baseline plugin architecture

- [x] Controller and DJ software registries discover built-in modules and Python entry points.
- [x] Controller and software lists are consumed dynamically by the current GUI.
- [x] Serato and Traktor are exposed as software plugins.

### Phase 1 — plugin contracts and declarative profiles — COMPLETE

- [x] Define and validate a versioned JSON plugin manifest for controllers and DJ software.
- [x] Add plugin capabilities and permissions to the manifest.
- [x] Support controller profiles from JSON first; evaluate YAML after the schema stabilizes.
- [x] Define schema validation, duplicate-ID handling, and useful diagnostics.
- [x] Add plugin enable/disable state and preferences.
- [x] Add profile fixtures and contract tests that require no MIDI hardware.
- [x] Add plugin lifecycle operations: discover, validate manifest, register, enable/disable, reload, and report compatibility errors.

### MIDI Foundation — normalized MIDI 1.0 API — COMPLETE

- [x] Define normalized port identity/state and raw MIDI message types aligned with Web MIDI concepts.
- [x] Expose available mido ports through the normalized port API while keeping the native MIDI 1.0 transport.
- [x] Preserve raw bytes, timestamps, port identity, realtime messages, and SysEx in the normalized message contract.
- [x] Add deterministic hardware-free tests for ports, messages, SysEx, and plugin detection adapters.

### Phase 2 — assisted integration detection — COMPLETE

- [x] Detect the mapping software from file signature and extension; return a reason and ask for confirmation when ambiguous.
- [x] Detect the controller from MIDI port names and return ranked plugin candidates.
- [x] Show the confidence and reason for a detection result before enabling an integration.
- [x] Keep explicit user selection as the fallback for unknown or ambiguous hardware/software.
- [x] Add MIDI Identity Reply/SysEx parsing, identity metadata hooks, and capability scoring where hardware permits it.

### Phase 3 — multi-device MIDI engine — COMPLETE

- [x] Adopt the W3C [Web MIDI API](https://github.com/WebAudio/web-midi-api) as the conceptual compatibility model for access, input/output ports, events, and SysEx opt-in.
- [x] Keep the native implementation on MIDI 1.0 byte messages through `mido/rtmidi`; do not make a browser API dependency part of the desktop runtime.
- [x] Define an internal normalized MIDI message/port API aligned with Web MIDI naming while preserving realtime messages and timestamps.
- [x] Specify MIDI 2.0/UMP as a future extension instead of mixing it into the initial MIDI 1.0 router.
- [x] Add a one-way MIDI router with port/channel/message filters and loop prevention.
- [x] Add monitoring/status for routes, dropped messages, latency, and errors.
- [x] Add the initial MIDI Clock mirror with Start/Stop/Continue handling, 24 PPQN forwarding, and source selection.
- [x] Add Clock mirror jitter safeguards and timing diagnostics.
- [x] Document Serato, Traktor, and Rekordbox clock-specific behavior before enabling cross-software clock sync.
- [x] Add integration tests with virtual MIDI ports and deterministic fake clocks.
- [x] Reject Clock destinations that are empty, duplicated, or equal to their source.
- [x] Reject feedback loops that combine regular MIDI routes with Clock routes.
- [x] Reset Clock jitter measurement at Start/Continue/Stop boundaries so Serato pauses and restarts do not create false jitter samples.
- [x] Add a live Clock source indicator distinguishing configured, waiting, inactive, and actively receiving states.
- [x] Document the Serato virtual-port troubleshooting path for `CLOCK INACTIVE`.
- [x] Document that Serato DJ Pro is not a native MIDI Clock producer, the direct Link follower, and external bridge alternatives.
- [x] Distinguish an unopened Clock source, a source open without ticks, and transport-only input in the live diagnostic.
- [x] Separate MIDI input and output port selectors so an input such as `MIDI4x4 Midi In 1` cannot be configured as a Clock destination.
- [x] Add a direct Ableton Link follower that generates Start/Continue/Stop and 24 PPQN MIDI Clock without changing Link tempo.
- [x] Add deterministic Link scheduler tests and a clear missing-optional-binding diagnostic.
- [ ] Verify the direct Ableton Link → CoreMIDI output path with Serato, XDJ-XZ, DDJ-XP2, and a real MIDI destination on macOS.
- [ ] Verify the complete Serato → CoreMIDI virtual-port path on a real macOS/Serato setup, including port discovery, Clock output selection, Start/Stop, and sustained 24 PPQN ticks; virtual-port tests alone are not sufficient evidence.

### Phase 4 — safe software/controller operations — IN PROGRESS

- [x] Add read-only software status and configuration capability declarations.
- [x] Add configuration updates only through backup, preview/diff, validation, and rollback.
- [x] Add the hardware-free safe-update engine with backup, preview/diff, validation, atomic apply, and rollback primitives.
- [x] Route GUI Save and Save As through validation, backup, and atomic safe-update writes.
- [x] Add a preferences surface for enabled plugins, detection policy, routing policy, and trust decisions.
- [x] Support unknown devices and unsupported mapping formats through a generic MIDI profile.
- [x] Document plugin installation, updates, compatibility, trust, and troubleshooting.

### Cross-cutting diagnostics

- [x] Add a rotating execution log with configurable DEBUG/INFO/WARNING/ERROR/CRITICAL verbosity and CLI path override.

### Tracking rules

- Every phase produces a focused commit and annotated tag.
- A phase is complete only when its contract tests, documentation, and failure diagnostics are present.
- Automatic detection and Clock/routing remain disabled until their safety tests pass.

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

- [x] Add the `Dashboard` with loaded-file status, controller cards, catalog statistics, MIDI availability indicators, and drill-down shortcuts.
- [x] Use three columns for the Dashboard Controller Overview grid.
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
- [x] Keep layout-cell navigation in the originating tab and fade the previous layout selection as a short history trail.
- [x] Keep layout views synchronized across tabs.
- [x] Increase the Physical control panel height to keep multiple catalog matches readable.
- [x] Make dynamic controller selectors in all layout views horizontally scrollable.
- [x] Add zoomable/pannable `Controller Images` diagrams with reset zoom.
- [x] Remove the obsolete `Go to` section from the Dashboard layout.

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
- [x] Add official reference images for Numark Mixtrack Pro FX and Hercules DJControl Inpulse 500, then declare them in their controller plugins. These are physical product views; a complete annotated MIDI map still requires vendor documentation or hardware capture.
- [x] Add the controller documentation index with official PDF/source URLs, local archives, and an explicit distinction between MIDI message lists, user guides, product sheets, and physical reference images.

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
- [x] Recognize DDJ-XP2's captured second-click NOTE values for PAD MODE 5-8 (28, 31, 33, 35), including shifted variants.
- [x] Add regression coverage proving that every current Pioneer pad-grid profile resolves PAD MODE 1-8.
- [x] Archive the available official controller documents locally and expose them from Controller Images; keep unavailable FLX4 MIDI documentation linked to official support.
- [x] Replay selected or all Controller Setup rows once.
- [x] Move configurable repeated Controller Setup playback into the `MIDI Routing` view and remove the standalone `Metronome` tab.
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
- [x] Complete the Help menu with bundled project documentation, controller PDFs, and official external references.
- [x] Make Live Monitor and MIDI Routing independent closable dock panels, with View-menu toggles and Dashboard shortcuts.
- [x] Translate the Dashboard UI and its tests to English.
- [x] Rename the project to DJ MIDI Studio.

## Open backlog

Ordered by current priority:

- [x] Add the first non-Pioneer controller plugins: Numark Mixtrack Pro FX and Hercules DJControl Inpulse 500. Their initial discrete-control profiles are conservative and must be verified against specific hardware/firmware captures before production use.
- [ ] Continue adding controller models beyond the current DDJ-XP2, XDJ-XZ, DDJ-1000, DDJ-FLX4, DDJ-FLX10, DDJ-REV1, Numark Mixtrack Pro FX, and Hercules DJControl Inpulse 500 catalog. The shortlist below is ordered by a combination of market reach, availability of official MIDI documentation, and fit with the current catalog architecture.
- [x] Add support for Traktor through the Native Instruments Traktor software plugin; keep Rekordbox and VirtualDJ open. The plugin now has a dedicated guide documenting NML/TSI detection, NOTE/CC normalization, export behavior, and unsupported advanced Traktor features.
- [x] Automatically detect the connected controller and enable the correct catalog module.
- [x] Add automatic detection of the DJ software and enable the correct mapping parser.
- [x] Cover Serato and Traktor Clock-specific routing behavior and safeguards; Rekordbox compatibility remains separately constrained by vendor/version verification.
- [x] Keep the Clock roadmap wording aligned with the implemented Serato/Traktor compatibility documentation.
- [x] Add Clock mirror and MIDI routing support for multi-device setups.
- [x] Add the GUI configuration surface for MIDI routes and opt-in Clock policies.
- [x] Add controlled physical route execution behind the Preferences routing flag, with fake-port integration tests.
- [x] Execute the configured MIDI Clock mirror through the same opt-in physical routing session, with fake-port tests.
- [x] Support multiple independent Clock source/destination configuration lines in the routing UI and session.
- [x] Add a virtual MIDI input path for receiving Serato Clock, including Start/Stop transport forwarding documentation.
- [x] Add more end-to-end examples and use cases to the documentation.
- [x] Extend the advanced user guide with deeper vendor-specific workflows and troubleshooting.

### Plugin-based integrations and dynamic registries

The controller catalog already has a dynamic in-process registry. The next
step is to make both hardware and DJ software integrations discoverable
plugins, so adding an integration does not require editing a central hardcoded
list or the GUI.

- [x] Define a stable plugin contract for MIDI controller integrations, including identifier, display name, manufacturer, supported software, MIDI capabilities, catalog definition, layout metadata, reference images, and documentation links.
- [x] Define a stable plugin contract for DJ software integrations, including identifier, display name, mapping-file format, parser, exporter, validation rules, and supported mapping features.
- [x] Split the current controller registry API from the future software registry API while sharing common plugin metadata and discovery mechanisms.
- [x] Move controller and software lists to registry-backed/dynamically discovered sources throughout the GUI, Dashboard, filters, and documentation helpers.
- [x] Support explicit plugin discovery from built-in modules and external Python package entry points.
- [x] Add plugin lifecycle operations: discover, validate manifest, register, enable/disable, reload, and report compatibility errors.
- [x] Add a plugin manifest/version format with API compatibility, plugin version, vendor, license, and required application version.

### MIDI API standards decision

The W3C Web MIDI API is the reference for public concepts and naming, not the
native transport implementation. The desktop engine must remain usable
without a browser and must expose MIDI 1.0 channel voice messages, system
realtime messages, timestamps, port identity, and explicit SysEx permissions.
MIDI 2.0 Universal MIDI Packets (UMP) will be handled by a later adapter once
the MIDI 1.0 router and Clock mirror are stable.
- [x] Add a preferences/settings surface for choosing enabled controller and software plugins.
- [x] Apply enabled-plugin preferences to active controller/software lists, detection, lookup, and parser selection.
- [x] Resolve the active controller/software integration from a connected MIDI device, imported mapping file, or explicit user selection.
- [x] Keep unknown devices and unsupported mapping formats usable through a generic MIDI profile instead of failing application startup.
- [x] Add trust checks before loading third-party plugins, with clear diagnostics for rejected or unavailable plugins; document that Python entry points remain in-process.
- [x] Add plugin contract tests and discovery tests that run without MIDI hardware.
- [x] Document how to create, install, update, and troubleshoot a third-party controller or software plugin.

### Candidate controller catalogues

#### Priority 1 — Pioneer DJ ecosystem

- [x] **DDJ-FLX4** — initial conservative two-deck/eight-pad profile and official product reference image delivered; MIDI values remain provisional pending an FLX4-specific message list or hardware capture.
- [x] **DDJ-FLX10** — initial conservative four-deck profile delivered; the official MIDI message list and annotated reference artwork are archived in `docs/controllers/` and `assets/controllers/`. Firmware capture remains verification work.
- [x] **DDJ-REV1** — official MIDI Message List E1 archived, conservative Serato profile delivered, and official reference artwork added; continuous controls remain outside the normalized catalog.
- [ ] **DDJ-REV5** — current two-deck battle controller with substantial Serato usage and a distinct pad/deck layout.
- [ ] **DDJ-800** — established two-channel Rekordbox controller, useful for users between entry-level and flagship hardware.

#### Priority 2 — other widely used ecosystems

- [ ] **Native Instruments Traktor Kontrol S2 MK3** — common Traktor entry point and a representative non-Pioneer catalog.
- [x] **Numark Mixtrack Pro FX** — initial discrete-control plugin profile added; verify against the target firmware/software combination.
- [x] **Hercules DJControl Inpulse 500** — initial discrete-control plugin profile added; verify against the target firmware/software combination.
- [ ] **RANE FOUR** — established four-channel Serato controller with a distinct professional layout.
- [ ] **Denon DJ Prime 4+** — widely used standalone four-deck system and a useful Engine DJ/Serato comparison point.

#### Integration checklist for each candidate

- [ ] Obtain and archive the manufacturer's official MIDI message list or verify the mapping from hardware capture. DDJ-FLX4, Numark Mixtrack Pro FX, and Hercules DJControl Inpulse 500 remain open pending controller-specific evidence; see `docs/controllers/README.md`. DDJ-REV1 is archived and verified against the vendor list, but still benefits from a hardware capture.
- [x] Add the controller module and registration entry with static controls, pad lookup, section order, and layout metadata for DDJ-FLX4.
- [x] Add the official DDJ-FLX4 product reference image; an annotated MIDI map remains open.
- [x] Add catalog lookup, layout, and image-view coverage for DDJ-FLX4.
- [x] Document the supported software, firmware assumptions, MIDI channels, and known limitations for DDJ-FLX4.
- [x] Add DDJ-REV1 catalog lookup, layout, image-view tests, official MIDI documentation, and profile limitations.

#### Innovations

- [ ] Add MIDI API support for:
  - [ ] MIDI controller configuration updates, monitoring/status, and advanced features (e.g., mirroring, routing, clock/sync).
  - [ ] DJ software configuration updates, monitoring/status, and advanced features (e.g., multi-deck, multi-controller, and multi-software setups).
- [x] Add the initial plugin-based architecture for controller and software integrations, with dynamic discovery and registration; plugin manifests/versioning remain open below.
- [x] Add automatic detection of the DJ software and enable the correct mapping parser.
- [x] Add Clock mirror and MIDI routing support for multi-device setups (/!\ Serato & Rekordbox clock specificities! /!\).
- [ ] Controlleur and Software plugins can be added by external configuration file (yaml/json)
- [x] Add a plugin manifest/version format with API compatibility, plugin version, vendor, license, and required application version.
