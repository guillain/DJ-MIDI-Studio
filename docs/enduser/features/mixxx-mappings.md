# 🎚️ Mixxx mappings

> 🎚️ Mixxx controller mappings (`.midi.xml`) open in the same channel,
> deck and control views as the other software, and a re-assigned MIDI
> trigger saves back into the original file without touching anything else.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Mixxx mappings

## Table of Contents

- [Supported files](#supported-files)
- [What you see](#what-you-see)
- [Saving](#saving)
- [Create a Mixxx mapping from a profile](#create-a-mixxx-mapping-from-a-profile)
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

Change a binding's channel, type or number and save: only the `<status>`
and `<midino>` of the bindings that moved are rewritten, in place. Every
other byte — comments, indentation, script references, options, LED
values — stays exactly as it was, and a file you open and save without
changes comes out identical. The save confirmation shows the changed lines.

Refused with an explanation rather than approximated: adding or removing a
binding, changing its Mixxx key or deck (do that in Mixxx), giving a number
to a binding that has none (pitch bend), and a value the file spells as an
XML entity (`&CC;`). Keep a copy of the original and check the result in
Mixxx before using it live.

## Create a Mixxx mapping from a profile

For a controller Mixxx doesn't support yet, or one you've captured
yourself in Controller Setup, `File → Export → Mixxx Mapping from
Profile...` writes a Mixxx mapping you can load in Mixxx:

1. Pick the controller. Every button and pad of its profile is listed, one
   row per MIDI channel (SHIFT layers left out).
2. Double-click **Mixxx function** to choose what a row does, and **Deck**
   to change the deck. Rows start with a guess from the control's name
   (`PLAY/PAUSE` → Play / pause, a hot cue pad → its hot cue); check them.
   Use the filter and **Only rows with a function** to review them quickly.
3. **Save Mixxx mapping…**, then copy the `.midi.xml` file into Mixxx's
   controllers folder and pick it in Mixxx's Preferences → Controllers.

Only rows with a function are written, and only Mixxx functions that
Mixxx's own mappings use for a button are offered (about 40: transport,
sync, key lock, loops, hot cues, load, PFL…). Knobs, faders and jog wheels
aren't in profiles, so map those in Mixxx's own MIDI learning wizard.
Tick **Also bind Note Off** if your controller releases its buttons with a
Note Off rather than a Note On at zero (Pioneer controllers use the
latter): without it, a held function such as Cue would never let go.

## Technical reference

The format, the real files it was checked on and a cross-check of this
app's controller profiles against Mixxx's mappings are in
[`software/mixxx/README.md`](../../../software/mixxx/README.md). The plugin
is `src/djmidi/software/mixxx.py`; tests in `tests/test_mixxx_mapping.py`.

## Related

- [Mapping editor](mapping-editor.md): the views and validation.
- [rekordbox mappings](rekordbox-mappings.md) and [Traktor mappings](traktor-mappings.md).
