import os

from djmidi.first_run import (
    FirstRunChoices,
    detect_connected_controllers,
    find_serato_mappings,
    should_show_wizard,
)


def test_wizard_only_on_a_genuine_first_launch():
    assert should_show_wizard(preferences_existed=False, wizard_done=False)
    assert not should_show_wizard(preferences_existed=True, wizard_done=False)
    assert not should_show_wizard(preferences_existed=False, wizard_done=True)


def test_detection_merges_ports_per_controller_and_reports_unknown_ports():
    detection = detect_connected_controllers(
        ["PIONEER DDJ-XP2", "PIONEER DDJ-XP2 Out", "IAC Driver Bus 1", "PIONEER DDJ-XP2"]
    )
    assert [c.controller for c in detection.controllers] == ["DDJ-XP2"]
    assert detection.controllers[0].ports == ("PIONEER DDJ-XP2", "PIONEER DDJ-XP2 Out")
    assert detection.controllers[0].score == 100
    assert detection.unmatched_ports == ("IAC Driver Bus 1",)


def test_detection_keeps_several_controllers_in_port_order():
    detection = detect_connected_controllers(["XDJ-XZ", "PIONEER DDJ-XP2"])
    assert [c.controller for c in detection.controllers] == ["XDJ-XZ", "DDJ-XP2"]


def test_detection_with_no_ports_is_empty():
    detection = detect_connected_controllers([])
    assert detection.controllers == () and detection.unmatched_ports == ()


def test_finds_serato_mappings_newest_first_and_only_xml(tmp_path):
    folder = tmp_path / "Music" / "_Serato_" / "MIDI" / "Xml"
    folder.mkdir(parents=True)
    old, new = folder / "old.xml", folder / "New.XML"
    for index, path in enumerate((old, new)):
        path.write_text("<midi/>", encoding="utf-8")
        os.utime(path, (1_000 + index, 1_000 + index))
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    (folder / "._old.xml").write_text("x", encoding="utf-8")
    (folder / "sub.xml").mkdir()
    before = sorted(p.name for p in folder.iterdir())

    found = find_serato_mappings(tmp_path)

    assert [c.path for c in found] == [new, old]
    assert sorted(p.name for p in folder.iterdir()) == before  # read-only


def test_missing_serato_folder_finds_nothing(tmp_path):
    assert find_serato_mappings(tmp_path) == []


def test_mapping_list_is_capped(tmp_path):
    folder = tmp_path / "Music" / "_Serato_" / "MIDI" / "Xml"
    folder.mkdir(parents=True)
    for index in range(5):
        (folder / f"m{index}.xml").write_text("<midi/>", encoding="utf-8")
    assert len(find_serato_mappings(tmp_path, limit=3)) == 3


def test_default_choices_change_nothing():
    choices = FirstRunChoices()
    assert choices.controller is None and choices.mapping is None and not choices.record_sync_set
