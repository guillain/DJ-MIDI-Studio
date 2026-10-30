# 📸 Snapshots

> Keep named versions of a mapping — "before the club gig", "festival
> setup" — and see what changed since, or bring one back.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Snapshots

## Table of Contents

- [Save a snapshot](#save-a-snapshot)
- [Compare, restore, delete](#compare-restore-delete)
- [Where snapshots are kept](#where-snapshots-are-kept)
- [Related](#related)

## Save a snapshot

With a mapping open, choose `File → Save Snapshot...` and give the version
a name. The snapshot is the mapping exactly as it is in the app at that
moment, unsaved edits included — the file on disk isn't touched.

Saving a mapping already keeps one previous version (`Restore Previous
Version...`); snapshots keep as many as you like, under names you choose.

## Compare, restore, delete

`File → Snapshots...` lists the open mapping's snapshots, newest first:

- **Compare** (or double-click) opens the [mapping diff](mapping-diff.md):
  what the mapping in the app does differently from that snapshot, control
  by control.
- **Restore** puts the snapshot's mappings back. It is one step of
  `Edit → Undo`, and nothing is written until you save the mapping. Restore
  works on Serato mappings; for Traktor, rekordbox and Mixxx mappings,
  compare instead.
- **Delete** removes the snapshot.

## Where snapshots are kept

In the `Snapshots` folder of your DJ MIDI Studio folder
(`Documents/DJ MIDI Studio`), one subfolder per mapping, each snapshot a
normal mapping file you could also open directly. A workspace backup
(`File → Back Up Workspace...`) includes them.

## Related

- [Mapping diff](mapping-diff.md)
- [Copy Deck Mappings](deck-copy.md)
- [Mapping editor](mapping-editor.md)
