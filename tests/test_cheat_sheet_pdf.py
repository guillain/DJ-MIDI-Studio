"""Cheat-sheet PDF rendering and the File -> Export entry (issue #182)."""

import re
from pathlib import Path

from PySide6.QtCore import Qt

from djmidi.gui import cheat_sheet as cs
from djmidi.gui.cheat_sheet_dialog import CheatSheetExportDialog
from djmidi.gui.cheat_sheet_pdf import render_sheet_image, write_cheat_sheet_pdf
from djmidi.gui.main_window import MainWindow
from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"
_PAGE_RE = re.compile(rb"/Type\s*/Page(?!s)")


def _page_count(pdf: Path) -> int:
    return len(_PAGE_RE.findall(pdf.read_bytes()))


def test_pdf_has_one_page_per_sheet_on_the_real_fixture(tmp_path):
    sheets = cs.build_sheets(parse_file(FIXTURE), ["DDJ-XP2", "XDJ-XZ"])
    target = tmp_path / "cheat.pdf"
    pages = write_cheat_sheet_pdf(target, sheets, FIXTURE.name)
    assert pages == 3  # two photo pages + the function-name glossary
    assert target.read_bytes().startswith(b"%PDF")
    assert target.stat().st_size > 50_000  # the two photos are embedded
    assert _page_count(target) == 3


def test_long_tables_paginate(tmp_path):
    # DDJ-800 has no geometry: its 64 mapped triggers go to a table that
    # doesn't fit on one A4 page.
    sheets = cs.build_sheets(parse_file(FIXTURE), ["DDJ-800"])
    target = tmp_path / "table.pdf"
    pages = write_cheat_sheet_pdf(target, sheets)
    assert pages == 3  # two table pages + the function-name glossary
    assert _page_count(target) == 3


def test_rendered_page_draws_the_photo_and_labels():
    sheet = cs.build_sheets(parse_file(FIXTURE), ["DDJ-XP2"])[0]
    image = render_sheet_image(sheet, dpi=60)
    assert not image.isNull()
    assert image.width() > image.height()  # A4 landscape
    colors = {image.pixelColor(x, image.height() // 2).name() for x in range(0, image.width(), 7)}
    assert len(colors) > 10  # not a blank page


def test_dialog_lists_candidates_and_preselects(geometry_free_controller):
    dialog = CheatSheetExportDialog([("DDJ-XP2", 64), (geometry_free_controller, 64)], {"DDJ-XP2"})
    assert dialog.selected_controllers() == ["DDJ-XP2"]
    ok = dialog._buttons.button(dialog._buttons.StandardButton.Ok)
    assert ok.isEnabled()
    dialog._list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert dialog.selected_controllers() == []
    assert not ok.isEnabled()
    assert "table" in dialog._list.item(1).text()


def test_file_export_menu_offers_the_cheat_sheet(tmp_path):
    window = MainWindow()
    try:
        file_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&File")
        export_menu = next(a.menu() for a in file_menu.actions() if a.text() == "&Export")
        assert window._cheat_sheet_action in export_menu.actions()
        assert not window._cheat_sheet_action.isEnabled()
        window.config = parse_file(FIXTURE)
        window.current_path = FIXTURE
        window._refresh_file_actions()
        assert window._cheat_sheet_action.isEnabled()
        target = tmp_path / "sheet.pdf"
        assert window._on_export_cheat_sheet(["XDJ-XZ"], target) == target
        assert _page_count(target) == 2  # the photo page + the function-name glossary
        assert "2 page" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_preselection_prefers_connected_and_shown_controllers(monkeypatch):
    from djmidi.gui import main_window as main_window_mod

    ports: list[str] = []
    monkeypatch.setattr(main_window_mod, "list_input_ports", lambda: ports)
    window = MainWindow()
    try:
        assert window.controller_image_view.set_controller("XDJ-XZ")
        assert window._cheat_sheet_preselection(["DDJ-XP2", "XDJ-XZ"]) == {"XDJ-XZ"}
        # Nothing connected or shown among the candidates: the best match.
        assert window._cheat_sheet_preselection(["DDJ-800", "DDJ-1000"]) == {"DDJ-800"}
        ports.append("DDJ-XP2")
        assert window._cheat_sheet_preselection(["DDJ-XP2", "XDJ-XZ"]) == {"DDJ-XP2", "XDJ-XZ"}
    finally:
        window.close()
