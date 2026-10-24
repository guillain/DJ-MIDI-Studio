"""Shared text normalisation for the app's searches (issue #343).

The command palette and the reverse function search both tokenize their
index text and the query with `tokenize`, so accents never decide a match:
`préf`, `pref` and `PRÉF` all find "Préférences", `bibliotheque` finds
"Bibliothèque". Qt-free.

`normalize` = NFKD decomposition, combining marks dropped, casefold
(`ß` -> `ss`, ligatures and full-width letters folded by NFKD). `tokenize`
then keeps runs of Unicode letters and digits; the underscore is a separator
(Serato tags such as `auto_loop_roll` split into words), as is any
punctuation.
"""

from __future__ import annotations

import re
import unicodedata

_TOKEN_RE = re.compile(r"[^\W_]+")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return stripped.casefold()


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize(text))


__all__ = ["normalize", "tokenize"]
