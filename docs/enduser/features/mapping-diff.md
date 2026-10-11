# 🔍 Compare mappings

> See what changed between two mappings — trigger by trigger, by physical
> control — instead of reading a 16,000-line XML diff.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Compare mappings

## Table of Contents

- [Opening a comparison](#opening-a-comparison)
- [What the list shows](#what-the-list-shows)
- [Serato's repeated triggers](#seratos-repeated-triggers)
- [Finding a change on the controller](#finding-a-change-on-the-controller)
- [Related](#related)

## Opening a comparison

Open a mapping first, then from the **File** menu:

| Menu | Compares the open mapping with |
| --- | --- |
| `Compare Mapping With…` | Any Serato `.xml` or Traktor `.tsi` file you pick — a colleague's mapping, an older export, a backup |
| `Compare With Previous Version` | The `.bak` kept next to the file by its last save (greyed out when there is none) |

The open mapping is compared **as it is in the app**, unsaved edits
included, so you can check what you are about to save. The window title
line reads *From `<the other file>` to `<the open mapping>`*: everything is
described as going from the other file to yours.

## What the list shows

Each row names the physical control (from every controller profile that
knows the trigger — a mixed DDJ-XP2 + XDJ-XZ setup can show both), the raw
trigger (channel, Note/CC number, and whether it is the press or the LED
output), and the change. Rows are grouped by kind:

| Group | Means |
| --- | --- |
| **Re-assigned** | The trigger now drives a different function, e.g. `codfather_st (deck 3, slot 1) -> play (deck 3, slot 1)` |
| **Added** | A function bound only in your mapping |
| **Removed** | A function bound only in the other file |
| **Changed values** | Same function on the same trigger, with different translation or alias values, e.g. `alias on: 127 -> 100` or `behaviour: explicit -> toggle` |
| **Duplicate count** | Identical content, but a different number of copies (see below) |

The order of controls in the file does not matter: two files with the same
bindings in a different order compare equal.

## Serato's repeated triggers

Serato writes every trigger several times — usually 10 identical copies —
and needs them all. The comparison counts copies instead of listing each
one, so a file that lost one copy shows a single **Duplicate count** row
(`copies: x10 -> x9`), not nine adds or removes. When only some of the
copies were edited, the **Changed values** row says how many
(`on 1 of 10 copies`). Edits made in the **By Deck** view always apply to
every copy at once.

## Finding a change on the controller

Click a row: the control is highlighted on the controller layouts and
selected in **By Channel**, just like clicking it on a layout. A removed
trigger that no longer exists in your mapping is only highlighted. The
window stays open beside the main one, so you can walk through the list.

## Related

- [Mapping editor](mapping-editor.md): editing, validation, the diff shown before each save, and restoring the previous version.
- [Traktor mappings](traktor-mappings.md): comparing `.tsi` files works the same way.
- [Workspace and preferences](workspace.md#your-files): every file action in the File menu.
