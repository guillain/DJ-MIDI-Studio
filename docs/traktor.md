# Traktor integration

> 🎧 Traktor controller mappings (`.tsi`) open in the same channel/control
> views as Serato mappings, and a re-assigned MIDI trigger saves back into
> the original file without touching anything else.

DJ MIDI Studio includes a discoverable `traktor` software plugin for Native
Instruments Traktor controller mappings.

## Supported files

- **`.tsi` controller mappings** — the real format Traktor imports and
  exports (`Controller Manager → Import/Export`), including a full settings
  export that contains several devices. Verified against real exports of an
  XDJ-XZ (5 devices, 8,963 mappings), a Behringer CMD Studio 4a, and a Korg
  nanoPAD2.
- A `.tsi` without controller mappings (e.g. a keyboard-only export) opens as
  an empty mapping.
- *Legacy:* flat `<NML><MAPPINGS><MAPPING>` XML files produced by earlier
  versions of this app. This is **not** a format Traktor reads; `.nml` is
  Traktor's track collection, handled by the `Music Library` tab instead.

## What you see

Each Traktor mapping that has a MIDI assignment becomes one control:

- its channel and Note / CC / Pitch Bend number (Traktor's `Ch01.Note.C#2`
  notation is converted, with `C-1` = note 0);
- `click` for an input command, `output` for LED feedback;
- the Traktor command (Play/Pause, Cue and Sync On by name — other commands
  as `Command <id>`), its target deck, interaction mode (Toggle, Hold,
  Direct…), controller type (Button, Fader/Knob, Encoder, LED), the device
  it belongs to, and Traktor's own comment.

A command that was added in Traktor but never MIDI-learned has no trigger,
so it doesn't appear in the views; it stays in the file untouched.

## Saving

Change a control's channel, type, or number and save: only that binding's
MIDI trigger is rewritten. Every other byte — command settings, LED ranges,
modifiers, the rest of Traktor's settings — is kept as is. The save
confirmation lists each re-assigned binding (for example
`Cue (device #1, in): Ch01.Note.C#-1 -> Ch01.Note.D-1`) instead of the
unreadable encoded data, and the usual validation, backup, atomic write,
and rollback safeguards apply.

The following are refused with an explanation rather than approximated:
adding or removing a binding (do that in Traktor's Controller Manager),
re-assigning a two-message binding (e.g. a 14-bit `CC.032+CC.000` pair),
and changes to command settings (only the MIDI trigger is written back).

Keep a copy of the original file and check the result in Traktor before
using it live.

## Technical reference

The format is documented, with sources, in `software/traktor/README.md`.
The implementation lives in `src/djmidi/software/_tsi.py` (the `.tsi`
codec) on top of the generic chunk codec `src/djmidi/binary_chunks.py`, and
`src/djmidi/software/traktor.py` (the plugin). Tests in
`tests/test_traktor_tsi.py` run against the real exports in
`data/traktor/*.tsi.zip`.
