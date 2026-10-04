# 📖 User guide

> From download to your first edited mapping: install, first launch,
> supported files, the everyday workflow, and troubleshooting.

📍 [Docs](../README.md) › [End user](README.md) › User guide

## Table of Contents

- [Install](#install)
- [First launch](#first-launch)
- [Supported files](#supported-files)
- [Everyday workflow](#everyday-workflow)
- [Controller detection](#controller-detection)
- [Send MIDI from the command line](#send-midi-from-the-command-line)
- [Logs and troubleshooting](#logs-and-troubleshooting)
- [Related](#related)

## Install

1. Download the archive for your system (macOS, Windows or Linux) from the
   [latest release](https://github.com/guillain/DJ-MIDI-Studio/releases/latest).
2. Check it against the published `SHA-256` checksums.
3. Unpack it and run `djmidi`. No Python or other install is needed.

**macOS:** the app is not signed. On first launch, right-click it → `Open`
(or clear the quarantine flag) to get past Gatekeeper.

The documentation and the controller manuals are bundled, so everything in
the `Help` menu works offline.

## First launch

- **Helpful Notes** opens with quick tips (reopen it from `View`).
- The **Dashboard** shows every built-in controller. If you only own one or
  two, open ⚙ **Preferences** → `Plugins` and disable the others so the
  selectors stay short.
- Plug in your controllers: the Dashboard marks them `MIDI: available`.

Your window layout, tool settings and preferences are kept between
launches. See [Workspace and preferences](features/workspace.md).

## Supported files

| File | Software | What you can do |
| --- | --- | --- |
| `.xml` MIDI mapping | Serato DJ Pro | Open, explore, edit, validate, save ([Mapping editor](features/mapping-editor.md)) |
| `.tsi` controller mapping | Traktor Pro | Open, explore, re-assign MIDI triggers ([Traktor mappings](features/traktor-mappings.md)) |
| `.crate` crates | Serato | Import playlists, export new crates ([Music Library](features/music-library.md)) |
| `collection.nml` | Traktor | Import playlists; export a new playlist `.nml` |
| `export.pdb` (USB export) | Rekordbox | Import playlists |
| MP3, WAV, AIFF, FLAC, M4A, OGG, AAC | — | Read and write tags |
| Session `.json` | DJ MIDI Studio | Save and reload a [Controller Setup](features/controller-setup.md) draft |

Library files are only ever read: exports always create a new file.

## Everyday workflow

1. **Open** a mapping with `File → Open…`.
2. **Explore** it in `By Channel`, `By Deck` or `By Controller`, or click
   through it in a [Controller Emulator](features/controller-emulator.md).
3. **Check live** what each button does with the
   [Live Monitor](features/live-monitor.md); it starts by itself when a
   mapping is loaded.
4. **Edit** in the right-hand panel; `Edit → Undo` is always available.
5. **Validate** with `Edit → Validate`.
6. **Save** with `File → Save`; you see the exact changes first, a backup is
   kept, and `File → Rollback Last Save` restores it.

New controller? Start with [Controller Setup](features/controller-setup.md).
Before a gig, [Controller Sync](features/controller-sync.md) puts every
controller in its starting state in one click.

## Controller detection

The app can recognize the software of a mapping file and the controllers on
your MIDI ports. With the default `Ask before enabling` (⚙ Preferences), it
asks before using what it detected; `Suggest detected integration` applies a
confident match automatically. An uncertain match is never applied silently.

An unknown controller still works: Live Monitor shows its raw messages, and
[Controller Setup](features/controller-setup.md) turns them into a profile.

## Send MIDI from the command line

When running from source (see [Developer setup](../developer/setup/setup.md)),
`djmidi-send-midi` sends one Note or CC to a port, handy for scripts or to
test a controller. The release builds include only the app itself.

```bash
uv run djmidi-send-midi --list-ports
uv run djmidi-send-midi --port "Your Port Name" --type note_on --channel 1 --data1 27 --data2 127
uv run djmidi-send-midi --port "Your Port Name" --type note_off --channel 1 --data1 27 --data2 0
uv run djmidi-send-midi --port "Your Port Name" --type note_on --channel 1 --data1 27 --data2 127 --double-click
```

Example, DDJ-XP2 pad modes (channels 1–4): `PAD MODE 1–4` are notes `27`,
`30`, `32`, `34`. A double-click on them reaches `PAD MODE 5–8`, which the
hardware sends as the distinct notes `28`, `31`, `33`, `35`.

In the app, [Controller Setup](features/controller-setup.md#send-midi-back-to-the-controller)
sends one-shot messages and the
[Metronome](features/midi-routing-and-clock.md#metronome) plays them on a
loop.

## Logs and troubleshooting

The app keeps a rotating log in your system's user log folder. To report a
problem, start it with more detail and an explicit file:

```bash
djmidi --log-level DEBUG --log-file /tmp/djmidi.log
```

Levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. You can also set
them in ⚙ Preferences.

| Symptom | Try |
| --- | --- |
| A controller isn't listed | Check it is enabled in ⚙ Preferences → `Plugins`, or tick `View → Show all controllers` |
| No events in Live Monitor | `Refresh ports`, tick the controller's input, `Start monitoring`; another app may hold the port |
| Serato's LED feedback doesn't show | Add `DJMidiStudio Monitor` as an extra MIDI output in Serato |
| `CLOCK INACTIVE` | See [MIDI Clock compatibility](midi-clock-compatibility.md) |
| macOS full screen turns black | Leave full screen once and re-enter it |

## Related

- [Features](features/README.md)
- [End-to-end examples](examples.md)
- [Supported controllers](controller-profiles.md)
