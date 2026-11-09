"""Atelier step 6 (issue #413): remapping one control onto another."""

import pytest

from djmidi import catalog
from djmidi.atelier import feature_by_id
from djmidi.atelier.remap import describe_remap, remap_rule, with_remap, without_remap
from djmidi.midi_api import MidiMessage
from djmidi.midi_router import MidiValueTransform, RemapRule

SYNC = "deck.beat-sync@1"  # DDJ-XP2 deck 1 BEAT SYNC: ch 1 note 88


@pytest.fixture(autouse=True)
def _every_controller_enabled():
    catalog.set_enabled_plugin_ids(None)


def _feature(feature_id):
    feature = feature_by_id("DDJ-XP2", feature_id)
    assert feature is not None, feature_id
    return feature


def test_a_rule_from_two_features_and_its_effect_on_a_message():
    source, target = _feature(SYNC), _feature("deck.quantize@1")
    rule = remap_rule(source, target)
    assert (rule.source_kind, rule.source_channel, rule.source_data1) == ("note", 1, 88)
    assert (rule.target_kind, rule.target_channel, rule.target_data1) == ("note", 1, target.input.number)
    transform = with_remap(None, rule)
    pressed = transform.apply(MidiMessage(bytes([0x90, 88, 127]), 0.0))
    assert pressed.data == bytes([0x90, target.input.number, 127])


def test_block_drops_the_source_control():
    transform = with_remap(None, remap_rule(_feature(SYNC), None))
    assert transform.apply(MidiMessage(bytes([0x90, 88, 127]), 0.0)) is None


def test_a_new_rule_replaces_the_one_for_the_same_source_in_place():
    first = RemapRule("cc", 16, 1, "cc", 16, 2)
    old = remap_rule(_feature(SYNC), None)
    transform = MidiValueTransform(invert_data2=True, remaps=(old, first))
    updated = with_remap(transform, remap_rule(_feature(SYNC), _feature("deck.quantize@1")))
    assert updated.invert_data2 is True  # the rest of the transform is kept
    assert updated.remaps[1] == first and updated.remaps[0].target_kind == "note"
    assert without_remap(updated, first).remaps == (updated.remaps[0],)


def test_rules_read_by_their_features():
    rule = remap_rule(_feature(SYNC), _feature("deck.quantize@1"))
    assert describe_remap("DDJ-XP2", rule) == "BEAT SYNC (deck 1) → QUANTIZE (deck 1)"
    assert describe_remap("DDJ-XP2", remap_rule(_feature(SYNC), None)) == "BEAT SYNC (deck 1) → blocked"
    assert describe_remap("DDJ-XP2", RemapRule("cc", 16, 127, "block")) == "CC ch 16 · 127 → blocked"


# --- the Atelier's remap panel --------------------------------------------


def _atelier(transforms):
    from djmidi.gui.atelier_view import AtelierView

    view = AtelierView()
    view.route_labels_provider = lambda: ["DDJ-XP2 → IAC Driver Bus 1"]
    view.route_transform_provider = lambda index: transforms.get(index)
    view.routeTransformChanged.connect(lambda index, transform: transforms.__setitem__(index, transform))
    view.controller_combo.setCurrentText("DDJ-XP2")
    view.refresh_routes()
    return view


def test_two_clicks_remap_a_control_onto_another():
    transforms = {}
    view = _atelier(transforms)
    view.select_feature(SYNC)
    assert view.remap_button.isEnabled()
    view.start_remap()
    target = view.pick_key(("DDJ-XP2", "DECK", "QUANTIZE"))
    assert target is not None
    [rule] = transforms[0].remaps
    assert (rule.source_data1, rule.target_data1) == (88, target.input.number)
    assert view.remap_list.item(0).text() == "BEAT SYNC (deck 1) → QUANTIZE (deck 1)"


def test_block_and_remove():
    transforms = {}
    view = _atelier(transforms)
    view.select_feature(SYNC)
    view.block_button.click()
    assert transforms[0].remaps[0].target_kind == "block"
    view.remap_list.setCurrentRow(0)
    view.remove_remap_button.click()
    assert transforms[0].remaps == ()


def test_no_route_disables_the_panel():
    from djmidi.gui.atelier_view import AtelierView

    view = AtelierView()
    view.controller_combo.setCurrentText("DDJ-XP2")
    view.refresh_routes()
    view.select_feature(SYNC)
    assert not view.route_combo.isEnabled() and not view.remap_button.isEnabled()


def test_the_main_window_writes_the_remap_into_the_route_in_place():
    from djmidi.gui.main_window import MainWindow
    from djmidi.midi_router import MidiRoute

    window = MainWindow()
    router = window.midi_routing_view.router
    router.add_route(MidiRoute("DDJ-XP2", "IAC Driver Bus 1"))
    router.add_route(MidiRoute("XDJ-XZ", "IAC Driver Bus 2"))
    window.midi_routing_view._refresh_routes_table()
    window.midi_routing_view.routesChanged.emit()
    view = window.atelier_view
    view.controller_combo.setCurrentText("DDJ-XP2")
    view.route_combo.setCurrentIndex(0)
    view.select_feature(SYNC)
    view.block_button.click()
    first, second = router.routes
    assert first.source_port_id == "DDJ-XP2" and first.transform.remaps[0].target_kind == "block"
    assert second.source_port_id == "XDJ-XZ"  # the edited route kept its place
    window.close()
