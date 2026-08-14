from PySide6.QtWidgets import QApplication

from seratomidiconf.gui.main_window import MainWindow


def _ratio(splitter) -> float:
    sizes = splitter.sizes()
    total = sizes[0] + sizes[1]
    return sizes[0] / total if total else 0.0


def test_pair_splitters_start_near_half_height():
    window = MainWindow()
    window.show()
    QApplication.processEvents()

    for splitter in window._pair_splitters:
        assert abs(_ratio(splitter) - 0.5) < 0.08

    window.close()


def test_pair_splitter_ratio_is_kept_on_window_resize():
    window = MainWindow()
    window.show()
    QApplication.processEvents()

    splitter = window._pair_splitters[0]
    splitter.setSizes([200, 400])
    window._remember_pair_ratio(splitter)
    QApplication.processEvents()
    before = _ratio(splitter)

    window.resize(1600, 900)
    QApplication.processEvents()
    after = _ratio(splitter)

    assert abs(after - before) < 0.08
    window.close()


def test_intro_drilldown_switches_tab_and_controller():
    window = MainWindow()
    window.show()
    QApplication.processEvents()

    window._on_intro_drilldown_requested("images", "XDJ-XZ")
    QApplication.processEvents()

    assert window.left_tabs.currentIndex() == window._tab_indexes["images"]
    assert window.layout_view._controller == "XDJ-XZ"
    assert window.deck_layout_view._controller == "XDJ-XZ"
    assert window.controller_layout_view._controller == "XDJ-XZ"

    window.close()


