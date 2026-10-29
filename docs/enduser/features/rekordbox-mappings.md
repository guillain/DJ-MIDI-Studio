# 🎛️ rekordbox mappings

> 🎛️ rekordbox MIDI mappings (`.midi.csv`) open read-only in the same
> channel, deck and control views as Serato and Traktor mappings, so you can
> see what every button of your controller does in rekordbox.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › rekordbox mappings

## Table of Contents

- [Supported files](#supported-files)
- [What you see](#what-you-see)
- [Building a controller profile from it](#building-a-controller-profile-from-it)
- [Saving](#saving)
- [Technical reference](#technical-reference)
- [Related](#related)

DJ MIDI Studio includes a discoverable `rekordbox` software plugin for
Pioneer/AlphaTheta rekordbox MIDI mappings.

## Supported files

- **`.midi.csv` mappings** — the CSV format rekordbox uses for MIDI
  mappings. rekordbox ships one per supported device: on macOS they are in
  `rekordbox.app/Contents/Resources/MidiMappings/` (right-click the app →
  *Show Package Contents*). All 67 files bundled with rekordbox 7 open.
- A file is recognized by its first line (`@file,1,<device name>`), whatever
  its extension, so `File → Open` picks rekordbox without asking.

## What you see

Each mapping row becomes one control per deck it applies to:

- its channel and Note / CC / Pitch Bend number, decoded from rekordbox's
  hexadecimal addresses (`9058` = Note On, channel 1, note 88) and per-deck
  channel offsets;
- `click` for the input, `output` for LED feedback;
- the rekordbox command (`PlayPause`, `Sync`, `LoopHalf`…), its deck (1-4,
  none for a global control such as Browse), and in the details the
  physical control name (`Sync+Shift` is the SHIFT layer), the control type
  (Button, Pad, Rotary…), rekordbox's options and comment.

Disabled rows (starting with `#`) and rekordbox's internal parameters are
not shown. Validation and **Ready for live** work as for any other mapping.

## Building a controller profile from it

Because these files name every control, Controller Setup can turn one into
a named controller profile: `Learn triggers from a mapping…` → pick the
`.midi.csv`. See [Controller Setup](controller-setup.md#from-a-rekordbox-mapping-names-included).

## Saving

Saving is refused with an explanation: how rekordbox stores a user's own
edits next to its defaults isn't known yet, so the app doesn't write these
files. Change mappings in rekordbox's own MIDI settings.

## Technical reference

The format is documented, with how it was checked against this app's
controller profiles, in
[`software/rekordbox/README.md`](../../../software/rekordbox/README.md).
The plugin is `src/djmidi/software/rekordbox.py`; tests in
`tests/test_rekordbox_mapping.py` use a synthetic file in the same shape
(rekordbox's own files are AlphaTheta's and aren't copied into this
project).

## Related

- [Mapping editor](mapping-editor.md): the views and validation.
- [Traktor mappings](traktor-mappings.md): the same for Traktor `.tsi` files.
- [Music Library](music-library.md): rekordbox USB `export.pdb` playlists.
