from pathlib import Path

from djmidi.parser import parse_file

FIXTURE = Path(__file__).parent.parent / "data" / "xdj_xz-ddj_xp2-4decks.xml"


def test_parses_sample_file():
    config = parse_file(FIXTURE)
    assert config.app_version == " 4.0.9.3040"
    assert len(config.controls) == 640


def test_control_has_click_and_output_userio():
    config = parse_file(FIXTURE)
    control = config.controls[0]
    assert {u.event for u in control.userios} == {"click", "output"}


def test_mapping_tags_are_preserved():
    config = parse_file(FIXTURE)
    tags = {
        mapping.tag
        for control in config.controls
        for userio in control.userios
        for mapping in userio.mappings
    }
    assert tags == {
        "codfather_st",
        "codfather_fx",
        "auto_loop_specific_length",
        "auto_loop_roll_specific_length",
    }


def test_translation_and_alias_parsed():
    config = parse_file(FIXTURE)
    control = next(
        control
        for control in config.controls
        if any(
            mapping.tag == "codfather_st" and mapping.deck_id == "1"
            for userio in control.userios
            for mapping in userio.mappings
        )
    )
    click = next(u for u in control.userios if u.event == "click")
    mapping = click.mappings[0]
    assert mapping.tag == "codfather_st"
    assert mapping.deck_id == "1"
    translation = mapping.translations[0]
    assert translation.action_on == "press"
    assert translation.behaviour == "toggle"

    output = next(u for u in control.userios if u.event == "output")
    output_translation = output.mappings[0].translations[0]
    alias_names = {a.name for a in output_translation.aliases}
    assert alias_names == {"on", "off"}


def test_no_data_lost_in_extra_attrs_when_none_unexpected():
    config = parse_file(FIXTURE)
    for control in config.controls:
        assert control.extra_attrs == {}
