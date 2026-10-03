# 🛠️ Developer documentation

> How DJ MIDI Studio is built: its services, its design, how to set it up,
> test it, ship it, and work on it with AI agents.

📍 [Docs](../README.md) › Developer

## Table of Contents

- [Services at a glance](#services-at-a-glance)
- [Start here](#start-here)
- [In this section](#in-this-section)

## Services at a glance

The code lives in `src/djmidi/`. Every service below except `gui/` is
Qt-free and tested on its own.

| Service | Modules | Responsibility |
| --- | --- | --- |
| Mapping core | `model.py`, `parser.py`, `exporter.py`, `validator.py`, `safe_update.py` | Typed model of a Serato mapping, byte-identical round-trip, structural and conflict checks, validated/backed-up/atomic saves |
| DJ software plugins | `software/` (`serato.py`, `traktor.py`, `_tsi.py`), `binary_chunks.py` | Parse and export each software's mapping format; Traktor `.tsi` binary-in-XML codec |
| Controller catalog | `catalog/` (`_registry.py`, one module per controller, `codegen.py`, `community.py`, `profile.py`) | Plugin-style registry naming each controller's MIDI triggers; profile generation and community submission |
| Plugin system | `plugins/` (`manifest.py`, `lifecycle.py`, `preferences.py`), `integration_detection.py`, `generic_profile.py` | Manifests, discovery and trust, preferences, software/controller detection |
| MIDI engine | `midi_api.py`, `midi_io.py`, `midi_router.py`, `midi_routing_session.py`, `midi_virtual.py`, `midi_send.py`, `session_player.py` | Normalized MIDI 1.0 I/O, live monitoring, one-way routing, virtual ports, playback |
| Clock | `midi_clock.py`, `ableton_link.py` | Clock mirror with jitter safeguards; Ableton Link follower emitting 24 PPQN |
| Controller Sync | `controller_sync.py` | Per-controller initialization sets and port resolution |
| Music library | `library/` (`db.py`, `scanner.py`, `metadata.py`, `analysis.py`, `playlist.py`, `serato_library.py`, `traktor_library.py`, `rekordbox_library.py`, `workspace.py`) | SQLite index, incremental scan, surgical tag writes, BPM/Camelot, playlists, DJ-software library formats |
| Taxonomy | `taxonomy/` | Genre family/category registry, aliases, fuzzy suggestions |
| GUI | `gui/` | PySide6 application: tabs, docks, layouts, emulator, Music Library |

The [architecture](design/architecture.md) page shows how they fit together.

## Start here

| I want to… | Read |
| --- | --- |
| Run the app from source | [Quickstart](setup/quickstart.md), then [Developer setup](setup/setup.md) |
| Understand the code | [Architecture](design/architecture.md) |
| Make a change | [Development workflow](workflow.md) and [Contributing](contributing.md) |
| Add a controller or plugin | [Plugin manifest](design/plugin-manifest.md), [Supported controllers](../enduser/controller-profiles.md), `CLAUDE.md` |
| Run the checks | [Testing and quality](cicd/testing-and-quality.md), [Quality gates](cicd/quality-gates.md) |
| Ship a release | [Build and release](cicd/build-and-release.md), [Release checklist](cicd/release-checklist.md) |
| Work with an AI agent | [AI-assisted development](agent/ai-assisted-development.md) |

The backlog is [`TODO.md`](../../TODO.md); the detailed maintainer notes
are in [`CLAUDE.md`](../../CLAUDE.md).

## In this section

| Page | What it covers |
| --- | --- |
| [setup/](setup/README.md) | Quickstart and developer environment |
| [design/](design/README.md) | Architecture, plugin manifest, evolution record |
| [cicd/](cicd/README.md) | Tests, quality gates, build, release |
| [agent/](agent/README.md) | AI-assisted development guide and reusable agent assets |
| [Development workflow](workflow.md) | Branch, implement, validate, document |
| [Contributing](contributing.md) | What to contribute and pull request checklist |
