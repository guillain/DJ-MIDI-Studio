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
- [Pioneer DDJ-FLX4](#pioneer-ddj-flx4)
- [Hercules DJControl Inpulse 500](#hercules-djcontrol-inpulse-500)
- [Pad modes](#pad-modes)
- [Profile library (rekordbox devices)](#profile-library-rekordbox-devices)
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
| Pioneer DDJ-REV5 | Official MIDI Message List E1 | ✅ | ✅ | Not yet |
| Pioneer DDJ-800 | Official MIDI Message List E3 | ✅ | ✅ | Not yet |
| Pioneer DDJ-FLX4 | Official MIDI Message List E1 | ✅ | ✅ | Not yet |
| Numark Mixtrack Pro FX | Conservative community values; user guide for the layout | ✅ | — | Not yet |
| Hercules DJControl Inpulse 500 | Official MIDI Commands sheet (2022) | ✅ | ✅ | Not yet |
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

## Pioneer DDJ-FLX4

Transcribed from the official Pioneer MIDI Message List bundled with the
app (`Help → Controller References`); not yet checked on a real unit. Deck
buttons send on MIDI channel 1 (deck 1) and 2 (deck 2), e.g. `PLAY/PAUSE`
is note 11 and `CUE` note 12. The pads send on channel 8 (deck 1) and 10
(deck 2), one channel higher with SHIFT; each of the 8 pad modes has its own
16 notes, so a pad is named with its mode, e.g.
`Deck 1 Pad 3 (BEAT JUMP)`. The four pad-mode buttons, `BROWSE` push, both
`LOAD` buttons, the Beat FX buttons, both `CUE` buttons of the mixer,
`MASTER CUE`, `SMART CFX` and `SMART FADER` are named too. The FX CH SELECT
switch and the rear MONO/STEREO switch are left out.

Profiles before v0.48.140 used community values (`PLAY/PAUSE` on note 0,
pads on channels 6 and 7, and KEYLOCK/SLIP/REVERSE/QUANTIZE buttons the
FLX4 doesn't have) that don't match the official list.

## Hercules DJControl Inpulse 500

Transcribed from the official Hercules "MIDI Commands" sheet bundled with
the app (`Help → Controller References`); not yet checked on a real unit.
Deck 1 buttons send on MIDI channel 2 and deck 2 on channel 3, with the
SHIFT layer on channels 5 and 6 (e.g. `PLAY/PAUSE` is note 7 on both
decks). The pads send on channel 7 (deck 1) and 8 (deck 2): each of the 8
pad modes has its own 16 notes, the first 8 for the plain pads and the next
8 for SHIFT, so a pad is named with its mode, e.g.
`Deck 1 Pad 3 (PAD MODE 6)`. The four mode buttons select modes 1–4, and
modes 5–8 with SHIFT; a long press sends a separate note. The mixer's PFL,
FX 1–4, crossfader-curve switch, the browse push and the two LOAD buttons
are named too.

Left out because the sheet contradicts itself on them: `Guides` and
`Assistant` (both printed as the same note), deck 2's long press on mode
button 4 and `LOAD 2` with SHIFT (channel and status byte disagree).
Profiles before v0.48.89 used community values for this controller (pads
on notes 40–47) that don't match the sheet.

## Pad modes

The Pioneer pad-grid profiles (DDJ-XP2, XDJ-XZ, DDJ-1000, DDJ-FLX4,
DDJ-FLX10, DDJ-REV1) resolve pad modes 1 to 8. On the DDJ-XP2, modes 5–8 are
reached by double-clicking `PAD MODE 1–4`; the hardware then sends a
distinct note for the second click. The Hercules DJControl Inpulse 500
resolves its 8 pad modes too, and in the
[Controller Emulator](features/controller-emulator.md) clicking one of its
`PAD MODE` buttons steers later pad clicks to that mode's notes. The same
works for the DDJ-FLX4, DDJ-800 and DDJ-REV5 mode buttons; with SHIFT
latched, a DDJ-FLX4 mode button selects KEYBOARD / PAD FX 2 / BEAT LOOP /
KEY SHIFT and a DDJ-REV5 one PITCH PLAY / PIANO PLAY / STEMS / SCRATCH
BANK (the DDJ-800's list doesn't say which mode SHIFT selects, so SHIFT
keeps the plain mode there). The DDJ-REV5 profile also has the `HOT CUE`
and `SCRATCH BANK` buttons under KEY −/+ and the LOAD buttons (`LOAD DECK
1–4`, one note per target deck). The Numark
profile covers its main eight-pad bank only: its mode-switch messages aren't
documented, so they aren't guessed.

## Profile library (rekordbox devices)

Beyond the built-in controllers, the app ships a **library** of ready-made
profiles for 46 more Pioneer DJ / AlphaTheta devices: DDJ-200, DDJ-400, DDJ-ERGO, DDJ-FLX2, DDJ-FLX6, DDJ-GRV6, DDJ-RB, DDJ-REV7, DDJ-RR, DDJ-RX, DDJ-RZ, DDJ-RZX, DDJ-SB, DDJ-SB2, DDJ-SP1, DDJ-SR, DDJ-SX, DDJ-SX2, DDJ-SZ, DDJ-WeGO, DDJ-WeGO2, DDJ-WeGO3, DDJ-WeGO4, DDJ-XP1, DJM-250MK2, DJM-450, DJM-750MK2, DJM-900NXS2, DJM-A9, DJM-S11, DJM-S7, DJM-S9, DJM-T1, DJM-TOUR1, DJM-V10, EUPHONIA, OMNIS-DUO, OPUS-QUAD, PLX-CRSS12, XDJ-AERO, XDJ-AZ, XDJ-R1, XDJ-RR, XDJ-RX, XDJ-RX2, XDJ-RX3.

They are built from the MIDI mappings rekordbox ships for each device, so
they cover each device's **buttons and pads**, named and grouped as
rekordbox names them (`Sync +SHIFT`, `Pad 3 (HotCue)`); knobs, faders and
jogs aren't included, and they have no picture (the layout views show them
as a grid of controls). Their source is rekordbox's default mapping, not the
vendor's MIDI documentation, and none has been checked on a real unit.

They aren't active until you install them, so they don't crowd every
controller list: **`File` → `Controller Profile` → `Install from Library…`**,
filter (a device's MIDI port names match too), select one or more, then
**`Install`** (or double-click). An installed profile shows up in every
view at once and loads at every launch, like a profile made in
[Controller Setup](features/controller-setup.md); **`Uninstall`** in the
same window removes it again.

When you launch the app with such a controller plugged in (its MIDI port
names it), the app asks once whether to install its profile. Answer No and
it won't ask again for that device; the library window still has it.

## Add your own controller

Any controller can be added without its manufacturer's MIDI documentation:
[Controller Setup](features/controller-setup.md) learns it from the
hardware, or from a Serato mapping you already use. `Install` keeps it for
every launch, as a JSON profile in `Documents/DJ MIDI Studio/Controllers`,
and it can be shared with the community catalog.

## JSON profiles

A controller with only static Note/CC controls is described by a JSON file
— exactly what Controller Setup's `Install` writes. Any such file placed in
`Documents/DJ MIDI Studio/Controllers` is loaded at launch:

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
