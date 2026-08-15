# MIDI Clock compatibility notes

## Current safety policy

DJ MIDI Studio currently exposes MIDI Clock as a tested engine primitive, not
as an enabled GUI routing mode. The mirror forwards Start, Continue, Stop, and
24 PPQN Clock messages from one selected source, rejects implausibly short
intervals, and reports observed timing jitter.

## Serato DJ

Serato's MIDI setup can route output to the application's virtual monitor when
the user adds that destination explicitly. This is the supported way to
observe Serato output. Clock behavior depends on the Serato version, hardware
MIDI configuration, and whether the selected device exposes Clock messages;
the application must not assume that a mapping file implies Clock support.

## Rekordbox

Rekordbox configurations and Performance-mode MIDI behavior vary by version
and connected hardware. A mapping parser match does not prove that Rekordbox
is a valid Clock source or destination. Clock mirror support therefore remains
opt-in and requires a real-device verification of Start/Stop/Continue and
24 PPQN behavior before it can be enabled in the GUI.

## Validation rule

Cross-software Clock sync stays disabled until a test record exists for the
specific Serato/Rekordbox versions, hardware ports, direction, and measured
jitter. Virtual-port tests validate routing policy and timing logic; they do
not claim vendor compatibility.
