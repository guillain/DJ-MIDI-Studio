# 🎚️ Mixxx mappings

> 🎚️ Mixxx controller mappings (`.midi.xml`) open read-only in the same
> channel, deck and control views as Serato, Traktor and rekordbox
> mappings.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Mixxx mappings

## Table of Contents

- [Supported files](#supported-files)
- [What you see](#what-you-see)
- [Saving](#saving)
- [Technical reference](#technical-reference)
- [Related](#related)

DJ MIDI Studio includes a discoverable `mixxx` software plugin for Mixxx
controller mappings.

## Supported files

- **`.midi.xml` mappings** — the ones Mixxx ships for its supported
  controllers and the ones you make or download. Both the current
  (`MixxxControllerPreset`) and the older (`MixxxMIDIPreset`) shape open; a
  file is recognized by its content, so `File → Open` picks Mixxx without
  asking even though the name ends in `.xml`.

## What you see

Each binding becomes one control per MIDI address:

- its channel and Note / CC / Pitch Bend number;
- `click` for an input, `output` for LED feedback;
- the Mixxx key it drives (`play`, `crossfader`…) or, for a scripted
  binding, the script function (`MyController.deck[0].play.input`), with its
  deck (from `[Channel1]`…), and in the details the Mixxx group, the
  description and the options.

What a script function then does lives in the mapping's JavaScript file and
isn't shown. [Controller Setup](controller-setup.md) can also learn the
triggers of a Mixxx file to start a controller profile.

## Saving

Saving is refused with an explanation: a faithful write has to keep the
file's comments and layout, which isn't implemented yet. Edit mappings in
Mixxx's controller preferences.

## Technical reference

The format, the real files it was checked on and a cross-check of this
app's controller profiles against Mixxx's mappings are in
[`software/mixxx/README.md`](../../../software/mixxx/README.md). The plugin
is `src/djmidi/software/mixxx.py`; tests in `tests/test_mixxx_mapping.py`.

## Related

- [Mapping editor](mapping-editor.md): the views and validation.
- [rekordbox mappings](rekordbox-mappings.md) and [Traktor mappings](traktor-mappings.md).
