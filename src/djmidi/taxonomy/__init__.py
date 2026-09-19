"""Genre/style taxonomy: a `Category` per genre/subgenre pairing (mined
from the maintainer's real Serato Subcrates, see issue #127), registered by
importing its family module (`tek.py`, `electro.py`) for the registration
side effect -- mirrors `catalog/`'s plugin-style registry pattern.

To add a new family: create `taxonomy/<family>.py`, call
`register(Category(family, name, aliases))` once per subcategory (see
`tek.py`), and drop the module in this package. `discover_plugins()`
(called once below) imports every non-underscore module here automatically
-- no import-list edit needed, unlike `catalog/__init__.py`'s manual step.

To federate a spelling/casing variant into an existing category:
`add_alias(canonical, alias)`. To merge two categories the maintainer
confirms are really the same thing: `merge_categories(keep, absorb)`.
Neither ever happens automatically -- `resolve_category()`'s own fuzzy
suggestions are exactly that, suggestions, never auto-applied.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

from djmidi.taxonomy._registry import (
    FUZZY_THRESHOLD,
    Category,
    CategoryMatch,
    Confidence,
    add_alias,
    all_categories,
    families,
    get_category,
    merge_categories,
    register,
    resolve_category,
    unregister,
)

_LOGGER = logging.getLogger(__name__)

_DISCOVERED = False


def discover_plugins() -> None:
    """Discovers built-in family modules. Idempotent so callers (tests,
    a future GUI) can safely refresh after registering something new."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module_info.name}")
    _LOGGER.info("Discovered %d taxonomy categories", len(all_categories()))


discover_plugins()


def __getattr__(name: str) -> object:
    # PEP 562: computed fresh from the live registry on every access, like
    # catalog.CONTROLLER_NAMES -- a category registered after this package
    # was imported is still picked up by every consumer of these two names.
    if name == "FAMILIES":
        return families()
    if name == "CATEGORIES":
        return all_categories()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CATEGORIES",
    "FAMILIES",
    "FUZZY_THRESHOLD",
    "Category",
    "CategoryMatch",
    "Confidence",
    "add_alias",
    "all_categories",
    "discover_plugins",
    "families",
    "get_category",
    "merge_categories",
    "register",
    "resolve_category",
    "unregister",
]
