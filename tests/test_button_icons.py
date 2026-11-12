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
