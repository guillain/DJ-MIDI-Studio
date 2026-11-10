# 🧪 Hardware session

> 🧪 One checklist of everything the project still needs to try on real
> controllers and DJ software. Capture what the controller sends, mark each
> check, and paste the report into the issue it names.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Hardware session

## Table of Contents

- [Why](#why)
- [Open it](#open-it)
- [Run a check](#run-a-check)
- [The checks](#the-checks)
- [Share the report](#share-the-report)
- [Related](#related)

## Why

Some answers can't come from documentation. For example, the DDJ-XP2's
official MIDI list and rekordbox's own mapping disagree on two note numbers,
and nobody has recorded what the CMD jog wheels send. This window lists those
open questions, in one place, for whoever has the hardware.

## Open it

**`Help` → `Hardware Session…`**. The window can stay open beside the app.
What you do is saved as you go (`Exports/hardware-session.json` in the
workspace), so a session can be continued another day.

## Run a check

1. Pick a check on the left and read its steps.
2. For a check that listens to the controller, click **`Start capture`**,
   do what the steps say, then click **`Stop capture`**. Every message
   received is listed. The line under the list says what the capture means.
   For the DDJ-XP2 loop buttons, it says which source the notes you pressed
   agree with. **`Clear capture`** starts again.
3. Mark the check **`Pass`**, **`Fail`** or **`Skip`**, and write what you saw
   in the note. **`Reset`** brings it back to *to do*.

The app listens through the [Live Monitor](live-monitor.md), which is started
for you. While a capture runs, presses only go to the capture: they don't
fire [macros](midi-macros.md). The capture doesn't see pitch bend messages
yet: if a CMD Studio 4a jog sends nothing, write that in the note.

## The checks

| Check | What it settles | Issue |
| --- | --- | --- |
| DDJ-XP2: 1/2X and 2X notes | Notes 16 / 17 (official PDF) or 18 / 19 (rekordbox) | #356 |
| CMD Micro / CMD Studio 4a jogs | What the jogs send, so they can turn on screen | #356 |
| Atelier: probe the LEDs | Real LED addresses, via [the Atelier](atelier.md)'s LED probe | #413 |
| Pioneer pad colours | Which value shows which colour | #413 |
| No freeze during a live session | The freeze fix, and which port sends MIDI bursts | #356 |
| Serato: MIDI-learn Play, Cue and Sync | Serato's own function names | #194 |
| Traktor: import a playlist | Whether Traktor accepts this app's `.nml` | #356 |
| Traktor: Controller Manager exports | How Traktor writes a new binding | #233 |

## Share the report

**`Copy report`** or **`Save report…`** gives the whole session as Markdown,
in English. It contains the results, your notes and the captured messages.
Paste it into the issue each check names. The app never sends anything
itself.

## Related

- [Verify a controller profile](profile-check.md): check a whole profile, control by control.
- [Live Monitor](live-monitor.md): watch raw MIDI from your controller.
- [Report a problem](report-a-problem.md): send the log after the live session check.
