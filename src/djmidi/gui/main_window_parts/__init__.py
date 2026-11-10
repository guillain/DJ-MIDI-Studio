"""MainWindow split into focused mixins (issue #429)."""

from djmidi.gui.main_window_parts.docks import DockWindowsMixin
from djmidi.gui.main_window_parts.files import MappingFilesMixin
from djmidi.gui.main_window_parts.live_midi import LiveMidiMixin
from djmidi.gui.main_window_parts.macros import MacrosMixin
from djmidi.gui.main_window_parts.mapping_views import MappingViewsMixin
from djmidi.gui.main_window_parts.tools import ToolsMixin

__all__ = ["DockWindowsMixin", "LiveMidiMixin", "MacrosMixin", "MappingFilesMixin", "MappingViewsMixin", "ToolsMixin"]
