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

These also surfaced real controller candidates with no catalog module
yet — CMD Studio 4a and nanoPAD2 — tracked in `TODO.md`'s "New candidates"
list. (The Behringer CMD-LC1, from the real Serato export
`data/serato/cmd-lc1.xml.zip`, now has one: `catalog/behringer_cmd_lc_1.py`.)

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

## Serato ↔ Traktor conversion: research (issue #194)

Issue #194 asked for converting a loaded Serato mapping to a `.tsi` and
back, limited to a small command subset (Play/Cue/Sync/hot cues). This
section records what was examined (2026-10-12), why no converter shipped,
and which captures would unblock one. Nothing below was written to any
real file; the `.tsi`/`.xml` exports were unzipped to a scratch directory
and read only.

### The Traktor half is ready (for re-targeting existing bindings)

Everything needed to *re-target* an existing Traktor binding is already
proven, and needs no new binary knowledge:

- **Command IDs 100/206/125 hold on three controllers, not one.** Besides
  the XDJ-XZ cross-check above, both Behringer devices in
  `cmd-studio-4a.tsi` match the hardware-captured catalogs exactly:
  CMD Micro deck A Sync/Play/Cue on `A#0`/`B0`/`C1` = notes 22/23/24 and
  deck B on `D2`/`D#2`/`E2` = 38/39/40 (`catalog/behringer_cmd_micro.py`);
  CMD Studio 4a Cue/Play on `G2`/`G#2` = 43/44 (left) and `D#5`/`E5` =
  75/76 (right) (`catalog/behringer_cmd_studio_4a.py`).
- **`CMAD.TargetDeck` 0-3 is decks A-D.** In the XDJ-XZ export it follows
  the MIDI channel (Ch01 → 0 … Ch04 → 3); in the CMD Micro mapping both
  decks share channel 1 and only `TargetDeck` (0 vs 1) tells them apart —
  so the deck lives in `TargetDeck`, not in the channel.
- **The three commands always use the same settings.** Across all 80
  mappings of commands 100/206/125: input Play and Sync are
  `Button`/`Toggle`, input Cue is `Button`/`Hold`, every output is
  `LED`/`Output`. Re-labelling keeps those bytes as they are.
- **Re-labelling is already a supported write** (`_export_tsi` →
  `TsiDocument.to_text(relabel)`), byte-identical outside the edited
  `DCBM` labels.

Limits that a converter would have to report, not work around:

- a template can only receive commands it already holds — the real CMD
  Studio 4a mapping has Play and Cue but **no Sync** binding, although the
  hardware has a SYNC button (catalog notes 45/77);
- some of these bindings carry **modifier conditions**: 8 of the 10 input
  Sync mappings in the XDJ-XZ export have `ModifierOneId` 2548 set, and 2
  output Play mappings have `ModifierOneId` 100. Re-labelling such a
  binding to a Serato trigger keeps the condition, so the new button only
  works while that modifier is in the recorded state;
- one command can appear several times per deck (the XDJ-XZ export has a
  second device whose Play/Cue *outputs* drive CC 77/68 screen feedback),
  so "the" Play binding of a deck isn't always unique.

### The Serato half is the blocker

**No real Serato export contains a Play, Cue or Sync mapping.** All three
real files (`data/xdj_xz-ddj_xp2-4decks.xml`,
`data/serato/cmd-lc1.xml.zip`, `data/serato/ddj-xp2-custom.xml.zip`) use
only four mapping tags in total:

| Tag | Elements across the 3 files |
|---|---|
| `auto_loop_specific_length` | 2,591 |
| `codfather_fx` | 768 |
| `codfather_st` | 732 |
| `auto_loop_roll_specific_length` | 231 |

Serato's own mapping guide can't be fetched (Cloudflare bot challenge, see
the Help menu note in `CLAUDE.md`), and no other source in this repository
names the XML tag Serato writes for Play, Cue or Sync. Without that name:

- **Serato → Traktor** can't tell which Serato element is "Play", so it
  has nothing to re-target the Traktor template's bindings to;
- **Traktor → Serato** can't write a Serato element for a Traktor Play
  binding — that would mean inventing a tag, a `translation`
  (`action_on`/`behaviour`) and aliases, the same kind of fabrication the
  catalog refuses for controller MIDI data.

The four tags the real files *do* contain don't help either: no Traktor
command ID for loops or effects has been cross-checked (only 100/125/206
are named), and the meaning of a Serato `slot_id` for
`auto_loop_specific_length` (which loop length a slot stands for) isn't
confirmed either (`CLAUDE.md`'s 10x-duplication note).

So no converter shipped for #194 — a half that would only ever report
"not supported" for every element of every real file would be dead code.

### `CMAD` layout check (for a future "create a binding" feature)

Parsing every one of the 9,360 real `CMAD` payloads with the field list
above consumes each one **exactly**, with no trailing byte — good evidence
the field *order* is right. The values of the "Unknown" fields are not
understood, though:

- the first `DWORD` is always `4`, and the last is always `0`;
- the `DWORD`s before `SetValueTo`, before `LedMinControllerRange` and
  before `LedMaxControllerRange` are `1` or `2` and always move together
  (8,118 × `1`, 1,242 × `2`), which looks like a value-type tag, but isn't
  proven to be one;
- the documented `Resolution` enum doesn't match reality: 5,396 mappings
  carry `0x00000001`, which isn't one of its values (`0x3D800000`, the
  documented default, appears 3,945 times; `0x3B800000`, not in the enum,
  19 times).

So *creating* a binding (needed whenever the template lacks a command)
would still mean copying a `CMAD` from another mapping of the same command
and hoping its unknown fields mean the same thing — not done.

### What would unblock a converter

Captures the maintainer could make, in order of value:

1. **Serato tag names (unblocks both directions for the subset).** In
   Serato DJ Pro, with a controller that has no native Serato support (e.g.
   the CMD LC-1, or the IAC Driver), MIDI-learn deck 1 and deck 2 Play,
   Cue and Sync, then export the mapping XML. Better still: one export per
   step (Play only, then Play + Cue, …) so each new element is
   unambiguous. Hot cues 1-8 on one deck the same way, if hot cues are
   wanted too.
2. **A Traktor template with every target command.** A `.tsi` for the
   destination controller that already has Play, Cue and Sync (and hot cues
   if wanted) mapped on every deck, without modifier conditions — the
   converter would only re-label it.
3. **Hot-cue command IDs.** Map hot cue 1 and hot cue 2 on deck A in
   Traktor on a known note, export, and the ID can be cross-checked the
   same way as 100/206/125. (Not checked here: the community list's
   hot-cue IDs stay unverified, per this file's rule.)
4. **`CMAD` field meaning (only to create bindings).** Two exports of the
   same Traktor mapping, before and after adding exactly one command, then
   after changing exactly one setting (e.g. Resolution, or "Set to value")
   in Traktor's Controller Manager — the byte difference names the field.

With (1) and (2), the conservative design is: take a Serato mapping and a
template `.tsi`; for each Serato Play/Cue/Sync element whose deck maps to
a template binding with the same command and `TargetDeck`, re-label that
binding to the Serato trigger through the existing `to_text(relabel)`
path; list every other Serato element, every template binding left
untouched and every modifier-conditioned binding in a report.

## Sources

- [ivanz/TraktorMappingFileFormat](https://github.com/ivanz/TraktorMappingFileFormat) — reverse-engineered `.tsi` format spec (wiki + `.bt` binary template)
- [Native Instruments — Managing Your Track Collection](https://docs.native-instruments.com/ni-tech-manuals/traktor-pro-manual/en/managing-your-track-collection) — confirms `.nml` is the collection format, not mappings
