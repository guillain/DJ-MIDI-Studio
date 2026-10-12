# 🎵 Music Library

> Get a messy collection mix-ready: scan your folders, fix tags in bulk,
> see every key on the Camelot wheel, sort tracks into genre categories, and
> build harmonic playlists you can export to Serato and Traktor.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Music Library

## Table of Contents

- [What it does](#what-it-does)
- [Scan your music](#scan-your-music)
- [Relink moved tracks](#relink-moved-tracks)
- [Browse, sort and filter](#browse-sort-and-filter)
- [Listen to a track](#listen-to-a-track)
- [Edit tags](#edit-tags)
- [Write tags to many tracks at once](#write-tags-to-many-tracks-at-once)
- [Find duplicate tracks](#find-duplicate-tracks)
- [Genre categories](#genre-categories)
- [Playlists](#playlists)
- [Import and export with DJ software](#import-and-export-with-dj-software)
- [Safety: what is never touched](#safety-what-is-never-touched)
- [Related](#related)

## What it does

The `Music Library` tab manages your own tracks, independently of any MIDI
mapping. It is built for large collections (tens of thousands of files)
and stays responsive while it works.

![Music Library: track table and Track panel](../../images/layout/music-library.png)

## Scan your music

1. `Add folder…` and pick one or more music folders.
2. Click `Scan & read tags`. A progress bar runs; the window stays usable.

Later scans only re-read files that changed. A file that disappears, for
example on an unplugged drive, is greyed out as *missing* instead of being
forgotten. MP3, WAV, AIFF, FLAC, M4A, OGG and AAC files are indexed.

The index lives beside the preferences file as `library.sqlite3`; it
records file paths, sizes, dates and a cache of the tags, never the audio.

## Relink moved tracks

When you move or rename folders, the old paths show up as *missing* and the
files appear again under their new paths. `Relink missing…` finds where each
missing track went and lists it with its proposed new path:

- Rows with exactly one file of the **same name and size** are ticked
  already.
- Several possible files, a file with the same name but another size, or a
  differently named file whose title and artist tags match are listed but
  left unticked. Pick the right file in the `Relink to` list and tick it.
- `(not scanned yet)` means the file sits in one of your music folders but
  hasn't been scanned; relinking indexes it.

Click `Relink checked…` and confirm. Playlists that listed the old path now
use the new one, the cached tags follow, and the stale entry disappears.
Only this app's index changes: no audio file and no Serato, Traktor or
Rekordbox library is touched. Relinking can't be undone, so check the list
before confirming.

![Relink missing tracks: two moved files, ticked](../../images/layout/music-library-relink.png)

## Browse, sort and filter

- Click a column header to sort (BPM sorts numerically).
- Type in the search box to search titles, artists, genres, BPM, keys and
  comments.
- Narrow the list with the filters under it. They combine, and the
  `N / M tracks` counter shows how many tracks are left:

| Filter | Shows |
| --- | --- |
| Category | One category, or `Uncategorized` |
| Genre | Tracks with that genre tag (the list holds every genre in your library) |
| Key | Tracks with that key tag, as written in the file |
| Camelot | Tracks in that Camelot key; tick `+ compatible` to add the keys that mix harmonically with it (±1 on the wheel and the relative major/minor) |
| BPM `min` – `max` | Tracks within that range, both ends included; leave a side at `min` / `max` for no limit. Tracks without a BPM are hidden while a BPM limit is set |

`Reset filters` clears the search box and every filter. Filters stay as they
are after a rescan or a tag edit.

![Filters: 170–180 BPM, compatible with 8A](../../images/layout/music-library-filters.png)

The **Camelot** column translates any key notation into the Camelot wheel
used for harmonic mixing: `Am`, `F#m`, Open Key `7m` and `8A` are all
understood.

## Listen to a track

The preview bar under the table plays the selected track, so you can check
a category or a key by ear without opening your DJ software:

- `▶ Play` / `❚❚ Pause` and `■ Stop` (stop rewinds to the start).
- Drag the slider to move through the track; the label shows position and
  length.
- While a track plays, selecting another one switches to it straight away —
  handy for auditioning a list with the arrow keys.
- Tick **Start at 30%** to skip the intro.

![Preview bar playing a track](../../images/layout/music-library-preview.png)

Playback stops when you leave the tab or close the app. If your system
can't play audio through Qt, the bar stays greyed out with a tooltip
explaining why; files are only read, never changed.

## Edit tags

Select a track; the **Track** panel shows its title, artist, album, genre,
BPM, key, comment, rating and energy. Edit any field and click `Write tags`
(or press Enter). Only the changed fields are written to the file.

`Undo` / `Redo` write the previous values back. `Revert` discards edits you
haven't written yet. `Clean noise frames…` lists leftover junk tags (old
ID3v1 comment copies, old player preferences, ReplayGain values…) and
removes them only after you confirm.

## Write tags to many tracks at once

To give a whole album the same genre, or fix an artist name everywhere:

1. Select the tracks in the table (Shift-click for a range, Cmd/Ctrl-click
   to add tracks).
2. Optionally type the new values in the Track panel.
3. Click `Write tags to selection…`.
4. Tick the tag(s) to write. Each field starts with the Track panel's value,
   and the fields you just edited are already ticked. Unticked tags are left
   as they are in every file; a ticked empty field clears that tag.
5. Click `Write to N track(s)`.

Tracks that already have the value are skipped, the whole batch is a single
`Undo` step, and a file that can't be written is reported at the end
without stopping the others.

A long batch shows a progress window (`Writing tags… 312/850`), and so does
its `Undo`. `Cancel` stops after the current file: the files already written
keep their new tags, and `Undo` restores exactly those. The window stays
open until the table has been refreshed, so the app is ready as soon as it
closes.

![Write tags to selection](../../images/layout/music-library-bulk-tags.png)

## Find duplicate tracks

Click `Find duplicates…` (next to `Scan & read tags`, after a scan). The
search runs in the background with a progress bar, then a **Duplicate
tracks** window lists two kinds of groups:

| Group | Meaning |
| --- | --- |
| Exact copies | Byte-identical files. Only files of exactly the same size are read and compared, so this stays quick on a large collection |
| Same artist + title | Tags that match once case, accents, punctuation, `feat.` credits and an `(Original Mix)` suffix are ignored. Other versions — `(Extended Mix)`, `(Radio Edit)`, remixes, `(Live)` — stay separate. These are candidates, not proof: compare them before acting |

Each file shows its path, format and size; expand a group to see each
file's bitrate. Select a file and click `Reveal in Finder` (or double-click
it) to see it in your file manager.

Nothing is deleted or moved from this window: you decide which copy to keep
and remove the others yourself, in Finder or in your DJ software. Track
lengths are not compared yet.

![Duplicate tracks: an exact copy and two same artist + title groups](../../images/layout/music-library-duplicates.png)

## Genre categories

Tracks are sorted into two-level categories, `Family / Name` (for example
`Tek / PsyTrance`), using your folder names and Serato crate names first,
then the genre tag, since a genre tag alone is often wrong.

- A category shown in amber as `? Tek / PsyTrance` is only a
  **suggestion** from a near-match spelling. Select the track and click
  `Confirm suggested category` to make that spelling a permanent alias.
  `Confirm all suggestions (N)` does it for every track shown in the table
  (narrow them with the filters first if you want), after listing each
  genre → category pair. Suggestions are never applied on their own.
- The **Categories** panel shows track counts and lets you create, rename,
  merge and delete categories and aliases (`DnB`, `D&B` and `Drum and Bass`
  can all mean `Drum & Bass`).

![Music Library: Categories panel](../../images/layout/music-library-categories.png)

## Playlists

The **Playlists** panel:

| Button | Result |
| --- | --- |
| `New from selection` | A playlist of the selected rows |
| `Auto: sort visible` | Every visible row, grouped by category, then BPM range, then key |
| `Auto: match current` | The selected track followed by every visible track within ±6 % BPM and a harmonically compatible Camelot key |
| `Auto: mix path…` | The visible tracks chained into a set you can actually mix: each track is within ±6 % BPM and a compatible Camelot key of the one before, and the BPM rises, falls or stays steady (you choose). Starts from the selected track (else the slowest, or the fastest when falling); tracks that can't be chained go to a second `… (leftovers)` playlist |
| `Rename…` / `Delete` | Manage the selected playlist |

A rising or falling path never steps back, so it skips tracks to keep the
BPM moving one way — filter the table to one category first for the longest
paths, and check the leftovers playlist for what didn't fit.

![Music Library: Playlists panel](../../images/layout/music-library-playlists.png)

## Import and export with DJ software

| Software | Import (read-only) | Export |
| --- | --- | --- |
| Serato | `Import Serato crate…` (`_Serato_/Subcrates/*.crate`) | `Export as Serato crate…` writes a new `.crate` where you choose; copy it into `_Serato_/Subcrates` yourself |
| Traktor | `Import Traktor NML…` (playlists of `collection.nml`) | `Export as Traktor playlist…` writes a new `.nml`; in Traktor, right-click `Playlists` → `Import Playlist` |
| Rekordbox | `Import Rekordbox export…` (USB `PIONEER/rekordbox/export.pdb`) | — |

Imported Serato crate names also help categorize tracks.

## Safety: what is never touched

- Tag writes change only the fields you edit. Serato and Traktor data stored
  inside your audio files (cue points, beat grids, analysis) is preserved.
- Serato, Traktor and Rekordbox library files are only ever read. Exports
  always create a new file at the location you choose.
- Undo writes the old values back through the same careful path.
- `Find duplicates…` only reads files; it never deletes or moves one.

## Related

- [Supported files](../user-guide.md#supported-files)
- [Mapping editor](mapping-editor.md)
