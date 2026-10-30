"""Copy one deck's mappings onto another (phase 5 item 2)."""

from collections import Counter
from pathlib import Path

import pytest

from djmidi.deck_copy import (
    DeckCopyError,
    deck_channels,
    deck_ids,
    default_channel_map,
    plan_deck_copy,
)
from djmidi.exporter import to_xml_string
from djmidi.model import Control, MappingElement, MidiConfig, Translation, UserIO
from djmidi.parser import parse_file, parse_string

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def _control(channel, number, deck, tag="codfather_st", event="click"):
    mapping = MappingElement(tag=tag, deck_set="0", deck_id=deck, slot_id="0", translations=[Translation("press")])
    return Control(channel, "Note On", number, [UserIO(event, [mapping])])


def _decks(config):
    return Counter(
        (control.channel, control.control, mapping.deck_id)
        for control in config.controls
        for userio in control.userios
        for mapping in userio.mappings
    )


def test_the_real_fixture_has_one_channel_per_deck():
    config = parse_file(FIXTURE)
    assert deck_ids(config) == ["0", "1", "2", "3"]
    assert [deck_channels(config, deck) for deck in deck_ids(config)] == [["8"], ["10"], ["12"], ["14"]]
    assert default_channel_map(config, "0", "2") == {"8": "12"}


def test_a_copy_keeps_every_repeated_control_and_only_the_source_deck():
    shared = _control("1", "5", "0")
    shared.userios[0].mappings.append(MappingElement(tag="other", deck_id="3"))
    config = MidiConfig(controls=[shared, _control("1", "5", "0"), _control("1", "6", "0"), _control("2", "7", "1")])
    plan = plan_deck_copy(config, "0", "1", {"1": "2"})
    assert plan.copied == (("2", "Note On", "5"), ("2", "Note On", "6")) and plan.conflicts == ()
    added = plan.controls[len(config.controls):]
    assert len(added) == 3  # the two repeated copies of note 5 stay two
    assert all(m.deck_id == "1" and m.tag == "codfather_st" for c in added for u in c.userios for m in u.mappings)
    assert len(config.controls) == 4 and config.controls[0].userios[0].mappings[0].deck_id == "0"  # source untouched


def test_conflicts_are_skipped_or_replaced():
    target = _control("2", "5", "1", tag="old")
    target.userios[0].mappings.append(MappingElement(tag="keep", deck_id="3"))
    config = MidiConfig(controls=[_control("1", "5", "0"), _control("1", "6", "0"), target])
    skipped = plan_deck_copy(config, "0", "1", {"1": "2"})
    assert skipped.conflicts == (("2", "Note On", "5"),) and skipped.copied == (("2", "Note On", "6"),)
    replaced = plan_deck_copy(config, "0", "1", {"1": "2"}, replace=True)
    assert replaced.copied == (("2", "Note On", "5"), ("2", "Note On", "6"))
    tags = Counter(
        (control.control, mapping.deck_id, mapping.tag)
        for control in replaced.controls
        for userio in control.userios
        for mapping in userio.mappings
    )
    assert tags[("5", "1", "old")] == 0 and tags[("5", "3", "keep")] == 1 and tags[("5", "1", "codfather_st")] == 1


@pytest.mark.parametrize(
    ("source", "target", "channels", "message"),
    [("0", "0", None, "two different decks"), ("9", "1", None, "no mappings"), ("0", "1", {"1": "17"}, "1-16")],
)
def test_bad_requests_are_refused(source, target, channels, message):
    config = MidiConfig(controls=[_control("1", "5", "0")])
    with pytest.raises(DeckCopyError, match=message):
        plan_deck_copy(config, source, target, channels)


def test_replacing_deck_1_with_deck_0_on_the_real_fixture_round_trips():
    config = parse_file(FIXTURE)
    plan = plan_deck_copy(config, "0", "1", replace=True)
    assert len(plan.copied) == 16 and len(plan.conflicts) == 16
    reread = parse_string(to_xml_string(MidiConfig(config.app_version, plan.controls, config.extra_attrs)))
    decks = _decks(reread)
    deck0 = Counter({(c, n): k for (ch, n, d), k in decks.items() if d == "0" for c in [ch]})
    deck1 = Counter({(c, n): k for (ch, n, d), k in decks.items() if d == "1" for c in [ch]})
    assert {n: k for (_c, n), k in deck0.items()} == {n: k for (_c, n), k in deck1.items()}
    assert {c for c, _n in deck1} == {"10"}


def test_the_window_applies_a_copy_as_one_undo_step():
    from djmidi.gui.deck_copy_dialog import DeckCopyDialog
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    window._load_mapping_from_path(FIXTURE, software_id="serato")
    before = len(window.config.controls)
    dialog = window.open_deck_copy()
    assert isinstance(dialog, DeckCopyDialog)
    assert dialog.channel_map() == {"8": "10"}
    assert "Skipped" in dialog.preview.text() and not dialog.buttons.button(dialog.buttons.StandardButton.Ok).isEnabled()
    dialog.replace_box.setChecked(True)
    assert "replaced" in dialog.preview.text()
    dialog.accept()
    after = list(window.config.controls)
    assert window.undo_stack.count() == 1 and window.undo_stack.undoText().startswith("Copy deck 0")
    window.undo_stack.undo()
    assert len(window.config.controls) == before
    window.undo_stack.redo()
    assert window.config.controls == after


def test_only_serato_mappings_can_be_copied(monkeypatch):
    from djmidi.gui import main_window as main_window_module
    from djmidi.gui.main_window import MainWindow

    window = MainWindow()
    window.config = MidiConfig(controls=[_control("1", "5", "0")])
    window.software_id = "traktor"
    shown = []
    monkeypatch.setattr(main_window_module.QMessageBox, "information", lambda *args: shown.append(args))
    assert window.open_deck_copy() is None and shown
