from __future__ import annotations

import pytest

from djmidi import taxonomy
from djmidi.taxonomy._registry import Category, register, unregister


def test_builtin_families_are_registered_at_import():
    assert "Tek" in taxonomy.FAMILIES
    assert "Electro" in taxonomy.FAMILIES


def test_registering_twice_raises():
    category = Category("__TestFamily__", "__TestCategory__")
    register(category)
    try:
        with pytest.raises(ValueError, match="already registered"):
            register(category)
    finally:
        unregister(category.canonical)


def test_register_replace_true_overwrites_existing():
    first = Category("__TestFamily__", "__TestCategory__", frozenset({"one"}))
    second = Category("__TestFamily__", "__TestCategory__", frozenset({"two"}))
    register(first)
    try:
        register(second, replace=True)
        assert taxonomy.get_category(first.canonical) is second
        assert taxonomy.get_category(first.canonical).aliases == frozenset({"two"})
    finally:
        unregister(first.canonical)


def test_unregister_is_a_noop_for_unknown_canonical():
    unregister("__NoSuchCategory__")


def test_unknown_category_raises():
    with pytest.raises(ValueError, match="Unknown category"):
        taxonomy.get_category("__NoSuchCategory__")


def test_registering_a_new_category_is_picked_up_by_resolve_without_touching_init():
    """The whole point of the registry: adding a category is `register(...)`
    plus (normally) one new family module -- nothing else needs to change
    for it to show up in `all_categories()`/`resolve_category()`."""
    category = Category("__TestFamily2__", "__TestCategory2__", frozenset({"__TestAlias2__"}))
    register(category)
    try:
        assert category in taxonomy.all_categories()

        alias_match = taxonomy.resolve_category(raw_genre="__TestAlias2__")
        assert alias_match.category == category
        assert alias_match.confidence == "alias"

        exact_match = taxonomy.resolve_category(raw_genre="__TestFamily2__%%__TestCategory2__")
        assert exact_match.category == category
        assert exact_match.confidence == "exact"
    finally:
        unregister(category.canonical)


def test_discover_plugins_is_idempotent():
    before = len(taxonomy.all_categories())
    taxonomy.discover_plugins()
    assert len(taxonomy.all_categories()) == before
