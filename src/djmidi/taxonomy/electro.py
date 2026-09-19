"""Electro family seed categories, mined the same way as tek.py -- see
issue #127's investigation comment for the full real crate counts. Note
"DnB_jungle_pungle" is a distinct crate the maintainer keeps separate from
plain "Drum & Bass" (a jungle-flavored fusion, not a spelling variant), so
it is its own category rather than an alias of it."""

from __future__ import annotations

from djmidi.taxonomy._registry import Category, register

_FAMILY = "Electro"

register(Category(_FAMILY, "Drum & Bass", frozenset({"DnB", "D&B", "Drum and Bass"})))  # 8 real crates
register(Category(_FAMILY, "Dub", frozenset()))  # 8 real crates
register(Category(_FAMILY, "DnB_jungle_pungle", frozenset()))  # 6 real crates
register(Category(_FAMILY, "Ragga Jungle", frozenset()))  # 3 real crates
register(Category(_FAMILY, "Break beat", frozenset()))  # 2 real crates
