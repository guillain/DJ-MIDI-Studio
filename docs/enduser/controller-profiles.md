# 🎛️ Supported controllers

> Which controllers DJ MIDI Studio knows out of the box, where each profile
> comes from, how far it has been verified, and how to add your own.

📍 [Docs](../README.md) › [End user](README.md) › Supported controllers

## Table of Contents

- [Built-in controllers](#built-in-controllers)
- [What a profile covers](#what-a-profile-covers)
- [Behringer CMD LC-1](#behringer-cmd-lc-1)
- [Behringer CMD Micro](#behringer-cmd-micro)
- [Behringer CMD Studio 4a](#behringer-cmd-studio-4a)
- [Korg nanoPAD2](#korg-nanopad2)
- [Pad modes](#pad-modes)
- [Add your own controller](#add-your-own-controller)
- [JSON profiles](#json-profiles)
- [Related](#related)

## Built-in controllers

| Controller | Source of the profile | Real layout in emulator / images | Live jog | Verified on hardware |
| --- | --- | --- | --- | --- |
| Pioneer DDJ-XP2 | Official MIDI Message List E1 | ✅ | — | ✅ |
| Pioneer XDJ-XZ | Official MIDI Message List E3 | ✅ | ✅ | ✅ |
| Pioneer DDJ-1000 | Official MIDI Message List E1 | ✅ | ✅ | Not yet |
| Pioneer DDJ-FLX10 | Official MIDI Message List E1 | ✅ | ✅ | Not yet |
| Pioneer DDJ-REV1 | Official MIDI Message List E1 | ✅ | ✅ | Not yet |
| Pioneer DDJ-REV5 | Official MIDI Message List E1 | Grid | — | Not yet |
| Pioneer DDJ-800 | Official MIDI Message List E3 | Grid | — | Not yet |
| Pioneer DDJ-FLX4 | Conservative DDJ-400-family values; official list archived, not yet cross-checked | Grid | — | Not yet |
| Numark Mixtrack Pro FX | Conservative community values; user guide for the layout | ✅ | — | Not yet |
| Hercules DJControl Inpulse 500 | Conservative values; product sheet | Grid | — | Not yet |
| Behringer CMD LC-1 | Captured from a real unit with Controller Setup (no vendor list exists), checked against a real Serato export | ✅ | — | ✅ |
| Behringer CMD Micro | Captured from a real unit (no vendor list exists), checked against a real Traktor export | ✅ | — | ✅ |
| Behringer CMD Studio 4a | Captured from a real unit in all 4 deck layers (no vendor list exists), checked against a real Traktor export | ✅ | — | ✅ |
| Korg nanoPAD2 | Captured from a real unit in all 4 scenes (Korg publishes no note table) | ✅ | — | ✅ |

"Not yet" means the profile was transcribed from documentation but hasn't
been checked against a real device. Check the controls you rely on with the
[Live Monitor](features/live-monitor.md) before playing live, and report any
difference.

The manuals and MIDI message lists are bundled with the app
(`Help → Controller References`); the full source list is in the
[controller documentation index](../../controllers/README.md).

## What a profile covers

Profiles name the **discrete** controls — buttons, pads, mode and transport
keys — because those are what DJ mappings remap. Continuous controls (faders,
EQ and trim knobs, jog wheels, touch strips) aren't named, though the layouts
still draw them and the Live Monitor shows their raw values.

## Behringer CMD LC-1

The first profile built from a hardware capture rather than a manual, since
Behringer publishes no MIDI message list. With factory settings it uses MIDI
channel 8. Under the eight encoders, the face is 13 rows of 4 buttons, notes
left to right: the buttons printed 1–8 (notes 16–23), an unlabelled 4×8 grid
(32–63), then MUTE (64–67), SOLO (68–71) and RECORD (72–75); notes 24–31 are
unused. The encoders are endless rotaries without a push switch (CC from 16)
and, like every continuous control, aren't named. macOS calls its port
`CMD LC-1` with no manufacturer prefix; the profile declares that name so the
Dashboard still detects it. A Note On sent back on a button's own note lights
its LED, which is what Live Monitor and the Controller Emulator expect.

## Behringer CMD Micro

Behringer publishes no MIDI message list for the CMD Micro; the profile was
captured from a real unit and matches a real Traktor export. Every button
sends on MIDI channel 1: per deck `1`, `2`, `SYNC`, `▶II`, `CUE`, `PITCHBEND
−/+`, `LOAD A/B` and `CUE A/B`, plus the `LEFT`/`RIGHT` browse buttons. The
two decks don't use mirrored notes (on deck B, `1` is 34 and `2` is 36), so
check by name rather than by pattern. Jog wheels, faders, the crossfader and
the knobs (including BROWSE, which has no push) are continuous and aren't
named. macOS calls its port `CMD Micro`.

## Behringer CMD Studio 4a

Behringer publishes no MIDI message list for the CMD Studio 4a either; the
profile was captured from a real unit in all four deck layers and covers
every note of a real Traktor export. Each side switches between two decks,
and the deck only changes the MIDI channel, never the note: the left side
sends on channel 1 for deck A and 3 for deck C, the right side on 2 for deck
B and 4 for deck D. Names carry the side's decks, e.g. `HOT CUE 1 (A/C)`.
The deck-select buttons send on their own deck's channel only, and the
BROWSE `<`, `>` and `ENTER` buttons always send on channel 1. On the right
side the LOOP arrows are reversed compared with the left (55 is `>`, 56 is
`<`). Knobs, faders, the crossfader and the jog wheels are continuous and
aren't named; none of the knobs has a push switch. macOS calls its port
`Studio 4A`.

## Korg nanoPAD2

Korg documents the nanoPAD2's message format but not its notes: every pad is
assignable per scene in Korg's editor. The profile was captured from a real
unit in all four scenes. They all send on MIDI channel 1 with different notes,
so one profile covers every scene. The scenes work like pad modes: the 16
pads are `Pad 1–8` (top row) and `Pad 9–16` (bottom row), each named with its
scene, e.g. `Pad 5 (SCENE 2)`. If you reprogrammed your nanoPAD2 in Korg's
editor, your notes will differ: check them in the
[Live Monitor](features/live-monitor.md), or build your own profile with
[Controller Setup](features/controller-setup.md). The X-Y pad is continuous
and isn't named; HOLD, GATE ARP, TOUCH SCALE, KEY/RANGE, SCALE/TAP and SCENE
only change the controller's own state and send nothing to map. In
Controller Images, the `MIDI` layer shows a Korg editor layout
(notes 36–51) that differs from the captured unit: use it for pad positions,
not note numbers.

## Pad modes

The Pioneer pad-grid profiles (DDJ-XP2, XDJ-XZ, DDJ-1000, DDJ-FLX4,
DDJ-FLX10, DDJ-REV1) resolve pad modes 1 to 8. On the DDJ-XP2, modes 5–8 are
reached by double-clicking `PAD MODE 1–4`; the hardware then sends a
distinct note for the second click. The Numark and Hercules profiles cover
their main eight-pad bank only: their mode-switch messages aren't documented,
so they aren't guessed.

## Add your own controller

Any controller can be added without its manufacturer's MIDI documentation:
[Controller Setup](features/controller-setup.md) learns it from the
hardware, or from a Serato mapping you already use, and can share it with
the community catalog.

## JSON profiles

A controller with only static Note/CC controls can also be described in a
JSON file and installed as a plugin:

```json
{
  "manifest": {
    "schema_version": 1,
    "plugin_id": "example.controller",
    "kind": "controller",
    "name": "Example Controller",
    "version": "1.0.0",
    "api_version": "1",
    "vendor": "Example",
    "license": "MIT"
  },
  "controller": {
    "name": "Example Controller",
    "supported_software": ["serato"],
    "entries": [
      {"section": "DECK", "name": "PLAY", "note_or_cc": "NOTE", "channels": ["1", "2"], "data1": "60"}
    ]
  }
}
```

Pad formulas and device detection need a Python plugin instead. The
manifest fields are described in the
[plugin manifest reference](../developer/design/plugin-manifest.md).

## Related

- [Controller Setup](features/controller-setup.md)
- [Controller Images](features/controller-images.md)
- [Plugins](plugins.md)
