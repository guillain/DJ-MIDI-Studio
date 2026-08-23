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
- [Open backlog](#open-backlog)
  - [Phase 3 hardware validation](#phase-3-hardware-validation)
  - [Candidate controller catalogues](#candidate-controller-catalogues)
  - [Future MIDI API extensions](#future-midi-api-extensions)
  - [Next phases to define](#next-phases-to-define)

## Current roadmap status

The implementation roadmap is complete through Phase 4. Phase 3 remains
`IN PROGRESS — HARDWARE VALIDATION` because the software contracts, tests, and
diagnostics are delivered, but two macOS integrations still require a real
Serato/XDJ-XZ/DDJ-XP2 setup. No implementation item is being relabeled as
complete until that distinction is explicit.

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

### Phase 3 — multi-device MIDI engine — IN PROGRESS — HARDWARE VALIDATION

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

## Open backlog

### Phase 3 hardware validation

- [ ] Verify the direct Ableton Link → CoreMIDI output path with Serato, XDJ-XZ, DDJ-XP2, and a real MIDI destination on macOS.
- [ ] Verify the complete Serato → CoreMIDI virtual-port path on a real macOS/Serato setup, including port discovery, Clock output selection, Start/Stop, and sustained 24 PPQN ticks.

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
- [ ] Add MIDI-value animation for knobs, faders, pads, jog wheels, and VU meters.
- [ ] Add an optional performance mode with larger controls and reduced mapping detail.

### MIDI controller emulation

- [ ] Add a virtual controller emulator with MIDI input/output, mapping, and routing.
- [ ] Add the capability to emulate a real controller's MIDI messages and layout for testing, training, and demonstration purposes.
- [ ] Add a virtual controller with a configurable layout and MIDI message set for testing, training, and demonstration purposes.
- [ ] Add the list of existing controllers to the virtual controller emulator for testing, training, and demonstration purposes.

### Next phases to define

No new phase is committed yet. After the Phase 3 hardware validation review,
define the next phase together, including its scope, acceptance criteria,
documentation deliverables, tests, release tag, and any required hardware.

## Tracking rules

- Every phase produces a focused commit and annotated tag.
- A phase is complete only when its contract tests, documentation, diagnostics, and any required external validation are complete.
- Features that are implemented but hardware-unverified stay unchecked in the relevant validation backlog.
- Automatic detection and physical Clock/routing execution remain opt-in and safety-gated.
