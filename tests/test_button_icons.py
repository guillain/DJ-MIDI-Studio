"""UX review: every text button gets an icon from its English text."""

from PySide6.QtWidgets import QDialogButtonBox, QPushButton, QWidget

from djmidi.gui.button_icons import ButtonIconDecorator, _sources, role_for_text


def test_roles_come_from_the_english_text():
    assert role_for_text("&Save report…") == "save"
    assert role_for_text("Add sync set…") == "add"
    assert role_for_text("Move up") == "up"
    assert role_for_text("Delete selected row(s)") == "delete"
    assert role_for_text("Zebra") is None


def test_the_decorator_sets_icons_but_leaves_glyph_and_iconed_buttons():
    decorator = ButtonIconDecorator("en")
    parent = QWidget()
    save, glyph, compact = QPushButton("Save report…", parent), QPushButton("● Rec", parent), QPushButton("x", parent)
    compact.setProperty("compact", True)
    assert decorator.decorate(save) and not save.icon().isNull()
    assert not decorator.decorate(glyph) and not decorator.decorate(compact)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    assert decorator.role_for(box.button(QDialogButtonBox.StandardButton.Cancel)) == "stop"


def test_a_translated_button_is_looked_up_on_its_english_source():
    sources = _sources("fr")
    french = next(translation for translation, source in sources.items() if source == "Save report…")
    decorator = ButtonIconDecorator("fr")
    assert decorator.role_for(QPushButton(french)) == "save"


def _icon_colour(button: QPushButton) -> str:
    """The colour of the icon's most opaque pixel."""
    image = button.icon().pixmap(32, 32).toImage()
    best = max(
        (image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())),
        key=lambda colour: colour.alpha(),
    )
    return best.name()


def test_line_icons_follow_a_theme_switch():
    """Light theme review: icons drawn in the dark theme's cyan used to stay
    so after switching to light (pale on light pills)."""
    from PySide6.QtWidgets import QApplication

    from djmidi.gui.action_groups import chip
    from djmidi.gui.layout_view import ControllerLayoutView
    from djmidi.gui.theme import apply_theme, colors

    app = QApplication.instance()
    try:
        apply_theme(app, "dark")
        parent = QWidget()
        decorated, chipped = QPushButton("Save report…", parent), chip(QPushButton("Add", parent), "add")
        ButtonIconDecorator("en").decorate(decorated)
        view = ControllerLayoutView(show_deck_filter=True)
        assert _icon_colour(decorated) == colors("dark")["icon"]
        apply_theme(app, "light")
        assert _icon_colour(decorated) == colors("light")["icon"] == _icon_colour(chipped)
        assert colors("light")["tab_bg"] in view._controller_tabs.styleSheet()
        assert colors("light")["button_bg"] in view._deck_combo.styleSheet()
        apply_theme(app, "dark")
        assert _icon_colour(chipped) == colors("dark")["icon"]
    finally:
        apply_theme(app, "dark")


def test_the_controller_canvas_is_light_on_the_light_theme():
    from PySide6.QtWidgets import QApplication

    from djmidi.gui.layout_view import ControllerLayoutView, scene_colours
    from djmidi.gui.theme import apply_theme

    app = QApplication.instance()
    try:
        apply_theme(app, "dark")
        view = ControllerLayoutView()
        assert view._scene.backgroundBrush().color().lightness() < 60
        apply_theme(app, "light")
        view._rebuild_scene()
        assert view._scene.backgroundBrush().color() == scene_colours()["background"]
        assert scene_colours()["background"].lightness() > 200
        assert scene_colours()["background"].name() in view._view.styleSheet()
    finally:
        apply_theme(app, "dark")
