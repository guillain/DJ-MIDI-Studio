"""The documentation keeps one template (docs/README.md "Page template"):
every directory has a README.md index, every page a breadcrumb and a table of
contents, and every relative link (and #anchor) resolves -- so a moved or
renamed page can't silently leave dead links behind."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from djmidi.gui import main_window

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.rglob("*.md"))
LINKED_FILES = [ROOT / "README.md", *PAGES]

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)|<img [^>]*src=\"([^\"]+)\"")
_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, drop punctuation/emoji, spaces to '-'."""
    text = re.sub(r"`|\*", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in _FENCE.sub("", path.read_text(encoding="utf-8")).splitlines():
        match = re.match(r"#{1,6} (.+)", line)
        if match:
            slug = _slug(match.group(1))
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def _links(path: Path) -> list[str]:
    text = _FENCE.sub("", path.read_text(encoding="utf-8"))
    return [next(group for group in match.groups() if group) for match in _LINK.finditer(text)]


def test_every_docs_directory_has_a_readme_index():
    missing = [_rel(d) for d in [DOCS, *sorted(p for p in DOCS.rglob("*") if p.is_dir())] if not (d / "README.md").exists()]
    assert missing == []


@pytest.mark.parametrize("page", PAGES, ids=_rel)
def test_page_follows_the_template(page):
    lines = page.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# "), "first line must be the page title"
    assert any(line.startswith("📍 ") for line in lines[:12]), "missing the 📍 breadcrumb"
    assert "## Table of Contents" in lines, "missing ## Table of Contents"
    if page.name == "README.md":
        assert "## In this section" in lines, "an index page lists its pages under ## In this section"


@pytest.mark.parametrize("page", LINKED_FILES, ids=_rel)
def test_relative_links_and_anchors_resolve(page):
    broken = []
    for link in _links(page):
        if re.match(r"[a-z]+:", link):
            continue
        target, _, anchor = link.partition("#")
        path = (page.parent / target).resolve() if target else page
        if not path.exists() or (anchor and path.suffix == ".md" and anchor not in _anchors(path)):
            broken.append(link)
    assert broken == []


def test_help_menu_documents_exist():
    for _title, relative_path in [*main_window._LOCAL_HELP_DOCUMENTS, *main_window._LOCAL_CONTROLLER_DOCUMENTS]:
        assert (ROOT / relative_path).exists(), relative_path
