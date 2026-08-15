# End-to-End Examples

## Table of Contents

- [Detect a connected controller](#detect-a-connected-controller)
- [Open a Serato or Traktor mapping](#open-a-serato-or-traktor-mapping)
- [Inspect a physical MIDI event](#inspect-a-physical-midi-event)
- [Route MIDI between devices](#route-midi-between-devices)
- [Work with an unknown controller](#work-with-an-unknown-controller)

## Detect a connected controller

1. Connect the controller before starting DJ MIDI Studio.
2. Open `Settings -> Preferences...`.
3. Choose `Suggest detected integration` if high-confidence matches may be
   activated automatically. Keep `Ask before enabling` to confirm detections.
4. Start or refresh the `Live Monitor` port list.

The Dashboard and layout selectors update when a known controller is matched.
The detection message includes the confidence and the MIDI port evidence. An
ambiguous result is never silently selected.

Known built-in profiles currently include DDJ-XP2, XDJ-XZ, DDJ-1000, DDJ-FLX4,
DDJ-FLX10, DDJ-REV1, Numark Mixtrack Pro FX, and Hercules DJControl Inpulse
500. The DDJ-FLX4, DDJ-REV1, Numark, and Hercules profiles are conservative and should be checked
against the target hardware firmware before production use.

## Open a Serato or Traktor mapping

1. Open `Settings -> Preferences...`.
2. Select `Suggest detected integration` for automatic parser selection, or
   leave the default confirmation policy enabled.
3. Use `File -> Open...` and choose the mapping file.

Serato XML (`<midi>`) and Traktor NML (`<NML>`) signatures are detected before
the parser is selected. If the file is malformed, unsupported, or ambiguous,
the software selector remains available so the user can choose explicitly.

For the supported Traktor NML subset and its known limitations, see the
[Traktor integration guide](traktor.md).

## Inspect a physical MIDI event

1. Open `Live Monitor`.
2. Click `Select all sources`, or check only the desired MIDI inputs.
3. Click `Start monitoring`.
4. Trigger a button or pad on the controller.

Use the `Source device` column to identify the originating MIDI port. The
`Physical / Serato` column contains the physical control and mapping function;
the device name is intentionally kept in its dedicated column.

## Route MIDI between devices

1. Enable `Enable MIDI routing policies` in Preferences.
2. Open `MIDI Routing`, select a source and destination, then click `Add route`.
3. Optionally enable the Clock policy and add one or more source/destination lines.
4. Click `Start routing` only after checking the selected ports.

Routing is opt-in, opens only the ports used by enabled routes and Clock policy,
and closes them with `Stop routing`. The route graph rejects direct cycles;
Clock messages are subject to the configured minimum interval safeguard.

## Work with an unknown controller

1. Open `Controller Setup`.
2. Select the MIDI input and capture representative buttons or pads.
3. Review the learned channel, event type, and data value.
4. Apply the generated generic profile for the current session.

Unknown devices remain usable without claiming an incorrect catalog. Verify
the captured values against the manufacturer's MIDI documentation before
sharing or exporting a profile for wider use.
