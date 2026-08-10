from pathlib import Path

from seratomidiconf.gui.mapping_group import build_mapping_groups
from seratomidiconf.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "ddj-xp2-custom-4-decks.xml"


def test_groups_collapse_the_10x_duplicates_in_the_real_file():
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    # 64 unique (channel, control, event_type) triggers x 2 userio events (click/output).
    assert len(groups) == 128
    click_groups = [g for g in groups if g.event == "click"]
    assert len(click_groups) == 64
    # Every click group is exactly the 10 duplicate <control> blocks for that trigger.
    assert all(len(g.members) == 10 for g in click_groups)


def test_group_members_share_the_same_trigger_and_target():
    config = parse_file(FIXTURE)
    groups = build_mapping_groups(config)
    for group in groups:
        for control, userio, mapping in group.members:
            assert control.channel == group.channel
            assert control.control == group.control_no
            assert control.event_type == group.event_type
            assert userio.event == group.event
            assert mapping.tag == group.tag
            assert mapping.deck_id == group.deck_id
            assert mapping.slot_id == group.slot_id


def test_editing_all_members_keeps_group_consistent():
    config = parse_file(FIXTURE)
    group = build_mapping_groups(config)[0]
    for _, _, mapping in group.members:
        mapping.deck_id = "9"
    assert {m.deck_id for _, _, m in group.members} == {"9"}
