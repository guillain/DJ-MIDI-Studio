# DJ MIDI Studio 🎛️

> The DJ's MIDI workbench: set up and sync any controller, watch your MIDI
> live, play your controller on screen, edit Serato and Traktor mappings
> safely, and get your music library mix-ready.

<p align="center">
  <a href="https://github.com/guillain/DJ-MIDI-Studio/actions/workflows/build-executables.yml"><img src="https://github.com/guillain/DJ-MIDI-Studio/actions/workflows/build-executables.yml/badge.svg" alt="CI status"></a>
  <a href="https://github.com/guillain/DJ-MIDI-Studio/releases"><img src="https://img.shields.io/github/v/release/guillain/DJ-MIDI-Studio?include_prereleases" alt="Latest release"></a>
  <a href="docs/README.md"><img src="https://img.shields.io/badge/docs-local%20%26%20bundled-6f42c1" alt="Documentation"></a>
</p>

<p align="center">
  <img src="docs/images/layout/dashboard.png" alt="DJ MIDI Studio dashboard" width="900">
</p>

## Table of Contents

- [Highlights](#highlights)
- [Also in the box](#also-in-the-box)
- [Supported hardware and software](#supported-hardware-and-software)
- [Install](#install)
- [Documentation](#documentation)
- [For developers](#for-developers)

## Highlights

### 🎛️ Controller Setup and ⟳ Sync

Teach the app **any** MIDI controller by pressing its buttons, or import a
Serato mapping you already use. No manufacturer documentation needed. Then
record the buttons you always press after plugging in, and put **every
connected controller** in that state with one click on `⟳ Sync`.
→ [Controller Setup](docs/enduser/features/controller-setup.md) ·
[Controller Sync](docs/enduser/features/controller-sync.md)

<p align="center"><img src="docs/images/layout/controlleur-setup-ddj-xp2.png" alt="Controller Setup" width="800"></p>

### 📡 Live Monitor

Every MIDI message, translated into the physical control and the DJ-software
function it triggers — and the whole app reacts as you play: pads flash,
knobs turn, jog wheels spin, Serato's LED feedback lights up on screen.
→ [Live Monitor](docs/enduser/features/live-monitor.md)

<p align="center"><img src="docs/images/layout/live-monitor.png" alt="Live Monitor" width="800"></p>

### 🎵 Music Library

Scan tens of thousands of tracks, fix tags on a whole selection at once, read
every key on the Camelot wheel, sort tracks into genre categories that follow
your own folders and crates, and build harmonic playlists for Serato and
Traktor — without ever touching their data inside your files.
→ [Music Library](docs/enduser/features/music-library.md)

<p align="center"><img src="docs/images/layout/music-library.png" alt="Music Library" width="800"></p>

### 🕹️ Controller Emulator

A clickable twin of your controller on its real photo: click a pad to see
what the mapping does, switch pad modes, latch SHIFT, and turn on
`Live send` to play your DJ software from the screen.
→ [Controller Emulator](docs/enduser/features/controller-emulator.md)

<p align="center"><img src="docs/images/controllers/ddj-xp2.png" alt="Controller Emulator" width="700"></p>

## Also in the box

| | Feature | In one line |
| --- | --- | --- |
| 🗺️ | [Mapping editor](docs/enduser/features/mapping-editor.md) | Serato mappings by channel, deck or physical control; grouped edits, validation, diff before save, rollback |
| 🎧 | [Traktor mappings](docs/enduser/features/traktor-mappings.md) | Open Traktor `.tsi` mappings and re-assign MIDI triggers byte-safely |
| 🖼️ | [Controller Images](docs/enduser/features/controller-images.md) | Official diagrams and manuals, offline, with real control positions |
| 🔀 | [MIDI Routing, Clock and Metronome](docs/enduser/features/midi-routing-and-clock.md) | Route MIDI, generate 24 PPQN MIDI Clock from Ableton Link, loop MIDI |
| 🪟 | [Workspace and preferences](docs/enduser/features/workspace.md) | Dockable tools, Performance Mode, light/dark theme |

## Supported hardware and software

- **DJ software:** Serato DJ Pro (`.xml` mappings, crates), Traktor Pro
  (`.tsi` mappings, `collection.nml` playlists), Rekordbox (USB
  `export.pdb` playlists).
- **Controllers:** Pioneer DDJ-XP2, XDJ-XZ, DDJ-1000, DDJ-FLX4, DDJ-FLX10,
  DDJ-REV1, DDJ-REV5, DDJ-800, Numark Mixtrack Pro FX, Hercules DJControl
  Inpulse 500, Behringer CMD LC-1, CMD Micro, CMD Studio 4a, Korg nanoPAD2 — plus any controller through Controller Setup.
  [Verification status](docs/enduser/controller-profiles.md).
- **Systems:** macOS, Windows, Linux.

## Install

📦 Download the archive for your system from the
[latest release](https://github.com/guillain/DJ-MIDI-Studio/releases/latest),
unpack it and run `djmidi`. No Python needed; the documentation and
controller manuals are bundled, so the `Help` menu works offline.

- Check the download against the published `SHA-256` checksums.
- macOS: the app is unsigned; on first launch right-click → `Open`.
- To report a problem, run with `--log-level DEBUG --log-file <path>`.

Then follow the [User guide](docs/enduser/user-guide.md).

## Documentation

| | |
| --- | --- |
| 🎧 [End user documentation](docs/enduser/README.md) | Features, user guide, recipes, supported controllers |
| 🛠️ [Developer documentation](docs/developer/README.md) | Services, architecture, setup, CI/CD, AI-assisted development |
| 📚 [Documentation home](docs/README.md) | Map of every page |
| 📖 [Controller references](controllers/README.md) | Bundled manuals and MIDI message lists |

## For developers

Running from source takes `uv` and Python 3.14:

```bash
uv sync --group dev
uv run djmidi
uv run pytest
```

Start with the [Quickstart](docs/developer/setup/quickstart.md) and the
[services overview](docs/developer/README.md). Releases are built by GitHub
Actions from annotated `v*` tags ([Build and release](docs/developer/cicd/build-and-release.md)).
This project is developed with AI assistance under human review; see
[AI-assisted development](docs/developer/agent/ai-assisted-development.md).
