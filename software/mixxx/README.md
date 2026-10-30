# Mixxx mapping format

## Status: read-only plugin

`src/djmidi/software/mixxx.py` (`v0.48.151`, issue #365) reads Mixxx
controller mappings. Mixxx is the one major DJ program whose mapping format
is publicly documented, and its repository ships the mappings themselves;
the plugin was checked against all of them, read in place. Nothing from
them is copied into this repo (they are GPL-licensed); tests use a
synthetic file in the same shape.

## Real files

The `2.5` branch of [mixxxdj/mixxx](https://github.com/mixxxdj/mixxx) has
142 `res/controllers/*.midi.xml` files (16,933 `<control>` and 2,290
`<output>` elements), checked on 2026-10-30:

- **Root**: `<MixxxControllerPreset>` (60 files) or the older
  `<MixxxMIDIPreset>` (82), with `<info>` (`name`, `author`, …) and one
  `<controller>` holding `<scriptfiles>`, `<controls>` and `<outputs>`.
- **`<control>`** (an input binding): `<group>` (`[Channel1]` = deck 1,
  `[Master]`, `[Sampler2]`, `[EffectRack1_EffectUnit1]`…), `<key>` (a Mixxx
  control such as `play`, or a script function such as
  `MyController.deck[0].play.input` with `<options><script-binding/>`),
  `<status>` (always hex, `0x90` = Note On, channel 1), `<midino>` (hex
  data1; absent on a few pitch-bend bindings), optional `<description>`
  (on 6,219 controls) and `<options>` (`normal`, `script-binding`,
  `button`, `soft-takeover`, `fourteen-bit-msb/lsb`, `invert`…).
- **`<output>`** (LED feedback): the same addressing plus `<on>`, `<off>`,
  `<minimum>`, `<maximum>`.
- **Status types**: Note On 10,313, Control Change 4,182, Note Off 2,307,
  Pitch Bend 87, Program Change 32, System 8 (+4 malformed `0x0…`).

The plugin turns each address into a `Control` (input → `click`, output →
`output`), the key into `MappingElement.tag`, a `[ChannelN]` group into
`deck_id`, and keeps group/description/options/on/off in `extra_attrs`.
Program Change, System messages and bindings without a number are skipped.
All 142 files parse (17,095 controls) with no validation issue and are
detected by their root tag, even with a plain `.xml` suffix.

Much of a Mixxx mapping's behaviour lives in its JavaScript file; the
plugin shows which messages a mapping binds and to which key or script
function, not what the script then does.

## Cross-check against this project's profiles

Triggers of each built-in profile also bound in Mixxx's mapping for the same
device:

| Profile | Source | In Mixxx's mapping |
|---|---|---|
| Behringer CMD Micro | hardware capture | 100 % |
| Behringer CMD Studio 4a | hardware capture | 96 % |
| Hercules DJControl Inpulse 500 | official sheet | 79 % |
| DDJ-FLX4 | official PDF | 46 % (Mixxx maps fewer pad modes) |
| Numark Mixtrack Pro FX | community values | 41 % — real disagreement, issue #372 |

## What's still needed before writing

Writing must keep the file's comments and layout byte for byte except the
edited bindings (like the Traktor `.tsi` writer), which means patching the
XML text rather than re-serializing it. Not implemented.

## Sources

- [Mixxx manual — MIDI mapping file format](https://github.com/mixxxdj/mixxx/wiki/Midi-Controller-Mapping-File-Format)
- [mixxxdj/mixxx `res/controllers`](https://github.com/mixxxdj/mixxx/tree/2.5/res/controllers) (real mappings, read in place)
