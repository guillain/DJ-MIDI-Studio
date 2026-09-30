"""Tek family seed categories, mined from the maintainer's real Serato
Subcrates (`_Serato_/Subcrates/*.crate`, a `Genre%%Subgenre%%Playlist`
naming convention the maintainer already curates by hand) -- see issue
#127's investigation comment for the full real crate counts this was mined
from. Alias sets are the acronym/casing variants the maintainer explicitly
flagged as needing federation, not an exhaustive thesaurus."""

from __future__ import annotations

from djmidi.taxonomy._registry import Category, register

_FAMILY = "Tek"

register(Category(_FAMILY, "Tribe", frozenset({"TribeTek", "Tribecore"})))  # 24 real crates
register(Category(_FAMILY, "HardTek", frozenset()))  # 22 real crates
register(Category(_FAMILY, "RaggaTek", frozenset({"Raggatek", "Reggaeton Tek", "Ragga Tek"})))  # 17 real crates
register(Category(_FAMILY, "HardCore", frozenset()))  # 10 real crates
register(Category(_FAMILY, "FrenchCore", frozenset()))  # 9 real crates
register(Category(_FAMILY, "PsyTrance", frozenset({"Psy", "Psytrance", "Psy-Trance"})))  # 6 real crates
register(Category(_FAMILY, "BarBass", frozenset()))  # 6 real crates
