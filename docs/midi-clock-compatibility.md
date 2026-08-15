# MIDI Clock compatibility notes

## Current safety policy

DJ MIDI Studio exposes MIDI Clock as an opt-in GUI routing mode. The mirror
forwards Start, Continue, Stop, and 24 PPQN Clock messages from one or more
configured sources, rejects implausibly short intervals, and reports observed
timing jitter.

Clock topology is validated across normal MIDI routes and Clock routes
together. This prevents a regular route in one direction combined with a
Clock route in the reverse direction from creating a feedback loop. A Clock
source must have at least one distinct destination, and destination names
cannot be duplicated.

The MIDI Routing panel reports four distinct states: policy disabled, routing
configured but blocked by the Preferences safety gate, waiting for source
ticks, and `CLOCK ACTIVE` after recent Clock ticks have actually been received.
`CLOCK INACTIVE` after starting the session reports whether the source port is
not open, open without ticks, or has sent transport without any Clock ticks.

## Serato DJ

Serato's MIDI setup must route its MIDI Clock output to a destination that the
application can receive. In `MIDI Routing`, enable `Create virtual input for
Serato Clock`, select the generated `DJ MIDI Studio Serato Clock In` source,
add its destination controller, then start routing. In Serato's MIDI setup,
select that virtual port as the MIDI Clock output destination and enable the
Clock/Sync output option for the active deck or session. The virtual port is
created only while routing is running, so Serato should be configured after
DJ MIDI Studio has started the session.

Serato may emit transport messages only when its Clock/Sync mode and version
support them. If the controller receives Clock ticks but does not start or
stop, verify Serato's MIDI Clock transport/start-stop options and test the
controller's external-sync mode; a mapping file alone does not imply Clock
support.

Serato is more complex than a direct hardware Clock source: Serato's output
must be explicitly assigned to the application's generated virtual input, and
the virtual input exists only while the routing session is running. Configure
Serato after starting the session, and stop the session before removing or
changing that virtual endpoint. Do not use the same port as both the Serato
Clock input and a destination in a return route.

For Serato, `CLOCK INACTIVE` usually means one of these steps is missing:
start routing in DJ MIDI Studio, select `DJ MIDI Studio Serato Clock In` as
Serato's MIDI Clock output destination, and enable Serato's Clock/Sync output
for the active deck/session. The virtual port is not created before the
routing session starts. Hover the status label for the same actionable hint.

## Traktor

Traktor uses standard MIDI realtime messages for external Clock. Select the
Traktor MIDI output as a physical Clock source in `MIDI Routing`, enable the
Clock policy, and route it to the destination controller or software input.
The application forwards Start, Continue, Stop, and 24 PPQN Clock ticks; it
does not attempt to reinterpret Traktor's beat phase, tempo, transport mode,
or mapping-file settings. Configure Traktor's external Clock mode and verify
the destination's external-sync behavior before a live session.

## Rekordbox

Rekordbox configurations and Performance-mode MIDI behavior vary by version
and connected hardware. A mapping parser match does not prove that Rekordbox
is a valid Clock source or destination. Clock mirror support therefore remains
opt-in and requires a real-device verification of Start/Stop/Continue and
24 PPQN behavior before it can be enabled in the GUI.

## Validation rule

Cross-software Clock sync stays disabled until a test record exists for the
specific Serato/Traktor/Rekordbox versions, hardware ports, direction, and
measured jitter. Virtual-port tests validate routing policy and timing logic;
they do not claim vendor compatibility.
