from __future__ import annotations

import copy
import shutil
from pathlib import Path

from PySide6.QtWidgets import QApplication

from djmidi import file_locations
from djmidi.exporter import write_file
from djmidi.gui.main_window import MainWindow
from djmidi.gui.mapping_diff_dialog import ENTRY_ROLE, MappingDiffDialog, physical_names
from djmidi.mapping_diff import diff_configs
from djmidi.parser import parse_file

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _retag(config, channel: str, control: str, tag: str):
    changed = copy.deepcopy(config)
    for item in changed.controls:
        if (item.channel, item.control) == (channel, control):
            for userio in item.userios:
                for element in userio.mappings:
                    element.tag = tag
    return changed


def _window_with_backup(tmp_path) -> tuple[MainWindow, Path]:
    mapping = tmp_path / "mapping.xml"
    shutil.copy(FIXTURE, mapping)
    window = MainWindow()
    window.show()
    window.config = parse_file(mapping)
    window.current_path = mapping
    window._load_tree()
    window._refresh_file_actions()
    QApplication.processEvents()
    return window, mapping


def test_dialog_groups_entries_by_kind_with_physical_names():
    old = parse_file(FIXTURE)
    diff = diff_configs(old, _retag(old, "14", "65", "play"))
    dialog = MappingDiffDialog(diff, "a.xml", "b.xml")
    try:
        assert dialog.tree.topLevelItemCount() == 1
        assert dialog.tree.topLevelItem(0).text(0).startswith("Re-assigned (")
        entries = [item.data(0, ENTRY_ROLE) for item in dialog.entry_items()]
        assert {entry.trigger for entry in entries} == {("14", "Note On", "65")}
        names = physical_names(entries[0])
        assert names, "the fixture's triggers are all catalogued"
        assert dialog.entry_items()[0].text(0) == names
    finally:
        dialog.close()


def test_compare_actions_follow_the_backup(tmp_path):
    window, mapping = _window_with_backup(tmp_path)
    try:
        assert window._compare_action.isEnabled()
        assert not window._compare_backup_action.isEnabled()
        file_locations.backup_path(mapping).write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
        window._refresh_file_actions()
        assert window._compare_backup_action.isEnabled()
    finally:
        window.close()


def test_compare_with_previous_version_lists_and_highlights(tmp_path):
    window, mapping = _window_with_backup(tmp_path)
    try:
        write_file(_retag(window.config, "14", "65", "play"), file_locations.backup_path(mapping))
        window._refresh_file_actions()
        window._on_compare_with_backup()
        dialog = window._diff_dialog
        assert dialog is not None and dialog.isVisible()
        items = dialog.entry_items()
        entries = [item.data(0, ENTRY_ROLE) for item in items]
        assert {(entry.kind, entry.trigger) for entry in entries} == {("reassigned", ("14", "Note On", "65"))}
        assert all(entry.old_functions[0].startswith("play") for entry in entries)
        dialog.tree.setCurrentItem(items[0])
        QApplication.processEvents()
        assert window.layout_view._selected_keys
        assert window.left_tabs.currentIndex() == window._tab_indexes["channel"]
    finally:
        window.close()


def test_identical_file_reports_no_difference(tmp_path):
    window, _mapping = _window_with_backup(tmp_path)
    try:
        dialog = window._compare_with_path(FIXTURE)
        assert dialog is not None
        assert dialog.diff.is_empty
        assert dialog.entry_items() == []
    finally:
        window.close()
