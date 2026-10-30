"""The cheat sheet as an interactive web page (phase 6 item 6)."""

import json
import re
from pathlib import Path

from djmidi.gui import cheat_sheet
from djmidi.gui.cheat_sheet import Sheet, SheetEntry
from djmidi.gui.cheat_sheet_html import build_cheat_sheet_html
from djmidi.gui.geometry import ControlGeometry
from djmidi.parser import parse_file

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"
BOX = ControlGeometry(0.1, 0.2, 0.05, 0.04, "rect", "#ffffff")


def test_markers_carry_their_functions_and_text_is_escaped():
    pad = SheetEntry("PAD", "Pad 1", ('Loop "8"', "SHIFT: <x>"), BOX)
    knob = ControlGeometry(0.5, 0.5, 0.1, 0.1, "circle", "#ffffff")
    sheets = [
        Sheet("Acme", "Acme <pads>", "photo", (pad,), (knob,)),
        Sheet("Acme", "Acme — other mapped controls", "table", (SheetEntry("DECK", "PLAY", ("Play",)),)),
    ]
    html = build_cheat_sheet_html(sheets, lambda name: (b"\xff\xd8jpeg", "image/jpeg"), "set.xml", today="2026-10-30")
    assert html.startswith("<!doctype html>") and "set.xml — 2026-10-30" in html
    assert html.count("data:image/jpeg;base64,") == 1  # one photo per controller, embedded
    assert "<script" in html and "http" not in html.split("<style>")[1]  # no external resource
    marker = re.search(r'<button class="marker"[^>]*>', html).group(0)
    assert "left:10.000%;top:20.000%;width:5.000%;height:4.000%" in marker
    data = re.search(r'data-functions="([^"]*)"', marker).group(1)
    assert json.loads(data.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")) == [
        'Loop "8"', "SHIFT: <x>",
    ]  # fmt: skip
    assert 'class="marker round unmapped"' in html
    assert "<h2>Acme &lt;pads&gt;</h2>" in html and "<td>Play</td>" in html


def test_a_controller_without_a_photo_falls_back_to_a_table():
    sheets = [Sheet("Acme", "Acme", "photo", (SheetEntry("PAD", "Pad 1", ("Loop",), BOX),))]
    html = build_cheat_sheet_html(sheets, lambda name: None, words={"no_photo": "No picture"})
    assert "No picture" in html and "<td>Pad 1</td>" in html and "data:image" not in html


def test_the_real_fixture_exports_a_page_from_the_main_window(tmp_path):
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    try:
        window._load_mapping_from_path(FIXTURE, software_id="serato")
        assert window._cheat_sheet_web_action.isEnabled()
        path = window._on_export_cheat_sheet(["DDJ-XP2"], tmp_path / "sheet.html", web=True)
        html = path.read_text(encoding="utf-8")
        assert html.count("data:image/jpeg;base64,") == 1
        mapped = len(re.findall(r'<button class="marker', html))
        expected = sum(
            1 for sheet in cheat_sheet.build_sheets(parse_file(FIXTURE), ["DDJ-XP2"])
            for entry in sheet.entries if entry.geometry is not None
        )  # fmt: skip
        assert mapped == expected > 0
        assert path.stat().st_size < 3_000_000
    finally:
        window.close()
