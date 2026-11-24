# 🧪 Tests menu and hardware scenarios

> 🧪 Every functional test and hardware check in one menu, **`Tests`**
> (between `Macros` and `Help`): step-by-step scenarios on real controllers
> and DJ software, Serato MIDI Learn, set recording and analysis, and the
> MIDI latency test.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Tests menu

## Table of Contents

- [The Tests menu](#the-tests-menu)
- [Why](#why)
- [Open it](#open-it)
- [Run a check](#run-a-check)
- [The checks](#the-checks)
- [Share the report](#share-the-report)
- [Serato MIDI Learn](#serato-midi-learn)
- [Related](#related)

## The Tests menu

| Entry | What it does |
| --- | --- |
| **Hardware Scenarios…** | The checklist below: each scenario's steps, a capture, pass / fail and a report |
| **Check a Controller…** | [Verify a controller profile](profile-check.md), control by control and light by light |
| **Serato MIDI Learn…** | Teach Serato the notes the app sends on the IAC bus ([below](#serato-midi-learn)) |
| **Record a Live Set** | Starts the [Live Monitor](live-monitor.md)'s set recording |
| **Analyse a Set…** | Which controls a recorded set used, how often, in which order |
| **MIDI Latency Test…** | [Round-trip latency](midi-latency.md) through a port that echoes |

## Why

Some answers can't come from documentation. For example, the DDJ-XP2's
official MIDI list and rekordbox's own mapping disagree on two note numbers,
and nobody has recorded what the CMD jog wheels send. This window lists those
open questions, in one place, for whoever has the hardware.

## Open it

**`Tests` → `Hardware Scenarios…`**. The window can stay open beside the app.
What you do is saved as you go (`Exports/hardware-session.json` in the
workspace), so a session can be continued another day.

## Run a check

1. Pick a check on the left and read its steps.
2. For a check that listens to the controller, click **`Start capture`**,
   do what the steps say, then click **`Stop capture`**. Every message
   received is listed. The line under the list says what the capture means.
   For the DDJ-XP2 loop buttons, it says which source the notes you pressed
   agree with. **`Clear capture`** starts again.
3. A check done in another tool has a button that opens it (Check a
   Controller, Serato MIDI Learn, Record a live set, the Studio tab, the
   macros, the Startup Check).
4. Mark the check **`Pass`**, **`Fail`** or **`Skip`**, and write what you saw
   in the note. **`Reset`** brings it back to *to do*.

The app listens through the [Live Monitor](live-monitor.md), which is started
for you. While a capture runs, presses only go to the capture: they don't
fire [macros](midi-macros.md). Pitch bend shows as `Pitch Bend` lines, with a
value from 0 to 16383 (8192 is the centre).

## The checks

| Check | What it settles | Issue |
| --- | --- | --- |
| DDJ-XP2: 1/2X and 2X notes | Notes 18 / 19 while Serato runs (rekordbox, this profile); 16 / 17 with no DJ software (official PDF) | #356 |
| CMD Micro jogs | What the jogs send, so they can turn on screen | #356 |
| CMD Studio 4a: jogs and pitch faders | Whether the pitch bend Traktor binds per deck comes from the jog or the pitch fader | #356 |
| Atelier: probe the LEDs | Real LED addresses, via [the Atelier](atelier.md)'s LED probe | #413 |
| Pioneer pad colours | Which value shows which colour | #413 |
| No freeze during a live session | The freeze fix, and which port sends MIDI bursts | #356 |
| Serato: MIDI-learn the CUE button | Serato's name for Cue (Play, Sync and hot cues are known) | #194 |
| Traktor: import a playlist | Whether Traktor accepts this app's `.nml` | #356 |
| Traktor: learn Sync and Hotcue 1 | Traktor's command numbers for the `.tsi` writer | #233 |
| DDJ-XP2: pad lights with Serato | What a pad's light does when a hot cue is set, pressed, deleted, and with Serato closed | #451 |
| DDJ-XP2: what Serato sends to the lights | Serato's LED messages, spied with MIDI Monitor | #451 |
| DDJ-XP2: the app lights each pad | The pad LEDs, from the Lights tab with Serato closed | #451 |
| Startup Check: each button opens its tool | The Startup Check's buttons | #451 |
| Macros: each one does what its name says | Macros played into Serato | #486 |
| Record a set and analyse it | Named controls and repeated gestures in a real set | #488 |

## Share the report

**`Copy report`** or **`Save report…`** gives the whole session as Markdown,
in English. It contains the results, your notes and the captured messages.
Paste it into the issue each check names. The app never sends anything
itself.

## Serato MIDI Learn

Macros and scenes sent to the IAC bus only reach Serato's functions once
Serato has learned their notes. **`Tests` → `Serato MIDI Learn…`** walks
through them: deck 1 and 2 Play, Cue and Sync, then deck 1's eight hot cues.

1. In Serato, enable the bus in Setup → MIDI and switch MIDI mode on.
2. Click **`Send`**: a 5-second countdown starts. Click the function in
   Serato before it ends and stay there.
3. The note leaves on its own. The step turns ✓ when the note comes back on
   the bus, and the next step is selected. **`Back`** and **`Next`** move
   between steps.
4. At the end, save the MIDI preset in Serato.

The app writes nothing in Serato's files.

## Related

- [Verify a controller profile](profile-check.md): check a whole profile, control by control.
- [Live Monitor](live-monitor.md): watch raw MIDI from your controller.
- [Report a problem](report-a-problem.md): send the log after the live session check.
