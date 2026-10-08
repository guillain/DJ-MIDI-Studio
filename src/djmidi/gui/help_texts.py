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
        "<b>File → Open…</b>."
    ),
    "mapping-editor.md",
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
        "(duplicate copies are info only: they are expected). <b>File → Save</b> shows the "
        "exact changes before writing, keeps a backup, and <b>File → Rollback Last Save</b> "
        "restores it."
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
        "add <i>DJMidiStudio Monitor</i> as an extra MIDI output in Serato."
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
        "missing instead of being forgotten.<br><br>"
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
        "<b>Confirm suggested category</b> turns an amber suggestion into a permanent "
        "alias. <b>Clean noise frames…</b> lists leftover junk tags and removes them only "
        "after you confirm."
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

LIBRARY_PLAYLISTS: HelpEntry = (
    "Playlists",
    (
        "<ul><li><b>New from selection</b>: the selected tracks.</li>"
        "<li><b>Auto: sort visible</b>: every visible track, grouped by category, then BPM "
        "range, then key.</li>"
        "<li><b>Auto: match current</b>: the selected track followed by visible tracks "
        "within ±6&nbsp;% BPM and a compatible key.</li></ul>"
        "Import Serato crates, Traktor playlists or a Rekordbox USB export (read only); "
        "export to a new Serato crate or Traktor playlist file where you choose."
    ),
    "music-library.md",
)
