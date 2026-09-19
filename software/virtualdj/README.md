# VirtualDJ mapping format

## Status: candidate, not yet integrated

No `src/djmidi/software/virtualdj.py` plugin exists yet. This file records
what's known about the real format so a future integration starts from
evidence, not a guess.

## What the format is

Officially documented on VirtualDJ's own wiki ("VDJPedia") — the best-
documented of the four formats surveyed so far (Serato has no public spec
at all; Traktor's is reverse-engineered only). A VirtualDJ controller is
described by **two separate XML files**:

1. **A "definition" file** (`Documents/VirtualDJ/Devices/`) — gives a
   human-readable name to every physical MIDI code. Root element
   `<device name="..." type="MIDI" description="..." version="..."
   vid="..." pid="..." decks="N">`. Per-control elements:
   - `<button note="0x34" name="PLAY_PAUSE" deck="1" channel="1" />` —
     discrete NOTE-triggered controls; `cc="0x68" value="0x7F" off="0x00"`
     is the CC-triggered discrete-button variant.
   - `<slider ccmsb="0x08" cclsb="0x28" name="LEVEL" deck="1" channel="0"/>`
     — continuous controls (14-bit MSB/LSB CC pairs supported); `<jog>`,
     `<fulljog>`, `<encoder>`, `<fullencoder>` cover jog wheels/encoders.
   - **MIDI channels are zero-based** (`channel="0"` = MIDI channel 1) —
     same convention as Rekordbox's CSV format, opposite of this project's
     own 1-indexed internal model (`model.Control`), so a plugin needs the
     same `+1`/`-1` normalization already done for Traktor.
2. **A "mapping" file** (`Documents/VirtualDJ/Mappers/`) — a `<mapper>`
   root (optional `author`/`date`/minimum-`version`/`priority` attributes)
   containing `<map value="..." action="...VDJScript..."/>` children, where
   `value` is one of the definition file's `name`s and `action` is a
   **VDJScript** command string (VirtualDJ's own scripting language, not a
   simple function-name enum like Serato/Traktor/Rekordbox).

This project's normalized model (`Control`/`MappingElement`) maps
comfortably onto the *definition* file's discrete controls (name + raw
channel/note-or-CC), but the *mapping* file's `action` being a full
scripting-language string rather than a flat command name is a genuine
representational gap — closer to Traktor's `TraktorControlId`-plus-modifiers
richness than to Serato's flat `<mapping-tag>` scheme.

## What's needed before building a plugin

- A **real definition + mapping file pair** for at least one controller
  (VirtualDJ ships official ones per-controller, similar to rekordbox's
  bundled CSVs — check the app's own resources folder, or export one from
  a real setup) to validate against.
- A decision on how much of VDJScript's `action` strings this project's
  catalog scope should attempt to parse/represent vs. treat as an opaque
  passthrough string (mirroring how Traktor's richer `CMAD` settings —
  interaction mode, modifiers — go beyond what a flat `MappingElement.tag`
  can hold today).

## Sources

- [VirtualDJ — VDJPedia: Controller Developers](https://virtualdj.com/wiki/controller%20developers.html) (official)
- [VirtualDJ — VDJPedia: ControllerDefinitionMIDI](https://www.virtualdj.com/wiki/ControllerDefinitionMIDI.html) (official)
- [VirtualDJ — VDJPedia: How do I map my MIDI controller](https://www.virtualdj.com/wiki/How%20do%20I%20map%20my%20MIDI%20controller.html) (official)
