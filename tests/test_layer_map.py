"""Layered mapping overview (issue #253): the Qt-free resolution in
gui/layer_map.py against the real fixture, plus the View -> Layer Map
dialog."""

from pathlib import Path

from PySide6.QtCore import Qt

from djmidi import catalog
from djmidi.gui import layer_map as lm
from djmidi.gui.layer_map_dialog import (
    ALL_SECTIONS,
    FREE_TEXT,
    NOT_APPLICABLE,
    LayerMapDialog,
)
from djmidi.gui.main_window import MainWindow
from djmidi.model import Control, MappingElement, MidiConfig, UserIO
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _config() -> MidiConfig:
    return parse_file(FIXTURE)


def _info(name: str, section: str = "PAD") -> catalog.ControlInfo:
    return catalog.ControlInfo("X", section, name, "NOTE", ("1",), "0")


def _row(layer_map: lm.LayerMap, control: str, section: str = "PAD") -> lm.LayerRow:
    return next(row for row in layer_map.rows if row.control == control and row.section == section)


def test_layer_of_reads_bank_shift_and_qualifiers_from_the_name():
    assert lm.layer_of(_info("Deck 1 Pad 3 (PAD MODE 2)")) == "PAD MODE 2"
    assert lm.layer_of(_info("Deck 1 Pad 3 (PAD MODE 2) +SHIFT")) == "PAD MODE 2 + SHIFT"
    assert lm.layer_of(_info("Deck 4 Pad 8 (PAD MODE 7) (+SHIFT)")) == "PAD MODE 7 + SHIFT"
    assert lm.layer_of(_info("Deck 1 Performance Pad 1 (HOT CUE mode)")) == "HOT CUE mode"
    assert lm.layer_of(_info("Pad 16 (SCENE 4)")) == "SCENE 4"
    assert lm.layer_of(_info("Deck 1 Pad 1")) == lm.NORMAL
    assert lm.layer_of(_info("QUANTIZE", "DECK")) == lm.NORMAL
    assert lm.layer_of(_info("QUANTIZE (+SHIFT)", "DECK")) == lm.SHIFT
    assert lm.layer_of(_info("Rotary Selector (+SHIFT press)", "BROWSE")) == lm.SHIFT
    assert lm.layer_of(_info("SYNC (long press)", "DECK")) == "long press"
    assert lm.layer_of(_info("HOT CUE (direct button, +SHIFT)", "DECK")) == "direct button + SHIFT"


def test_a_key_shift_pad_bank_is_not_a_shift_layer():
    # DDJ-1000's "KEY SHIFT" pad mode carries "SHIFT" in its own name.
    plain = _info("Deck 1 Pad 1 (KEY SHIFT, PAGE 1)")
    shifted = _info("Deck 1 Pad 1 (KEY SHIFT, PAGE 1) (+SHIFT)")
    assert not lm.is_shift(plain)
    assert lm.layer_of(plain) == "KEY SHIFT, PAGE 1"
    assert lm.layer_of(shifted) == "KEY SHIFT, PAGE 1 + SHIFT"


def test_ddj_xp2_layers_are_normal_shift_then_every_pad_bank():
    layer_map = lm.build_layer_map(_config(), "DDJ-XP2")
    assert layer_map.layers[:4] == (lm.NORMAL, lm.SHIFT, "PAD MODE 1", "PAD MODE 1 + SHIFT")
    assert layer_map.layers[-1] == "PAD MODE 8 + SHIFT"
    assert len(layer_map.layers) == 2 + 16
    # Pads lead, by number, then the catalog's section order.
    assert [row.control for row in layer_map.rows[:3]] == ["Pad 1", "Pad 2", "Pad 3"]
    assert layer_map.rows[16].section == "DECK"
    # LED-feedback entries are no place for a new function.
    assert "MIDI-OUT" not in layer_map.sections()


def test_mapped_and_free_cells_on_the_real_fixture():
    layer_map = lm.build_layer_map(_config(), "DDJ-XP2")
    pad = _row(layer_map, "Pad 1")
    mapped = pad.cells["PAD MODE 5"]
    assert mapped.status == lm.STATUS_MAPPED
    assert mapped.functions == ("Codfather ST · slot 0 (D1, D2, D3, D4)",)
    assert mapped.free_triggers == ()
    free = pad.cells["PAD MODE 1"]
    assert free.status == lm.STATUS_FREE
    assert free.functions == ()
    assert len(free.free_triggers) == 4  # one per deck channel
    # A button has no pad bank.
    quantize = _row(layer_map, "QUANTIZE", "DECK")
    assert set(quantize.cells) == {lm.NORMAL, lm.SHIFT}
    assert layer_map.count(lm.STATUS_MAPPED) == 16


def test_a_combination_mapped_on_some_decks_only_is_partial():
    layer_map = lm.build_layer_map(_config(), "XDJ-XZ")
    cell = _row(layer_map, "Pad 1").cells["EXTENSION1 mode"]
    assert cell.status == lm.STATUS_PARTIAL
    assert cell.functions == ("Codfather ST · slot 0 (D1)",)
    assert 0 < len(cell.free_triggers) < len(cell.triggers)


def test_no_mapping_leaves_every_combination_free():
    layer_map = lm.build_layer_map(None, "Korg nanoPAD2")
    assert layer_map.layers == ("SCENE 1", "SCENE 2", "SCENE 3", "SCENE 4")
    assert layer_map.count(lm.STATUS_FREE) == 64
    assert layer_map.count(lm.STATUS_MAPPED) == 0


def test_output_elements_do_not_occupy_a_layer():
    output_only = Control(
        channel="8",
        event_type="Note On",
        control="0",
        userios=[UserIO(event="output", mappings=[MappingElement(tag="play", deck_id="0")])],
    )
    layer_map = lm.build_layer_map(MidiConfig(controls=[output_only]), "DDJ-XP2")
    assert layer_map.count(lm.STATUS_MAPPED) == 0


def test_describe_trigger():
    assert lm.describe_trigger(("9", "Note On", "18")) == "ch 9 · Note 18"
    assert lm.describe_trigger(("1", "Control Change", "7")) == "ch 1 · CC 7"


def _cell_texts(dialog: LayerMapDialog, column_title: str) -> list[str]:
    headers = [dialog.table.horizontalHeaderItem(c).text() for c in range(dialog.table.columnCount())]
    column = headers.index(column_title)
    return [dialog.table.item(r, column).text() for r in range(dialog.table.rowCount())]


def test_dialog_shows_functions_free_cells_and_missing_layers():
    config = _config()
    dialog = LayerMapDialog(lambda: config, [("DDJ-XP2", 64), ("XDJ-XZ", 16)], "DDJ-XP2")
    try:
        assert dialog.current_controller() == "DDJ-XP2"
        texts = _cell_texts(dialog, "PAD MODE 5")
        assert texts[0] == "Codfather ST · slot 0 (D1, D2, D3, D4)"
        assert _cell_texts(dialog, "PAD MODE 1")[0] == FREE_TEXT
        assert dialog.table.item(0, 0).data(Qt.ItemDataRole.UserRole) is None  # Pad 1 has no Normal layer
        assert dialog.table.item(0, 0).text() == NOT_APPLICABLE
        assert "16 mapped" in dialog.summary_label.text()

        dialog.section_combo.setCurrentText("DECK")
        assert dialog.table.columnCount() == 2  # Normal + SHIFT only
        assert all(dialog.table.verticalHeaderItem(r).text().startswith("DECK · ") for r in range(dialog.table.rowCount()))

        dialog.section_combo.setCurrentText(ALL_SECTIONS)
        dialog.controller_combo.setCurrentIndex(1)
        assert dialog.current_controller() == "XDJ-XZ"
        assert "partly free" in dialog.summary_label.text()
    finally:
        dialog.close()


def test_free_only_filter_and_refresh_follow_the_mapping():
    config = MidiConfig()
    dialog = LayerMapDialog(lambda: config, [("Korg nanoPAD2", 0)], None)
    try:
        assert dialog.table.rowCount() == 16
        # Map every scene of pad 1 through its own catalog triggers, then refresh.
        hits = [variant for cell in dialog.layer_map.rows[0].cells.values() for variant in cell.variants]
        for hit in hits:
            config.controls.append(
                Control(
                    channel=hit.channels[0],
                    event_type="Note On",
                    control=hit.data1,
                    userios=[UserIO(event="click", mappings=[MappingElement(tag="play", deck_id="0")])],
                )
            )
        dialog.free_only_checkbox.setChecked(True)
        assert dialog.table.rowCount() == 16  # still the old map
        dialog.refresh_button.click()
        assert dialog.table.rowCount() == 15
        assert dialog.layer_map.count(lm.STATUS_MAPPED) == 4
    finally:
        dialog.close()


def test_view_menu_opens_the_layer_map():
    window = MainWindow()
    try:
        view_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&View")
        assert window._layer_map_action in view_menu.actions()
        assert not window._layer_map_action.isEnabled()
        window.config = parse_file(FIXTURE)
        window._refresh_file_actions()
        assert window._layer_map_action.isEnabled()
        dialog = window._on_show_layer_map()
        assert dialog is not None
        names = [dialog.controller_combo.itemData(i) for i in range(dialog.controller_combo.count())]
        # Recognizing controllers first, then every other registered one.
        assert names[0] == "DDJ-XP2"
        assert set(names) == set(catalog.CONTROLLER_NAMES)
        assert dialog.table.rowCount() > 0
    finally:
        window.close()
