"""Per-control MIDI remapping over the routing layer (issue #368)."""

import json

import pytest

from djmidi.midi_api import MidiMessage
from djmidi.midi_router import (
    BLOCK,
    CC,
    NOTE,
    MidiRoute,
    MidiRouter,
    MidiValueTransform,
    RemapRule,
)
from djmidi.midi_routing_session import MidiRoutingSession


def _msg(*data):
    return MidiMessage(data=bytes(data), received_time=0.0)


def test_note_to_cc_keeps_the_value_and_the_release():
    rule = RemapRule(NOTE, 1, 40, CC, 2, 7)
    assert rule.matches(_msg(0x90, 40, 100)) and rule.matches(_msg(0x80, 40, 64))
    assert not rule.matches(_msg(0x91, 40, 100)) and not rule.matches(_msg(0xB0, 40, 100))
    assert rule.apply(_msg(0x90, 40, 100)).data == bytes((0xB1, 7, 100))
    assert rule.apply(_msg(0x80, 40, 64)).data == bytes((0xB1, 7, 0))  # release -> 0
    assert rule.label() == "Note 40 ch 1 → CC 7 ch 2"


def test_cc_to_note_and_block():
    rule = RemapRule(CC, 3, 20, NOTE, 1, 60)
    assert rule.apply(_msg(0xB2, 20, 127)).data == bytes((0x90, 60, 127))
    assert rule.apply(_msg(0xB2, 20, 0)).data == bytes((0x80, 60, 0))
    blocked = RemapRule(NOTE, 1, 40, BLOCK)
    assert blocked.apply(_msg(0x90, 40, 100)) is None and blocked.label() == "Note 40 ch 1 → blocked"
    with pytest.raises(ValueError):
        RemapRule(NOTE, 17, 40, CC)
    with pytest.raises(ValueError):
        RemapRule("pitch", 1, 40, CC)


def test_remaps_win_over_stream_wide_values_and_block_drops():
    transform = MidiValueTransform(
        channel_override=5, data1_offset=12, remaps=(RemapRule(NOTE, 1, 40, CC, 1, 7), RemapRule(NOTE, 1, 41, BLOCK))
    )
    assert transform.apply(_msg(0x90, 40, 100)).data == bytes((0xB0, 7, 100))
    assert transform.apply(_msg(0x90, 41, 100)) is None
    assert transform.apply(_msg(0x90, 42, 100)).data == bytes((0x94, 54, 100))  # untouched rules: stream values

    router = MidiRouter()
    router.add_route(MidiRoute("CTRL", "OUT", transform=transform))
    sent = []
    assert router.route_message("CTRL", _msg(0x90, 41, 100), lambda port, message: sent.append(message)) == 0
    assert router.stats.dropped == 1 and sent == []
    assert router.route_message("CTRL", _msg(0x90, 40, 100), lambda port, message: sent.append(message)) == 1


def test_session_opens_the_remap_port_as_a_virtual_output():
    opened = {}
    router = MidiRouter()
    router.add_route(MidiRoute("CTRL", "DJ MIDI Studio Remap"))
    session = MidiRoutingSession(
        router,
        input_opener=lambda name: opened.setdefault(name, "real-in"),
        output_opener=lambda name: opened.setdefault(name, "real-out"),
        virtual_output_opener=lambda name: opened.setdefault(name, "virtual-out"),
    )
    session.set_virtual_output_ids({"DJ MIDI Studio Remap"})
    session.start()
    try:
        assert opened == {"CTRL": "real-in", "DJ MIDI Studio Remap": "virtual-out"}
        with pytest.raises(RuntimeError):
            session.set_virtual_output_ids(())
    finally:
        session.stop()


def test_dialog_edits_learns_and_saves_remaps():
    from djmidi.gui.midi_route_transform_dialog import MidiRouteTransformDialog
    from djmidi.midi_io import MidiEvent

    dialog = MidiRouteTransformDialog(
        MidiValueTransform(remaps=(RemapRule(NOTE, 1, 40, CC, 2, 7),)), ensure_listening=lambda: True
    )
    assert dialog.rules() == (RemapRule(NOTE, 1, 40, CC, 2, 7),)
    dialog.remap_table.clearSelection()
    dialog.remap_table.setCurrentCell(-1, -1)
    dialog.learn_button.click()  # no row selected: adds one and learns into it
    assert dialog.is_learning
    assert not dialog.feed_learn_event(MidiEvent("in", "3", "Note On", "12", "0", 0.0, "X"))  # a release
    assert dialog.feed_learn_event(MidiEvent("in", "3", "Control Change", "12", "64", 0.0, "X"))
    learned = dialog.rules()[1]
    assert (learned.source_kind, learned.source_channel, learned.source_data1) == (CC, 3, 12)
    target = dialog.remap_table.cellWidget(1, 3)
    target.setCurrentIndex(target.findData(BLOCK))
    dialog._on_accept()
    assert dialog.result_transform().remaps[1].target_kind == BLOCK

    duplicate = MidiRouteTransformDialog(None)
    duplicate.add_rule(RemapRule(NOTE, 1, 40, CC))
    duplicate.add_rule(RemapRule(NOTE, 1, 40, BLOCK))
    duplicate._on_accept()
    assert duplicate.result_transform() is None and "same control" in duplicate.status.text()


def test_routes_with_remaps_survive_a_save_and_reload():
    from djmidi.gui.midi_routing_view import (
        REMAP_PORT_NAME,
        _route_from_dict,
        _route_to_dict,
    )

    route = MidiRoute("CTRL", REMAP_PORT_NAME, transform=MidiValueTransform(remaps=(RemapRule(NOTE, 1, 40, BLOCK),)))
    assert _route_from_dict(_route_to_dict(route)) == route
    raw = json.loads(json.dumps(_route_to_dict(route)))  # as stored in QSettings
    raw["transform"]["remaps"].append({"source_kind": "bad"})
    assert _route_from_dict(raw) == route  # an unreadable rule is skipped
