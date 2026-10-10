# ⟳ Controller Sync

> One button brings every connected controller into a known state: pad
> modes, LEDs, banks — whatever you recorded for it, sent to all of them at
> once.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Controller Sync

## Table of Contents

- [Why Sync](#why-sync)
- [Record a sync set](#record-a-sync-set)
- [Sync your controllers](#sync-your-controllers)
- [Sync at launch](#sync-at-launch)
- [How Sync finds each controller](#how-sync-finds-each-controller)
- [Manage sync sets](#manage-sync-sets)
- [Related](#related)

## Why Sync

After plugging controllers in, or after DJ software has reset them, you
usually press the same buttons every time: pick a pad mode, light a bank,
select a deck. Sync records those presses once per controller and replays
them all with a single click, on every connected controller at the same
time.

## Record a sync set

The quickest way is the **`● Rec`** button at the top right of the menu bar:

1. Click **`● Rec`**: the app listens to every connected MIDI controller.
2. Press the controls you want sent at initialization, in order, on any
   number of controllers.
3. Click **`■ Stop`**. One set is saved per controller that sent something,
   named after the controller recognized from its port (or the port name
   itself for an unknown device).

To record a single controller under a name you choose instead:

1. Open [Controller Setup](controller-setup.md) and type the controller's
   name.
2. Tick its input port and click `Start learning`.
3. Press the controls you want sent at initialization, in order.
4. Click `Stop learning`, then `Save as controller sync set`
   (`MIDI Output` → `Playback`).

There is one set per controller. Saving again under the same name asks
before replacing the existing set.

## Sync your controllers

Click **`⟳ Sync`** at the top right of the menu bar (beside the ⚙
Preferences button), or **`Sync controllers`** in the
[Live Monitor](live-monitor.md).

Each set is sent in recorded order, immediately (the pauses from the
recording are dropped). The status bar shows how many controllers were
synced and which ones were not connected.

## Sync at launch

With ⚙ **Preferences** → **Sync controllers at launch** ticked (the
default), every stored set is sent once when the app starts, as if you had
clicked `⟳ Sync`. Nothing happens when no set is recorded. Untick it to
sync only on demand.

## How Sync finds each controller

1. The output port the set was recorded on, if it is connected.
2. Otherwise, an output port whose name contains the recorded port name or
   the controller name, ignoring case and punctuation (`DDJ-XP2` matches
   `PIONEER DDJ-XP2`).
3. Otherwise the controller is skipped and reported. The other controllers
   are still synced.

## Manage sync sets

Open ⚙ **Preferences** → **Controller sync**. Each set shows its message
count; choose which output port it goes to (`Auto` follows the rules above)
or remove it.

Each set is a file in `Documents/DJ MIDI Studio/Sync`, one per controller,
so you can back it up or copy it to another computer. Sets recorded with an
older version are moved there automatically the first time you start this
one.

## Related

- [Controller Setup](controller-setup.md): where sync sets are recorded.
- [Live Monitor](live-monitor.md): check what each controller sends.
- [Workspace and preferences](workspace.md): the ⚙ Preferences dialog.
