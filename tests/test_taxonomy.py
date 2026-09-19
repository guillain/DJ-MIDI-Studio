from __future__ import annotations

import pytest

from djmidi import taxonomy
from djmidi.taxonomy import Category, resolve_category


def test_seeded_tek_family_round_trips():
    names = {category.name for category in taxonomy.all_categories() if category.family == "Tek"}
    assert names == {"Tribe", "HardTek", "RaggaTek", "HardCore", "FrenchCore", "PsyTrance", "BarBass"}


def test_seeded_electro_family_round_trips():
    names = {category.name for category in taxonomy.all_categories() if category.family == "Electro"}
    assert names == {"Drum & Bass", "Dub", "DnB_jungle_pungle", "Ragga Jungle", "Break beat"}


def test_families_lists_both_seeded_families():
    assert set(taxonomy.FAMILIES) == {"Tek", "Electro"}


def test_exact_match_on_crate_hint_ignores_playlist_suffix():
    match = resolve_category(raw_genre="Techno", crate_hint="Tek%%PsyTrance%%SomePlaylist")
    assert match.confidence == "exact"
    assert match.category.canonical == "Tek%%PsyTrance"


def test_exact_match_on_folder_hint_with_unknown_family_prefix():
    match = resolve_category(raw_genre=None, folder_hint="Unsorted/HardTek")
    assert match.confidence in {"exact", "alias"}
    assert match.category.name == "HardTek"


def test_crate_hint_wins_over_unreliable_raw_tag():
    """Mirrors the real investigation finding: tracks filed under
    Tek/PsyTrance can carry an unrelated TCON like "House"."""
    match = resolve_category(raw_genre="House", crate_hint="Tek%%PsyTrance")
    assert match.confidence == "exact"
    assert match.category.canonical == "Tek%%PsyTrance"


@pytest.mark.parametrize("alias", ["DnB", "D&B", "Drum and Bass", "Drum & Bass", "drum & bass"])
def test_drum_and_bass_aliases_federate(alias):
    match = resolve_category(raw_genre=alias)
    assert match.confidence in {"exact", "alias"}
    assert match.category.canonical == "Electro%%Drum & Bass"


@pytest.mark.parametrize("alias", ["Psy", "Psytrance", "PsyTrance", "Psy-Trance"])
def test_psytrance_aliases_federate(alias):
    match = resolve_category(raw_genre=alias)
    assert match.category.canonical == "Tek%%PsyTrance"


@pytest.mark.parametrize("alias", ["Tribe", "TribeTek", "Tribecore"])
def test_tribe_aliases_federate(alias):
    match = resolve_category(raw_genre=alias)
    assert match.category.canonical == "Tek%%Tribe"


@pytest.mark.parametrize("alias", ["Raggatek", "RaggaTek", "Reggaeton Tek", "Ragga Tek"])
def test_raggatek_aliases_federate(alias):
    match = resolve_category(raw_genre=alias)
    assert match.category.canonical == "Tek%%RaggaTek"


def test_dnb_jungle_pungle_stays_a_distinct_category_not_an_alias():
    """A real, separate crate the maintainer keeps apart from plain
    "Drum & Bass" -- must not collapse into it."""
    match = resolve_category(raw_genre="DnB_jungle_pungle")
    assert match.category.canonical == "Electro%%DnB_jungle_pungle"
    assert match.category.canonical != resolve_category(raw_genre="DnB").category.canonical


def test_fuzzy_suggestion_is_never_exact_or_alias():
    match = resolve_category(raw_genre="Drum n Bass")
    assert match.confidence == "fuzzy"
    assert match.category.canonical == "Electro%%Drum & Bass"
    assert match.score < 100.0


def test_fuzzy_suggestion_never_silently_becomes_exact_or_alias_confidence():
    """The hard requirement from issue #127: a fuzzy match must always be
    distinguishable from a confirmed one so a caller can gate on it."""
    match = resolve_category(raw_genre="Drum n Bass")
    assert match.confidence not in {"exact", "alias"}


def test_no_match_returns_none_confidence_and_no_category():
    match = resolve_category(raw_genre="Completely Unrelated Xyzzy Genre 12345")
    assert match.confidence == "none"
    assert match.category is None


def test_no_hints_at_all_returns_none():
    match = resolve_category(raw_genre=None)
    assert match.confidence == "none"
    assert match.category is None


def test_add_alias_then_resolves_as_alias():
    taxonomy.add_alias("Tek%%BarBass", "Bar Bass")
    try:
        match = resolve_category(raw_genre="Bar Bass")
        assert match.category.canonical == "Tek%%BarBass"
        assert match.confidence == "alias"
    finally:
        category = taxonomy.get_category("Tek%%BarBass")
        taxonomy.register(
            Category(category.family, category.name, frozenset(category.aliases - {"Bar Bass"})),
            replace=True,
        )


def test_merge_categories_absorbs_name_and_aliases_and_removes_absorbed():
    taxonomy.register(Category("Electro", "__TempDup__", frozenset({"__TempAlias__"})))
    try:
        merged = taxonomy.merge_categories("Electro%%Dub", "Electro%%__TempDup__")
        assert merged.canonical == "Electro%%Dub"
        assert "__TempDup__" in merged.aliases
        assert "__TempAlias__" in merged.aliases

        with pytest.raises(ValueError, match="Unknown category"):
            taxonomy.get_category("Electro%%__TempDup__")

        match = resolve_category(raw_genre="__TempDup__")
        assert match.category.canonical == "Electro%%Dub"
        assert match.confidence == "alias"
    finally:
        category = taxonomy.get_category("Electro%%Dub")
        restored = frozenset(category.aliases - {"__TempDup__", "__TempAlias__"})
        taxonomy.register(Category(category.family, category.name, restored), replace=True)
