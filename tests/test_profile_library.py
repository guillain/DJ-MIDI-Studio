"""The bundled controller profile library (profiles built from rekordbox's
own MIDI mappings, installed on demand). The CSVs here are synthetic, in
the shape rekordbox ships (see software/rekordbox/README.md)."""

import json

import pytest

from djmidi import catalog
from djmidi.catalog.library import (
    LIBRARY_DIR,
    REKORDBOX_LICENSE,
    build_rekordbox_profiles,
    device_name,
    install_library_profile,
    list_library_profiles,
    write_library,
)
from djmidi.catalog.profile import USER_PLUGIN_PREFIX, load_controller_profile
from djmidi.gui.layout import build_layout

HEADER = "#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment"
ROWS = (
    "# Deck,,,,,,,,,,,,,,",
    "PlayPause,PlayPause,Button,900B,0,1,,,,,,,,,",
    "Cue,Cue,Button,900C,0,1,,,,,,,,,",
    "Sync,Sync,Button,9058,0,1,,,,,,,,,",
    "Master,Sync+Shift,Button,905C,0,1,,,,,,,,,",
    "TempoSlider,TempoSlider,KnobSliderHiRes,B000,0,1,,,,,,,,,",
    "# Performance,,,,,,,,,,,,,,",
    "PAD1_PadMode1,PAD1_PadMode1,Pad,9700,0,2,,,,,,,,,",
    "PAD1_PadMode2,PAD1_PadMode2,Pad,9710,0,2,,,,,,,,,",
    "PAD2_PadMode1,PAD2_PadMode1,Pad,9701,0,2,,,,,,,,,",
)


def _csv(device: str, rows=ROWS) -> str:
    return "\n".join((f"@file,1,{device}", HEADER, *rows))


def test_device_names_drop_the_vendor_prefix_and_port_variant():
    assert device_name("PIONEER DDJ-SX 2IN2OUT") == "DDJ-SX"
    assert device_name("Pioneer DJ XDJ-RR MIDI") == "XDJ-RR"
    assert device_name("DDJ-SB MIDI") == "DDJ-SB"
    assert device_name("XDJ-XZ (2)") == "XDJ-XZ"
    assert device_name("EUPHONIA") == "EUPHONIA"


def test_build_merges_port_variants_and_skips_built_ins_and_tiny_files():
    texts = [
        _csv("PIONEER DDJ-TEST"),
        _csv("DDJ-TEST MIDI"),  # same device, another port name
        _csv("DDJ-XP2"),  # a built-in
        _csv("EUPHONIA"),
        _csv("DDJ-TINY", ROWS[:3]),  # 2 entries < MIN_ENTRIES
    ]
    definitions = build_rekordbox_profiles(texts, skip_names=["DDJ-XP2"])
    assert [d.name for d in definitions] == ["DDJ-TEST", "EUPHONIA"]
    test = definitions[0]
    assert test.port_names == ("PIONEER DDJ-TEST", "DDJ-TEST MIDI")
    assert test.plugin_id == USER_PLUGIN_PREFIX + "ddj-test"
    assert (test.manufacturer, definitions[1].manufacturer) == ("Pioneer DJ", "AlphaTheta")
    names = {(e.section, e.name): e.channels for e in test.static_entries}
    assert names[("Deck", "Sync +SHIFT")] == ("1", "2")
    assert ("PAD", "Pad 1 (PadMode2)") in names
    assert all("Tempo" not in name for _section, name in names)  # continuous controls left out


def test_written_library_lists_loads_and_drops_stale_files(tmp_path):
    definitions = build_rekordbox_profiles([_csv("DDJ-TEST"), _csv("DDJ-OTHER")])
    (tmp_path / "gone.json").write_text("{}", encoding="utf-8")
    write_library(definitions, tmp_path)
    assert sorted(path.name for path in tmp_path.glob("*.json")) == ["ddj-other.json", "ddj-test.json"]
    raw = json.loads((tmp_path / "ddj-test.json").read_text(encoding="utf-8"))
    assert raw["manifest"]["license"] == REKORDBOX_LICENSE
    profiles = list_library_profiles(tmp_path)
    assert [(p.name, p.vendor, p.source) for p in profiles] == [
        ("DDJ-OTHER", "Pioneer DJ", "rekordbox"),
        ("DDJ-TEST", "Pioneer DJ", "rekordbox"),
    ]
    assert profiles[1].entries == len(definitions[1].static_entries)
    assert not profiles[1].is_installed and not profiles[1].is_built_in


def test_install_copies_registers_and_groups_pads(tmp_path):
    write_library(build_rekordbox_profiles([_csv("DDJ-TEST")]), tmp_path / "library")
    profile = list_library_profiles(tmp_path / "library")[0]
    definition = install_library_profile(profile, tmp_path / "Controllers")
    assert (tmp_path / "Controllers" / "ddj-test.json").is_file()
    assert "DDJ-TEST" in catalog.CONTROLLER_NAMES and profile.is_installed
    assert catalog.detect_controller("PIONEER DDJ-TEST")[0].controller.name == "DDJ-TEST"
    cells = [cell.label for cell in build_layout(definition.name) if cell.section == "PAD"]
    assert cells == ["Pad 1", "Pad 2"]  # every mode of a pad on one cell, in pad order
    install_library_profile(profile, tmp_path / "Controllers")  # reinstalling is fine


def test_install_refuses_a_built_in_name(tmp_path):
    write_library(build_rekordbox_profiles([_csv("DDJ-XP2")]), tmp_path)
    profile = list_library_profiles(tmp_path)[0]
    assert profile.is_built_in
    with pytest.raises(ValueError, match="built-in"):
        install_library_profile(profile, tmp_path / "Controllers")


def test_every_bundled_library_profile_loads_cleanly():
    profiles = list_library_profiles(LIBRARY_DIR)
    assert len(profiles) >= 40
    for profile in profiles:
        assert not profile.is_built_in, profile.name
        definition = load_controller_profile(profile.path, replace=True)
        assert definition.plugin_id.startswith(USER_PLUGIN_PREFIX)
        names = [(entry.section, entry.name) for entry in definition.static_entries]
        assert len(names) == len(set(names)), profile.name
        keys = [cell.key for cell in build_layout(definition.name)]
        assert len(keys) == len(set(keys)), profile.name


# --- the dialog ---------------------------------------------------------------


def test_dialog_filters_installs_and_marks_installed(tmp_path):
    from djmidi.gui.profile_library_dialog import ProfileLibraryDialog

    write_library(build_rekordbox_profiles([_csv("DDJ-TEST"), _csv("PIONEER DDJ-OTHER"), _csv("DDJ-XP2")]), tmp_path)
    dialog = ProfileLibraryDialog(list_library_profiles(tmp_path), tmp_path / "Controllers")
    rows = [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())]
    assert rows == ["DDJ-OTHER", "DDJ-TEST", "DDJ-XP2"]
    assert dialog.table.item(2, 4).text() == "Built-in"
    dialog.filter_edit.setText("pioneer ddj other")  # port names match too
    assert [dialog.table.isRowHidden(row) for row in range(3)] == [False, True, True]
    dialog.filter_edit.clear()
    dialog.select_profile("DDJ-XP2")
    assert not dialog.install_button.isEnabled()
    installed = []
    dialog.installed.connect(installed.append)
    dialog.select_profile("DDJ-TEST")
    assert dialog.install_button.isEnabled()
    assert dialog.install_selected() == ["DDJ-TEST"] == installed
    assert dialog.table.item(1, 4).text() == "Installed"
    assert dialog.status.text() == "Installed: DDJ-TEST"


def test_main_window_shows_an_installed_library_profile_at_once(tmp_path, monkeypatch):
    from djmidi.gui import main_window as main_window_module
    from djmidi.gui.main_window import MainWindow

    write_library(build_rekordbox_profiles([_csv("DDJ-TEST")]), tmp_path)
    monkeypatch.setattr(main_window_module, "list_library_profiles", lambda: list_library_profiles(tmp_path))
    window = MainWindow()
    try:
        dialog = window.open_profile_library()
        dialog.select_profile("DDJ-TEST")
        dialog.install_selected()
        tabs = window.layout_view._controller_tabs
        assert "DDJ-TEST" in [tabs.tabText(index) for index in range(tabs.count())]
        assert window.statusBar().currentMessage() == "'DDJ-TEST' installed from the profile library."
        dialog.close()
    finally:
        window.close()


# --- suggestion for connected controllers, uninstall -------------------------


def _library(tmp_path, *devices):
    write_library(build_rekordbox_profiles([_csv(device) for device in devices], skip_names=["DDJ-XP2"]), tmp_path)
    return list_library_profiles(tmp_path)


def test_connected_profiles_match_whole_names_and_skip_covered_ports(tmp_path):
    from djmidi.catalog.library import connected_library_profiles

    profiles = _library(tmp_path, "PIONEER DDJ-SB", "DDJ-SB2", "DDJ-TEST MIDI")
    ports = ["PIONEER DDJ-SB2", "DDJ-TEST MIDI 1", "PIONEER DDJ-XP2", "IAC Driver Bus 1"]
    found = connected_library_profiles(ports, profiles)
    assert [(profile.name, port) for profile, port in found] == [
        ("DDJ-SB2", "PIONEER DDJ-SB2"),  # not DDJ-SB: "DDJ-SB" isn't a whole word of "DDJ-SB2"
        ("DDJ-TEST", "DDJ-TEST MIDI 1"),
    ]
    install_library_profile(found[1][0], tmp_path / "Controllers")
    assert [profile.name for profile, _port in connected_library_profiles(ports, list_library_profiles(tmp_path))] == [
        "DDJ-SB2"
    ]


def test_uninstall_removes_the_file_and_the_controller(tmp_path):
    from djmidi.catalog.profile import uninstall_user_profile

    profile = _library(tmp_path / "library", "DDJ-TEST")[0]
    install_library_profile(profile, tmp_path / "Controllers")
    assert uninstall_user_profile("DDJ-TEST", tmp_path / "Controllers") == [tmp_path / "Controllers" / "ddj-test.json"]
    assert "DDJ-TEST" not in catalog.CONTROLLER_NAMES and not profile.is_installed
    with pytest.raises(ValueError, match="built-in"):
        uninstall_user_profile("DDJ-XP2", tmp_path / "Controllers")


def test_dialog_uninstalls_installed_profiles(tmp_path):
    from djmidi.gui.profile_library_dialog import ProfileLibraryDialog

    profiles = _library(tmp_path / "library", "DDJ-TEST")
    dialog = ProfileLibraryDialog(profiles, tmp_path / "Controllers")
    dialog.select_profile("DDJ-TEST")
    assert not dialog.uninstall_button.isEnabled()
    dialog.install_selected()
    dialog.select_profile("DDJ-TEST")
    assert dialog.uninstall_button.isEnabled()
    removed = []
    dialog.uninstalled.connect(removed.append)
    assert dialog.uninstall_selected() == ["DDJ-TEST"] == removed
    assert dialog.table.item(0, 4).text() == "" and dialog.status.text() == "Uninstalled: DDJ-TEST"


def test_main_window_offers_connected_library_profiles_once(tmp_path, monkeypatch):
    from djmidi.gui import main_window as main_window_module
    from djmidi.gui.main_window import MainWindow

    _library(tmp_path, "DDJ-TEST", "DDJ-OTHER")
    monkeypatch.setattr(main_window_module, "list_library_profiles", lambda: list_library_profiles(tmp_path))
    window = MainWindow()
    try:
        questions = []
        ports = ["DDJ-TEST", "DDJ-OTHER 2"]
        declined = window._suggest_library_profiles(ports, ask=lambda text: questions.append(text) or False)
        assert declined == [] and "DDJ-TEST (DDJ-TEST)" in questions[0] and "DDJ-OTHER" in questions[0]
        assert window._suggest_library_profiles(ports, ask=lambda text: True) == []  # "No" is remembered
        window._session_dismissed_profiles = set()
        assert window._suggest_library_profiles(ports, ask=lambda text: True) == ["DDJ-TEST", "DDJ-OTHER"]
        tabs = window.layout_view._controller_tabs
        assert "DDJ-OTHER" in [tabs.tabText(index) for index in range(tabs.count())]
        assert window._suggest_library_profiles(ports, ask=lambda text: True) == []  # installed now

        dialog = window.open_profile_library()
        dialog.select_profile("DDJ-OTHER")
        dialog.uninstall_selected()
        assert "DDJ-OTHER" not in [tabs.tabText(index) for index in range(tabs.count())]
        assert window.statusBar().currentMessage() == "'DDJ-OTHER' uninstalled."
        dialog.close()
    finally:
        window.close()


# --- profiles from Mixxx's mappings -------------------------------------------

MIXXX = """<?xml version='1.0' encoding='utf-8'?>
<MixxxControllerPreset schemaVersion="1" mixxxVersion="2.3.0+">
  <info><name>{name}</name></info>
  <controller id="T"><controls>
{controls}
  </controls></controller>
</MixxxControllerPreset>"""
_BINDING = "<control><group>{group}</group><key>{key}</key><status>{status}</status><midino>{no}</midino></control>"


def _mixxx(name, bindings):
    controls = "\n".join(_BINDING.format(group=g, key=k, status=s, no=n) for g, k, s, n in bindings)
    return MIXXX.format(name=name, controls=controls)


BINDINGS = [
    ("[Channel1]", "play", "0x90", "0x01"),
    ("[Channel2]", "play", "0x91", "0x01"),
    ("[Channel1]", "Ctrl.deck[0].cueButton.input", "0x90", "0x02"),
    ("[Channel1]", "hotcue_1_activate", "0x94", "0x10"),
    ("[Channel1]", "hotcue_1_activate", "0x94", "0x18"),  # its SHIFT layer, same key
    ("[Master]", "crossfader", "0xB0", "0x08"),  # a CC: not a button
    ("[Library]", "MoveDown", "0x9F", "0x05"),
    ("[Sampler1]", "cue_gotoandplay", "0x9A", "0x00"),
]


def test_mixxx_names_and_sections():
    from djmidi.catalog.library import mixxx_control_name

    assert mixxx_control_name("hotcue_1_activate") == "HOTCUE 1 ACTIVATE"
    assert mixxx_control_name("Ctrl.deck[0].playButton.input") == "PLAY BUTTON"
    assert mixxx_control_name("Ctrl.shift") == "SHIFT"


def test_build_mixxx_profiles_keeps_buttons_and_skips_known_devices():
    from djmidi.catalog.library import build_mixxx_profiles

    texts = [
        _mixxx("Acme Mixmaster 4", BINDINGS),
        _mixxx("Acme Mixmaster 4", BINDINGS[:6]),  # a second mapping of one device: first wins
        _mixxx("Pioneer DDJ-TEST", BINDINGS),  # the rekordbox side covers it
        _mixxx("Acme Tiny", BINDINGS[:2]),  # under MIN_ENTRIES
        _mixxx("Acme Beta (unfinished)", BINDINGS),
    ]
    (definition,) = build_mixxx_profiles(texts, skip_names=["DDJ-TEST"])
    assert (definition.name, definition.manufacturer, definition.port_names) == (
        "Acme Mixmaster 4", "Acme", ("Mixmaster 4",),
    )
    names = {(e.section, e.name): (e.channels, e.data1) for e in definition.static_entries}
    assert names[("DECK", "PLAY")] == (("1", "2"), "1")
    assert names[("DECK", "CUE BUTTON")] == (("1",), "2")
    assert names[("DECK", "HOTCUE 1 ACTIVATE")] == (("5",), "16")
    assert names[("DECK", "HOTCUE 1 ACTIVATE #2")] == (("5",), "24")
    assert ("BROWSE", "MOVE DOWN") in names and ("SAMPLER", "CUE GOTOANDPLAY") in names
    assert not any("CROSSFADER" in name for _section, name in names)


def test_mixxx_library_profiles_list_with_their_source(tmp_path):
    from djmidi.catalog.library import MIXXX_LICENSE, SOURCE_MIXXX, build_mixxx_profiles
    from djmidi.gui.profile_library_dialog import ProfileLibraryDialog

    write_library(build_mixxx_profiles([_mixxx("Acme Mixmaster 4", BINDINGS)]), tmp_path / "mixxx", SOURCE_MIXXX)
    write_library(build_rekordbox_profiles([_csv("DDJ-TEST")]), tmp_path / "rekordbox")
    raw = json.loads((tmp_path / "mixxx" / "acme-mixmaster-4.json").read_text(encoding="utf-8"))
    assert raw["manifest"]["license"] == MIXXX_LICENSE
    profiles = list_library_profiles(tmp_path)
    assert [(p.name, p.source) for p in profiles] == [("Acme Mixmaster 4", "mixxx"), ("DDJ-TEST", "rekordbox")]
    dialog = ProfileLibraryDialog(profiles, tmp_path / "Controllers")
    assert [dialog.table.item(row, 2).text() for row in range(2)] == ["Mixxx", "rekordbox"]
