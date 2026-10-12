"""The text behind every contextual "?" help button (see help_button.py),
kept in one place so it can be proofread and kept in step with the user
documentation it summarizes. Each entry is (title, rich text, feature page in
docs/enduser/features or None)."""

from __future__ import annotations

HelpEntry = tuple[str, str, str | None]

DASHBOARD_OVERVIEW: HelpEntry = (
    "Dashboard",
    (
        "Summarizes the loaded mapping and gives every registered controller a card: "
        "its picture, whether a connected MIDI port matches it (<i>MIDI: available</i>), "
        "and shortcuts into the <b>By Channel</b>, <b>By Controller</b> and "
        "<b>Controller Images</b> views.<br><br>"
        "Open a Serato <tt>.xml</tt> or Traktor <tt>.tsi</tt> mapping with "
        "<b>File → Open Mapping…</b>."
    ),
    "mapping-editor.md",
)

DASHBOARD_FILES: HelpEntry = (
    "Your files",
    (
        "Everything you work with, in one place:<ul>"
        "<li><b>Mapping</b>: the Serato <tt>.xml</tt> or Traktor <tt>.tsi</tt> file open in the "
        "editor. It stays where your DJ software keeps it; <b>File → Save Mapping</b> writes it "
        "back there.</li>"
        "<li><b>Previous version</b>: every save keeps the version it replaces next to the file "
        "(<tt>.bak</tt>); <b>Restore previous…</b> puts it back.</li>"
        "<li><b>Recent</b>: the last mappings you opened (also in <b>File → Open Recent "
        "Mapping</b>).</li>"
        "<li><b>Sync sets</b>: the initialization messages recorded with <b>● Rec</b> or in "
        "Controller Setup, one per controller and scene (the combo beside <b>⟳ Sync</b> picks the "
        "active scene; a controller without a set for it gets its Default set), sent by <b>⟳ Sync</b>, "
        "at launch, when a controller is plugged in and, if enabled in Preferences, when you switch "
        "scene; "
        "edit their messages in <b>⚙ Preferences → Controller sync → Edit messages…</b>.</li></ul>"
        "Controller profiles you build live in <b>File → Controller Profile</b>. "
        "<b>File → Back Up Workspace…</b> saves your profiles, sync sets, drafts and preferences "
        "(and, if you want, the library index) in one zip; <b>Restore Workspace…</b> brings them "
        "back, on another Mac too, after showing what it overwrites."
    ),
    "workspace.md",
)

DASHBOARD_CONTROLLERS: HelpEntry = (
    "Known controllers",
    (
        "Every controller the app knows: the built-in profiles and the ones you installed from "
        "<b>Controller Setup</b>. The <b>Active controller for drill-down</b> is the one the "
        "<b>Channel</b>, <b>Controller</b> and <b>Images</b> shortcuts open. Hide controllers you "
        "don't own in ⚙ Preferences → Plugins."
    ),
    "controller-images.md",
)

DASHBOARD_TOOLS: HelpEntry = (
    "MIDI tools",
    (
        "Opens the tool windows: <b>Live Monitor</b> (watch what your controllers send), "
        "<b>MIDI Routing</b> and <b>MIDI Clock</b> (route MIDI between devices, follow "
        "Ableton Link), the <b>Metronome</b> and the <b>Controller Emulator</b>. "
        "Each one is a window you can dock, float, maximize or snap to a side "
        "(<b>☰</b> in its title bar)."
    ),
    "workspace.md",
)

MAPPING_VIEWS: HelpEntry = (
    "Mapping views",
    (
        "Three views of the same mapping:"
        "<ul>"
        "<li><b>By Channel</b>: MIDI channel → control → event → function. "
        "Inspect or fix one raw entry precisely.</li>"
        "<li><b>By Deck</b>: Serato deck → slot → function. One edit updates every "
        "duplicate copy at once, so they can never drift apart.</li>"
        "<li><b>By Controller</b>: controller → section → physical control. "
        "Find what a button does.</li>"
        "</ul>"
        "The drawing below each tree shows which controls are mapped, colored by deck. "
        "Tick the layers to show: <b>Controller</b> (the real photo), <b>MIDI</b> (the "
        "photo with its MIDI information, shown alone) and <b>Layout</b> (the app's "
        "markers), on controllers with a measured layout. Selecting anything highlights it in every view; clicking a control "
        "jumps to its raw entry. With <b>Live send</b> on, clicking a control also sends "
        "its MIDI message to the chosen output (<b>⟳</b> refreshes the ports)."
    ),
    "mapping-editor.md",
)

EDIT_PANEL: HelpEntry = (
    "Edit and validate",
    (
        "Edits the item selected in a tree. Every change can be undone "
        "(<b>Edit → Undo</b>).<br><br>"
        "Serato repeats each trigger several times in a mapping and those copies must stay "
        "identical: edit in <b>By Deck</b>, which updates every copy at once.<br><br>"
        "<b>Edit → Validate</b> lists errors, warnings and info in the table below "
        "(duplicate copies are info only: they are expected). <b>File → Save Mapping</b> shows the "
        "exact changes before writing, keeps a backup, and <b>File → Restore Previous Version…</b> "
        "restores it."
    ),
    "mapping-editor.md",
)

FUNCTION_SEARCH: HelpEntry = (
    "Find function",
    (
        "The reverse of the trees: type what a control should <i>do</i> and see which control "
        "does it. Words match the short function names and the original Serato tags "
        "(<tt>loop roll</tt> finds <tt>auto_loop_roll_specific_length</tt>, shown as "
        "<i>Loop roll</i>; hover a result for its tag), case and underscores don't matter.<br><br>"
        "<tt>deck 2</tt> / <tt>slot 3</tt> keep only that deck or slot (numbers as the file "
        "stores them, like the By Deck tab); a bare number matches either. Add <tt>output</tt> "
        "for LED feedback only.<br><br>"
        "Selecting a result outlines <b>all</b> its controls in red on the layout and selects "
        "the first one in the current tab, like clicking it on the layout."
    ),
    "mapping-editor.md",
)

CONTROLLER_IMAGES: HelpEntry = (
    "Controller Images",
    (
        "The reference picture of the selected controller: zoom with the mouse wheel, drag "
        "to pan, <b>Reset zoom</b> to fit. <b>Open documentation</b> opens its bundled "
        "manual or MIDI message list.<ul>"
        "<li><b>Controller</b>: the real photo. <b>MIDI</b>: the same controller with its "
        "MIDI information printed on it, when it ships one. One photo at a time.</li>"
        "<li><b>Layout</b>: a marker on every modeled control, at its true position "
        "(measured on the Controller photo, so greyed out over the MIDI one). With the "
        "Live Monitor running, a marker flashes when you hit that control.</li>"
        "<li><b>Live send</b> sends a clicked control's MIDI message to the chosen output.</li>"
        "</ul>"
    ),
    "controller-images.md",
)

CONTROLLER_EMULATOR: HelpEntry = (
    "Controller Emulator",
    (
        "Play one controller with the mouse. Click a pad or button: it flashes and the "
        "status line shows what the loaded mapping binds it to. Nothing is sent unless "
        "<b>Live send</b> is on.<ul>"
        "<li>Mode buttons (pad modes) and <b>SHIFT</b> are remembered like on the "
        "hardware.</li>"
        "<li>Drag knobs, faders and jog wheels vertically to move them (visual only).</li>"
        "<li>Layers: <b>Controller</b> photo, <b>MIDI</b> picture (alone) and <b>Layout</b> "
        "(the clickable controls).</li>"
        "<li>The emulator also follows the real controller when the Live Monitor is "
        "running.</li></ul>"
        "Open more emulators with <b>View → New Controller Emulator…</b>."
    ),
    "controller-emulator.md",
)

LIVE_MONITOR: HelpEntry = (
    "Live Monitor",
    (
        "Logs every MIDI event from the ticked inputs, with the physical control and the "
        "function the loaded mapping gives it, and makes every layout, the Controller "
        "Images overlay and the emulators react to the real hardware.<br><br>"
        "It starts on its own when a mapping is loaded (⚙ Preferences). To choose ports "
        "yourself: <b>Refresh ports</b>, tick inputs, <b>Start monitoring</b>.<br><br>"
        "To see the LED messages Serato sends back, tick <b>Create virtual monitor</b> and "
        "add <i>DJMidiStudio Monitor</i> as an extra MIDI output in Serato.<br><br>"
        "A press that fires two or more different functions on the same deck is shown in "
        "amber as <b>CONFLICT</b> and counted; Serato's identical repeated triggers are not "
        "conflicts."
    ),
    "live-monitor.md",
)

MIDI_ROUTING: HelpEntry = (
    "MIDI Routing",
    (
        "One-way routes from a MIDI input to a MIDI output.<ol>"
        "<li>Enable <i>MIDI routing policies</i> in ⚙ Preferences (off by default: it "
        "touches real hardware).</li>"
        "<li>Pick a source and a destination, <b>Add route</b>.</li>"
        "<li>Optionally <b>Edit transform…</b> to change the channel, offset the note/CC "
        "or invert the value.</li>"
        "<li><b>Start routing</b>. Only the ports your routes use are opened.</li></ol>"
        "Routes that would loop back on themselves are refused."
    ),
    "midi-routing-and-clock.md",
)

MIDI_CLOCK: HelpEntry = (
    "MIDI Clock",
    (
        "Forwards or generates MIDI Clock (Start/Stop/Continue + 24 ticks per beat).<br><br>"
        "Serato doesn't send MIDI Clock but shares its tempo over Ableton Link: tick "
        "<b>Enable Clock mirror policy</b>, choose <i>Ableton Link (DJ MIDI Studio)</i> as "
        "the source and your hardware's MIDI output as the destination, <b>Add Clock "
        "route</b>, then <b>Start routing</b>. The status line shows "
        "<i>CLOCK ACTIVE</i> while ticks flow."
    ),
    "midi-routing-and-clock.md",
)

METRONOME: HelpEntry = (
    "Metronome",
    (
        "Plays the rows captured in <b>Controller Setup</b> to an output port: the selected "
        "rows or all of them once, or on a loop at the chosen frequency and value. Handy "
        "to blink LEDs, test a mapping, or keep a device awake."
    ),
    "midi-routing-and-clock.md",
)

LIBRARY_FOLDERS: HelpEntry = (
    "Music folders",
    (
        "<b>Add folder…</b>, then <b>Scan &amp; read tags</b>. Later scans only re-read "
        "files that changed; a file that disappears (an unplugged drive) is greyed out as "
        "missing instead of being forgotten. <b>Relink missing…</b> finds where moved files "
        "went (same name and size) and relinks them, playlists included. <b>Health report…</b> "
        "lists files that need attention (corrupt, untagged, no cover, low bitrate). "
        "<b>Analyse BPM/key</b> estimates the tempo and key of tracks whose tags lack "
        "them (needs the optional analysis component); the estimates are amber "
        "suggestions until you apply them from the Track panel.<br><br>"
        "The index stores paths, sizes, dates and a cache of the tags, never the audio. "
        "Serato, Traktor and Rekordbox library files are only ever read."
    ),
    "music-library.md",
)

LIBRARY_TABLE: HelpEntry = (
    "Browse and filter",
    (
        "Click a column header to sort. The search box looks in titles, artists, genres, "
        "BPM, keys and comments; the filters under it combine:"
        "<ul><li><b>Category</b>, <b>Genre</b>, <b>Key</b>.</li>"
        "<li><b>Camelot</b>: tick <i>+ compatible</i> to add the keys that mix "
        "harmonically with it.</li>"
        "<li><b>BPM min – max</b>: both ends included.</li></ul>"
        "An amber <i>? Family / Name</i> category is only a suggestion. "
        "<b>Reset filters</b> clears everything."
    ),
    "music-library.md",
)

LIBRARY_TRACK: HelpEntry = (
    "Track tags",
    (
        "Edit the selected track's tags and click <b>Write tags</b>: only the changed "
        "fields are written, and Serato/Traktor data inside the file is preserved. "
        "<b>Undo</b> writes the old values back.<br><br>"
        "<b>Write tags to selection…</b> writes chosen tags to every selected track as "
        "one undo step, with a progress window you can cancel. "
        "<b>Apply analysis suggestions…</b> writes the selected tracks' estimated BPM/key "
        "into their empty tags, after listing them, as one undo step. "
        "<b>Confirm suggested category</b> turns an amber suggestion into a permanent "
        "alias; <b>Confirm all suggestions</b> does it for every track shown, after listing them. <b>Clean noise frames…</b> lists leftover junk tags and removes them only "
        "after you confirm."
    ),
    "music-library.md",
)

LIBRARY_PREVIEW: HelpEntry = (
    "Audio preview",
    (
        "<b>Play</b> the selected track to check its category or key by ear, without "
        "opening your DJ software. Drag the slider to move through it. While a track "
        "plays, selecting another one switches to it. Tick <b>Start at 30%</b> to skip "
        "the intro. <b>Vol</b> sets the volume (remembered). In the track list, "
        "<b>Space</b> plays/pauses and <b>Left</b>/<b>Right</b> jump 10 s. Tick "
        "<b>Auto-advance</b> to play the next track when one ends. Playback stops "
        "when you leave the tab."
    ),
    "music-library.md",
)

LIBRARY_CATEGORIES: HelpEntry = (
    "Genre categories",
    (
        "Two-level categories (<i>Family / Name</i>, e.g. <i>Tek / PsyTrance</i>), "
        "assigned from folder names and Serato crate names first, then the genre tag. "
        "Create, rename, merge and delete categories here, and add aliases so several "
        "spellings (<i>DnB</i>, <i>D&amp;B</i>, <i>Drum and Bass</i>) mean the same "
        "category."
    ),
    "music-library.md",
)

LIBRARY_DUPLICATES: HelpEntry = (
    "Duplicate tracks",
    (
        "<b>Find duplicates…</b> lists two kinds of groups from the scanned folders:"
        "<ul><li><b>Exact copies</b>: byte-identical files. Only files of the same size are "
        "read and compared by content hash.</li>"
        "<li><b>Same artist + title</b>: tags that match once case, accents, punctuation, "
        "<i>feat.</i> credits and <i>(Original Mix)</i> are ignored. Other versions "
        "(<i>Extended Mix</i>, <i>Radio Edit</i>, remixes) stay distinct. A candidate, not "
        "proof: compare format, size and bitrate.</li></ul>"
        "<b>Reveal in Finder</b> (or double-click) shows a copy. Tick the copies you don't want "
        "and click <b>Move ticked to Trash…</b>: after a confirmation they go to the Trash "
        "(never deleted outright) and show as missing. One copy of each group must stay. "
        "Playlists of this app listing a discarded copy can be pointed at the kept one."
    ),
    "music-library.md",
)

LIBRARY_HEALTH: HelpEntry = (
    "Library health report",
    (
        "<b>Health report…</b> opens every scanned file's header and tags once (read-only, "
        "no audio decoded) and lists:"
        "<ul><li><b>Unreadable / corrupt</b>: the file can't be parsed or opened.</li>"
        "<li><b>Zero length</b>: an empty (0-byte) file or a 0&nbsp;s duration.</li>"
        "<li><b>Empty title</b> / <b>Empty artist</b>: the tag is missing or blank.</li>"
        "<li><b>Missing artwork</b>: no embedded cover picture.</li>"
        "<li><b>Low bitrate</b>: 128&nbsp;kbps or less.</li></ul>"
        "Untick an issue type or type in the filter box to narrow the list. "
        "<b>Show in library</b> (or double-click) selects the track in the table to fix its tags; "
        "<b>Reveal in Finder</b> shows the file. <b>Export CSV…</b> saves the rows shown."
    ),
    "music-library.md",
)

LIBRARY_PLAYLISTS: HelpEntry = (
    "Playlists",
    (
        "<ul><li><b>New from selection</b>: the selected tracks.</li>"
        "<li><b>Auto: sort visible</b>: every visible track, grouped by category, then BPM "
        "range, then key.</li>"
        "<li><b>Auto: match current</b>: the selected track followed by visible tracks "
        "within ±6&nbsp;% BPM and a compatible key.</li>"
        "<li><b>Auto: mix path…</b>: visible tracks chained so each one mixes into the next "
        "(BPM rising, falling or steady), from the selected track, with your BPM tolerance "
        "(±&nbsp;%) and an optional maximum length (both remembered); tracks that don't fit go "
        "to a separate <i>(leftovers)</i> playlist. Only the tracks the current filter shows "
        "are used.</li></ul>"
        "Import Serato crates, Traktor playlists or a Rekordbox USB export (read only); "
        "export to a new Serato crate or Traktor playlist file where you choose."
    ),
    "music-library.md",
)

LIBRARY_SET: HelpEntry = (
    "Set preparation",
    (
        "Build a set by hand: drag tracks from the table into the list (or use <b>Add "
        "selection</b>), then drag them inside the list to reorder. Each track plays once.<br>"
        "The curve shows BPM (blue, left scale) and energy (orange, 1-10, from the Energy tag). "
        "A transition is <span style='color:#d64545'>red</span> and marked ⚠ when the BPM jumps "
        "past your tolerance or the keys clash on the Camelot wheel; dashed grey means a BPM or "
        "key is missing so it can't be checked. Nothing is reordered for you.<br>"
        "The draft is remembered. <b>Save as playlist…</b> stores it as an app playlist; the "
        "export buttons write a new Serato crate or Traktor playlist where you choose."
    ),
    "music-library.md",
)

MAPPING_DIFF: HelpEntry = (
    "Compare mappings",
    (
        "Lists what changed between two mappings by what each trigger <i>does</i>, not "
        "by XML text:<ul>"
        "<li><b>Re-assigned</b>: a trigger now drives a different function.</li>"
        "<li><b>Added</b> / <b>Removed</b>: functions bound only on one side.</li>"
        "<li><b>Changed values</b>: same function, different translation or alias values "
        "(e.g. <i>alias on: 127 → 100</i>).</li>"
        "<li><b>Duplicate count</b>: Serato repeats every trigger (often 10×); a file that "
        "gained or lost copies shows here once, not as many adds or removes.</li></ul>"
        "Functions show their short name (<i>Loop roll</i>); hover a change for the original "
        "Serato tags.<br><br>"
        "Click a row to highlight that control on the layouts and select it in "
        "<b>By Channel</b>. Opened from <b>File → Compare Mapping With…</b> or "
        "<b>File → Compare With Previous Version</b> (the <tt>.bak</tt> kept by the last save)."
    ),
    "mapping-diff.md",
)
