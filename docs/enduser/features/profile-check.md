# ✅ Verify a controller profile

> ✅ Press each control of your controller when asked: the app checks it
> against the profile, then the report can go to the project so the profile
> is marked verified or corrected.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Verify a controller profile

## Table of Contents

- [Why](#why)
- [Run a check](#run-a-check)
- [Read the results](#read-the-results)
- [Share the report](#share-the-report)
- [Related](#related)

## Why

Most controller profiles were transcribed from the vendor's MIDI
documentation, or built from rekordbox's mappings, and have never been
pressed on a real unit (`Not yet` in
[Supported controllers](../controller-profiles.md#built-in-controllers)).
If you own one of those controllers, a ten-minute check tells everyone
whether its profile is right.

## Run a check

1. Connect the controller.
2. **`File` → `Controller Profile` → `Verify Profile with the Controller…`**.
   The controller detected on your MIDI inputs is preselected; pick another
   one in **Controller** if needed, and choose its input in **Listen on**
   when several controllers are connected.
3. Click **`Start`**. The window asks for one physical control at a time —
   `Press Sync`, then `Hold SHIFT and press Sync` when the profile has a
   SHIFT layer for it. Press it. Any deck counts, and for a pad any pad mode.
4. **`Skip (not on my unit)`** for a control your controller doesn't have,
   **`Back`** to redo the previous one.

The app listens through the [Live Monitor](live-monitor.md) (started for
you). While the window is open, the presses are only used for the check:
they don't fire [macros](midi-macros.md).

## Read the results

Each answer is listed as it comes:

- ✓ the control sends what the profile says;
- ✗ it sends something else — the line says what, and whether the profile
  gives that message to another control (two controls swapped) or doesn't
  know it at all (a wrong note number);
- – skipped.

## Share the report

**`Submit to the project…`** opens a pre-filled GitHub issue (label
`profile-check`) with the report in your browser; nothing is sent until you
submit it there. A long report is copied to the clipboard instead, to paste
into the issue. **`Copy report`** and **`Save report…`** (Markdown, in the
`Exports` folder by default) keep it for you. The report names the
controller, the app version and the input — no mapping or personal file is
included.

## Related

- [Supported controllers](../controller-profiles.md): which profiles are verified.
- [Controller Setup](controller-setup.md): build or correct a profile.
- [Live Monitor](live-monitor.md): watch raw MIDI from your controller.
