# User Guide

## Table of Contents

- [Open a Serato XML File](#open-a-serato-xml-file)
- [Explore Mappings](#explore-mappings)
- [Edit Safely](#edit-safely)
- [Validate and Export](#validate-and-export)
- [Live Monitor Notes](#live-monitor-notes)
- [Send MIDI Commands](#send-midi-commands)

## Open a Serato XML File

1. Start the app.
2. Use `File -> Open...` and choose your Serato MIDI XML.

## Explore Mappings

- `Introduction`: known controllers, context, and quick drill-down.
- `By Channel`: raw model-level controls and mappings.
- `By Deck`: grouped duplicate mappings (safe synchronized edits).
- `By Controller`: physical layout/section perspective.
- `Controller Images`: static official diagrams.

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
uv run seratomidiconf-send-midi --list-ports
uv run seratomidiconf-send-midi --port "Your Port Name" --type note_on --channel 1 --data1 27 --data2 127
uv run seratomidiconf-send-midi --port "Your Port Name" --type note_off --channel 1 --data1 27 --data2 0
```

DDJ-XP2 known pad mode button note values (channels 1..4):

- `27` = `PAD MODE 1`
- `30` = `PAD MODE 2`
- `32` = `PAD MODE 3`
- `34` = `PAD MODE 4`

There is no dedicated static `PAD MODE 5` button trigger in the transcribed
DDJ-XP2 static table; mode-5 pad labels come from the pad-grid lookup layer.

