# User Guide

## Table of Contents

- [Open a Mapping File](#open-a-mapping-file)
- [Explore Mappings](#explore-mappings)
- [Screens and Layouts](#screens-and-layouts)
- [Edit Safely](#edit-safely)
- [Validate and Export](#validate-and-export)
- [Live Monitor Notes](#live-monitor-notes)
- [Send MIDI Commands](#send-midi-commands)

## Open a Mapping File

1. Start the app.
2. Use `File -> Open...`, choose your mapping file, then select the matching mapping software plugin (`Serato DJ` or `Native Instruments Traktor`).

Traktor mappings use NML/XML files. Automatic software detection is not enabled yet; selecting the plugin explicitly prevents an ambiguous XML extension from choosing the wrong parser.

## Explore Mappings

- `Introduction`: known controllers, context, and quick drill-down.
- `By Channel`: raw model-level controls and mappings.
- `By Deck`: grouped duplicate mappings (safe synchronized edits).
- `By Controller`: physical layout/section perspective.
- `Controller Images`: static official diagrams.
- `Metronome`: repeat the current Controller Setup session rows at a chosen frequency.
- `Controller Setup`: capture/import controller triggers, send one-shot session commands, and generate catalog modules.

For screenshots and a visual description of each tab, see [Screens and Layouts](screens-and-layouts.md).

## Screens and Layouts

- Use `Introduction` as the dashboard for loaded-file status, controller catalog cards, and drill-down shortcuts.
- Use `By Channel` for the raw control and mapping hierarchy.
- Use `By Deck` for grouped per-deck editing and physical layout verification.
- Use `By Controller` for controller/section-oriented physical mapping.
- Use `Controller Images` for zoomable reference diagrams.
- Use `Live Monitor` to inspect real-time MIDI traffic by source device.
- Use `Metronome` to replay Controller Setup rows once or in a loop.

## Edit Safely

- Prefer grouped edits in `By Deck` when dealing with Serato duplicate trigger sets.
- Use the layout views to verify the physical control impacted by your edit.

## Validate and Export

1. Run `Edit -> Validate`.
2. Inspect errors/warnings/info in the right panel.
3. Save with `File -> Save` or `File -> Save As...`.

## Live Monitor Notes

- Input monitoring works from selected MIDI input ports.
- Output-direction monitoring from Serato requires adding the app virtual destination in Serato MIDI setup.

## Send MIDI Commands

Use the CLI helper to send direct NOTE/CC output to a controller:

```bash
uv run djmidi-send-midi --list-ports
uv run djmidi-send-midi --port "Your Port Name" --type note_on --channel 1 --data1 27 --data2 127
uv run djmidi-send-midi --port "Your Port Name" --type note_off --channel 1 --data1 27 --data2 0
```

For DDJ-XP2 mode switching by double-click, you can use:

```bash
uv run djmidi-send-midi --port "Your Port Name" --type note_on --channel 1 --data1 27 --data2 127 --double-click
```

DDJ-XP2 known pad mode button note values (channels 1..4):

- `27` = `PAD MODE 1`
- `30` = `PAD MODE 2`
- `32` = `PAD MODE 3`
- `34` = `PAD MODE 4`

On real hardware, `PAD MODE 5..8` are reached by double-clicking `PAD MODE 1..4`.
So in practice:

- double-click `PAD MODE 1` to reach `PAD MODE 5`
- double-click `PAD MODE 2` to reach `PAD MODE 6`
- double-click `PAD MODE 3` to reach `PAD MODE 7`
- double-click `PAD MODE 4` to reach `PAD MODE 8`

Inside the GUI:

- use `Controller Setup` to send one-shot commands from the current saved/loaded session to the selected MIDI output;
- use `Metronome` when you want loop/repeat playback with a configurable frequency.
