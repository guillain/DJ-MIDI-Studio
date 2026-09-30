# Native Instruments Traktor mapping format

## Status: implemented and verified against real exports (issue #122)

`src/djmidi/software/_tsi.py` decodes `.tsi` controller mappings on top of
the generic chunk codec `src/djmidi/binary_chunks.py`, and
`src/djmidi/software/traktor.py` exposes them through the software-plugin
registry. Everything below was checked against the real exports in
`data/traktor/` (see "Verified against real files"); the original plugin's
flat-XML `<NML><MAPPING>` assumption (see next section) survives only as a
legacy fallback for files this app produced before.

## `.nml` is the wrong file entirely

`.nml` is Traktor's **track collection** format (playlists, tracks, hot
cues, BPM, musical key, other track metadata) — it has nothing to do with
controller mappings. Confirmed independently by Native Instruments' own
manual ("Managing Your Track Collection") and by community tooling that
parses it for library purposes only (e.g. `traktor-nml-utils` on PyPI).
Accepting `.nml`/generic `<root>NML</root>` XML as a controller-mapping
input, as the original plugin did, was never going to match a real
controller-mapping export.

## `.tsi` is the real controller-mapping format — and it's XML wrapping binary

Confirmed via a reverse-engineered but well-documented community spec:
[ivanz/TraktorMappingFileFormat](https://github.com/ivanz/TraktorMappingFileFormat)
(GitHub wiki + a literal [010 Editor binary
template](https://github.com/ivanz/TraktorMappingFileFormat/blob/master/Tools/TSI%20Mapping%20Template.bt)
giving exact field-level layouts). No official Native Instruments spec
exists for this format — treat everything below as reverse-engineered,
same evidentiary status this project already gives a "conservative
community profile" controller catalog, not as vendor-guaranteed.

### Container

A `.tsi` file is XML with a single relevant entry:

```xml
<Entry Name="DeviceIO.Config.Controller" Type="3" Value="<BASE64_BLOB>"/>
```

`Value` is a **Base64-encoded binary blob** — the actual mapping data.

### Binary structure: nested, ID3v2-like chunks

The decoded blob is a stream of **chunks**, each: a 4-character ASCII ID, a
32-bit **big-endian** size, then that many bytes of payload (which may
itself contain nested chunks). Strings are length-prefixed UTF-16
(`wchar_t`), also big-endian per the template.

Chunk types actually needed for controller mappings, field-by-field (from
the `.bt` template, big-endian throughout):

- **`DEVI`** (Device): `int NameLength` + `wchar_t Name[NameLength]` + `DDAT`
- **`DDAT`** (DeviceData): `DDIF` + `DDIV` + `DDIC` + `DDPT` + `DDDC` + `DDCB` + `DVST`
  - **`DDIF`** (DeviceTargetInfo): `int Target` (enum `DeviceTarget`: `Focus=0, DeckA=1, DeckB=2, DeckC=3, DeckD=4`)
  - **`DDIV`** (VersionInfo): `int VersionLength` + `wchar_t Version[]` + `int MappingFileRevision`
  - **`DDIC`** (MappingFileComment): `int CommentLength` + `wchar_t Comment[]`
  - **`DDPT`** (DevicePorts): `int InPortNameLength` + `wchar_t InPortName[]` + `int OutPortNameLength` + `wchar_t OutPortName[]`
  - **`DDDC`** (MidiDefinitionsContainer): `DDCI` (in) + `DDCO` (out)
    - **`DDCI`/`DDCO`** (MidiIn/OutDefinitions): `int NumberOfEntries` + that many `DCDT`
      - **`DCDT`** (MidiDefinition): `int MidiNoteLength` + `wchar_t MidiNote[]` (a human-readable label like `"Ch01.CC.001"`, not a raw number) + `DWORD Unknown1` + `DWORD Unknown2` + `float Velocity` + `int EncoderMode` (enum `MidiEncoderMode`: `_3Fh_41h=0, _7Fh_01h=1`) + `int ControlId`
  - **`DDCB`** (MappingsContainer): `CMAS` (mappings list) + `DCBM` list (note bindings)
    - **`CMAS`** (MappingsList): `int NumberOfMappings` + that many `CMAI`
      - **`CMAI`** (Mapping): `int MidiNoteBindingId` + `int MappingType` (enum: `In=0, Out=1`) + `int TraktorControlId` + `CMAD`
        - **`CMAD`** (MappingSettings): `DWORD Unknown1` + `int ControllerType` (enum `MappingControllerType`: `Button=0, FaderOrKnob=1, Encoder=2, LED=65535`) + `int InteractionMode` (enum `MappingInteractionMode`: `Toggle=1, Hold=2, Direct=3, Relative=4, Increment=5, Decrement=6, Reset=7, Output=8`) + `int TargetDeck` (enum `MappingTargetDeck`: `DeviceTargetDeck=-1`, `0-3` = deck A/FX1/RemixDeck1 slots, `4-15` = RemixDeck2-4 slots) + `int AutoRepeat` + `int Invert` + `int SoftTakeover` + `float RotarySensitivity` + `float RotaryAcceleration` + 2×`DWORD Unknown` + `float SetValueTo` + `int CommentLength` + `wchar_t Comment[]` + `int ModifierOneId` + `DWORD Unknown` + `int ModifierOneValue` + `int ModifierTwoId` + `DWORD Unknown` + `int ModifierTwoValue` + `DWORD Unknown` + `float LedMinControllerRange` + `DWORD Unknown` + `float LedMaxControllerRange` + `int LedMinMidiRange` + `int LedMaxMidiRange` + `int LedInvert` + `int LedBlend` + `DWORD Unknown` + `int Resolution` (enum `MappingResolution`, `DWORD`: `Fine=0x3C800000, Min/Default=0x3D800000, Coarse=0x3E000000, Switch=0x3F000000`) + `DWORD Unknown`
    - **`DCBM`** (MidiNoteBinding): `int Id` + `int MidiNoteLength` + `wchar_t MidiNote[]` — this is what actually ties a `CMAI.MidiNoteBindingId` back to a real MIDI channel/note-or-CC number, via the human-readable label string (needs parsing, e.g. `"Ch01.CC.001"` → channel 1, CC 1); no separate raw integer channel/note fields exist at this level.
  - **`DVST`**: opaque `byte Content[Size]` (unknown purpose per the template)

A top-level `DevicesList` (`int NumberOfDevices` + that many `DEVI`) sits
under a `DeviceMappingsContainer` wrapper — a `.tsi` can describe more than
one device/mapping at once.

### Traktor command IDs (`TraktorControlId`)

Every Traktor-side command (Play/Pause, Cue, Sync, …) has a fixed integer
ID, e.g. `100 → Play/Pause(DeckCommon)`, `206 → Cue`, `125 → SyncOn`. A
partial table (hundreds of entries) is published at
[ivanz/TraktorMappingFileFormat's wiki, "Traktor Commands List"](https://github.com/ivanz/TraktorMappingFileFormat/wiki/Traktor-Commands-List).
Only transcribe an ID → name pair here (or into the plugin) once actually
needed and cross-checked — don't bulk-copy the whole list speculatively.

## Real samples

The maintainer supplied real `.tsi` exports from their own Traktor setup
(2026-09-19), unblocking the item below — each zipped individually (one
`.zip` per file, so the archive listing itself stays browsable) in
`data/traktor/`:

- `xdj-xz-settings.tsi.zip` — a full Traktor settings export including the XDJ-XZ controller mapping
- `cmd-studio-4a.tsi.zip` — Behringer CMD Studio 4a mapping
- `nanopad2-remixer.tsi.zip` — Korg nanoPAD2 remix-deck mapping
- `keyboard-mapping.tsi.zip` — a computer-keyboard (not MIDI hardware) mapping

These also surfaced three real controller candidates with no catalog module
yet — CMD Studio 4a, nanoPAD2, and (from a real Serato export,
`data/serato/cmd-lc1.xml.zip`) the Behringer CMD-LC1 — tracked in
`TODO.md`'s "New candidates" list.

## Verified against real files

Checked on all four real exports (2026-09-30):

| File | Devices | Mappings | Notes |
|---|---|---|---|
| `xdj-xz-settings.tsi` | 5 | 8,963 | 8 compound labels |
| `cmd-studio-4a.tsi` | 4 | 381 | 1 command never MIDI-learned |
| `nanopad2-remixer.tsi` | 1 | 16 | |
| `keyboard-mapping.tsi` | 0 | 0 | no `DeviceIO.Config.Controller` entry |

- **Chunk tree** matches the layout above exactly, with two container
  headers the layout lists only implicitly: `DEVS` and `CMAS` start with an
  `int` count, and the `DCBM` *under* `DDCB` is a list (an `int` count of
  nested `DCBM` bindings), while each nested `DCBM` is a leaf. Re-encoding an
  unmodified tree and its Base64 is byte-identical on every file.
- **Binding labels** read `ChNN.Note.<note><octave>`, `ChNN.CC.NNN` or
  `ChNN.PitchBend`. Octave numbering starts at `C-1` = MIDI note 0, confirmed
  against the official Pioneer XDJ-XZ values in `catalog/xdj_xz.py`:
  Traktor's own XDJ-XZ mapping puts Play (command 100) on `C-1` (note 0),
  Cue (206) on `C#-1` (note 1) and Sync On (125) on `G1` (note 31) — exactly
  the Pioneer MIDI list's PLAY/PAUSE 0, CUE 1 and SYNC 31. That also
  confirms those three command IDs.
- **Compound labels** exist: `Ch01.CC.032+Ch01.CC.000` binds two messages
  at once (a 14-bit CC's MSB + LSB). Only their first part is shown as the
  trigger, and they are never rewritten.
- **Unassigned mappings** exist: a `CMAI` whose binding id has no `DCBM`
  entry is a command added in Traktor but never MIDI-learned.
- **`CMAD` field order** up to the comment is confirmed by real comments
  decoding cleanly ("HOTCUE", "Scratch A Light", ...); binding ids are unique
  per device.

## What's deliberately not done

- Writing is limited to re-labelling existing bindings. Creating a `.tsi`
  from scratch, or adding/removing bindings, would mean synthesizing
  `CMAD` payloads whose unknown fields aren't understood — refused instead.
- Only command IDs 100/125/206 are named (the three cross-checked above);
  every other command shows as `Command <id>` rather than a name copied
  from the community list without verification.
- `DDCI`/`DDCO` (the device's full MIDI in/out definitions) and `DVST` are
  decoded as opaque data and carried over verbatim.

## Sources

- [ivanz/TraktorMappingFileFormat](https://github.com/ivanz/TraktorMappingFileFormat) — reverse-engineered `.tsi` format spec (wiki + `.bt` binary template)
- [Native Instruments — Managing Your Track Collection](https://docs.native-instruments.com/ni-tech-manuals/traktor-pro-manual/en/managing-your-track-collection) — confirms `.nml` is the collection format, not mappings
