# 🎛️ Supported controllers

> Which controllers DJ MIDI Studio knows out of the box, where each profile
> comes from, how far it has been verified, and how to add your own.

📍 [Docs](../README.md) › [End user](README.md) › Supported controllers

## Table of Contents

- [Built-in controllers](#built-in-controllers)
- [What a profile covers](#what-a-profile-covers)
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
