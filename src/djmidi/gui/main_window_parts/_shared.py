"""Constants and helpers shared by MainWindow and its mixins (issue #429)."""

from __future__ import annotations

import logging

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
)
from PySide6.QtGui import (
    QColor,
)
from PySide6.QtWidgets import (
    QTreeView,
)

from djmidi.gui.translation import translator

_SEVERITY_COLORS = {
    "error": QColor(255, 200, 200),
    "warning": QColor(255, 235, 180),
    "info": QColor(225, 225, 225),
}

# The official docs catalog.py was transcribed from (see controllers/README.md).
_REFERENCE_LINKS = [
    ("Serato MIDI Mapping Guide", "https://support.serato.com/hc/en-us/articles/209377487-MIDI-mapping-with-Serato-DJ-Pro"),
    (
        "XDJ-XZ MIDI Message List (PDF)",
        "https://downloads.support.alphatheta.com/software_info/all-in-one-dj-systems/XDJ-XZ/XDJ-XZ_MIDI_Message_List_E3.pdf",
    ),
    (
        "DDJ-XP2 MIDI Message List (PDF)",
        "https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-XP2/DDJ-XP2_MIDI_Message_List_E1.pdf",
    ),
    (
        "Ableton Link documentation",
        "https://www.ableton.com/en/link/",
    ),
    (
        "DJ TechTools: Serato external sync overview",
        "https://djtechtools.com/2018/06/27/serato-dj-pro-four-ways-for-syncing-with-external-gear/",
    ),
]

_RECENT_SETTINGS_KEY = "files/recent_mappings"
_LAST_DIR_SETTINGS_KEY = "files/last_mapping_dir"
_LAST_MAPPING_SETTINGS_KEY = "files/last_mapping"
_LAST_SOFTWARE_SETTINGS_KEY = "files/last_mapping_software"
_LAST_DRAFT_SETTINGS_KEY = "files/last_draft"
# Sync status-bar summaries come from Qt-free controller_sync (issue #313).
_sync_translate = translator("ControllerSync")
# Lets controllers' MIDI ports settle before the launch-time Sync.
_STARTUP_SYNC_DELAY_MS = 1500
# Ready-for-live findings come from Qt-free live_ready (issue #319).
_live_ready_translate = translator("LiveReady")
# Macro results come from Qt-free midi_macros (issue #319).
_macro_translate = translator("MidiMacros")
# Validation messages and detection reasons come from Qt-free modules (issue #326).
_validator_translate = translator("Validator")
_detection_translate = translator("IntegrationDetection")
# Startup update check (issue #193): after the window is up, at most once a day.
_STARTUP_UPDATE_CHECK_DELAY_MS = 3000
# After launch Sync and the update check: offer library profiles for the
# controllers plugged in.
_STARTUP_LIBRARY_SUGGEST_DELAY_MS = 4500
_DISMISSED_LIBRARY_PROFILES_KEY = "library/dismissed_profiles"
_LAST_UPDATE_CHECK_SETTINGS_KEY = "updates/last_check"
_LAST_ANNOUNCED_VERSION_SETTINGS_KEY = "updates/last_announced_version"
# How often output ports are listed to spot a controller being plugged in.
_PLUG_IN_POLL_MS = 2000

# Menu titles, translated where the Help menu is built (issue #337).
_LOCAL_HELP_DOCUMENTS = [
    (QT_TRANSLATE_NOOP("MainWindow", "Documentation Home"), "docs/README.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "Features Overview"), "docs/enduser/README.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "User Guide"), "docs/enduser/user-guide.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "Feature Pages"), "docs/enduser/features/README.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "End-to-End Examples"), "docs/enduser/examples.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "Supported Controllers"), "docs/enduser/controller-profiles.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "MIDI Clock Compatibility"), "docs/enduser/midi-clock-compatibility.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "Developer Documentation"), "docs/developer/README.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "Architecture"), "docs/developer/design/architecture.md"),
    (QT_TRANSLATE_NOOP("MainWindow", "Build and Release"), "docs/developer/cicd/build-and-release.md"),
]

_LOCAL_CONTROLLER_DOCUMENTS = [
    (QT_TRANSLATE_NOOP("MainWindow", "Controller documentation index"), "controllers/README.md"),
    ("DDJ-XP2 MIDI Message List", "controllers/hardware/pioneer/DDJ-XP2/ddj-xp2-midi-message-list-e1.pdf"),
    ("XDJ-XZ MIDI Message List", "controllers/hardware/pioneer/XDJ-XZ/xdj-xz-midi-message-list-e3.pdf"),
    ("DDJ-1000 MIDI Message List", "controllers/hardware/pioneer/DDJ-1000/ddj-1000-midi-message-list-e1.pdf"),
    ("DDJ-FLX10 MIDI Message List", "controllers/hardware/pioneer/DDJ-FLX10/ddj-flx10-midi-message-list-e1.pdf"),
    ("DDJ-FLX4 MIDI Message List", "controllers/hardware/pioneer/DDJ-FLX4/ddj-flx4-midi-message-list-e1.pdf"),
    ("DDJ-REV1 MIDI Message List", "controllers/hardware/pioneer/DDJ-REV1/ddj-rev1-midi-message-list-e1.pdf"),
    ("Numark Mixtrack Pro FX User Guide", "controllers/hardware/numark/Mixtrack-Pro-FX/numark-mixtrack-pro-fx-user-guide-v1.2.pdf"),
    (
        "Hercules DJControl Inpulse 500 Product Sheet",
        "controllers/hardware/hercules/DJControl-Inpulse-500/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf",
    ),
]


_LOGGER = logging.getLogger("djmidi.gui.main_window")


def _human_size(size: int) -> str:
    # Localized units (Ko/Mo/Go in French), like the duplicates window's.
    from djmidi.gui.duplicates_dialog import format_size

    return format_size(size)

# Performance Mode: how much to shrink the tree pane (never fully to 0 -- the
# pair splitters are non-collapsible by design) and how much to enlarge the
# schematic layout glyphs.
_PERFORMANCE_TREE_RATIO = 0.03
_PERFORMANCE_ZOOM_FACTOR = 1.6


def _refresh_tree_row_layout(view: QTreeView) -> None:
    """Force Qt to repaint every currently *visible* branch row under
    `view`'s current stylesheet.

    `QTreeView.setStyleSheet()` alone leaves a row's already-laid-out area
    showing whatever background was cached the *last* time that row's
    expand state changed -- found on By Controller after a live theme
    switch: rows that stay collapsed (`_apply_controller_expand_state`
    only expands a section with a used leaf) rendered with the *previous*
    theme's dark background indefinitely, while rows that had just been
    freshly expanded/collapsed painted correctly. By Channel/Deck never
    showed this because `expandToDepth(0)` touches every top-level row's
    expand state once at construction, well before any later theme switch
    -- by then Qt has nothing stale left to redraw for those specific
    rows. Toggling a row's expanded state off and immediately back to
    whatever it already was is a UI no-op but forces the repaint.

    Deliberately bounded to the viewport rather than a recursive full-model
    walk (which this started as): a row that isn't currently painted has
    nothing stale to fix -- scrolling to it afterwards already repaints
    correctly on its own (confirmed: a live theme switch followed by a
    scroll renders every newly-revealed row in the *current* theme, no
    staleness). Bounding the cost to "however many rows are on screen"
    also matters for a reason unrelated to correctness: theme.signals
    .themeChanged is a persistent module-level signal, and a tree whose
    widget hasn't actually been destroyed yet (Qt's own deferred-deletion
    timing, not a bug in this codebase) keeps costing this function on
    every future theme switch for as long as it lingers -- a recursive
    whole-model walk turned that from negligible into something that
    visibly compounded across a long test run (or, in principle, a long
    real session with several mapping reloads)."""
    model = view.model()
    if model is None:
        return
    viewport_bottom = view.viewport().rect().bottom()
    index = view.indexAt(view.viewport().rect().topLeft())
    while index.isValid() and view.visualRect(index).top() <= viewport_bottom:
        if model.hasChildren(index):
            was_expanded = view.isExpanded(index)
            view.setExpanded(index, not was_expanded)
            view.setExpanded(index, was_expanded)
        index = view.indexBelow(index)


# A mapping column narrower than this truncates every row ("ch1 N..."); the
# column row scrolls sideways instead (see splitter_utils.scrollable_columns).
MAPPING_COLUMN_MIN_WIDTH = 220

