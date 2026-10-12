"""Checks GitHub for a newer DJ MIDI Studio release (issue #193).

Qt-free and read-only: it asks the GitHub "latest release" API which tag is
current and compares its numeric prefix with the running version. It never
downloads or installs anything — the GUI only shows a notice with a link to
the release page.

Release tags are milestone tags shaped ``vX.Y.Z-slug`` (e.g.
``v0.48.53-controller-sync-record``); only ``X.Y.Z`` is compared, the slug is
ignored. GitHub's ``/releases/latest`` endpoint already excludes drafts and
prereleases, and :func:`latest_release` re-checks both flags defensively.

Every failure (offline, timeout, rate limit, unexpected JSON) yields ``None``
and is only logged at debug level: an update check must never bother a DJ
who is offline at a gig.
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

LATEST_RELEASE_URL = "https://api.github.com/repos/guillain/DJ-MIDI-Studio/releases/latest"
RELEASES_PAGE_URL = "https://github.com/guillain/DJ-MIDI-Studio/releases"
REQUEST_TIMEOUT_S = 5.0
# Automatic checks run at most once per this interval (the menu action ignores it).
CHECK_INTERVAL_S = 24 * 60 * 60

_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)")

Version = tuple[int, int, int]
# Takes a URL, returns the response body; raises on any network error.
Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    version: Version
    url: str
    name: str = ""


def parse_version(tag: str | None) -> Version | None:
    """``"v0.48.53-controller-sync-record"`` / ``"0.48.53"`` -> ``(0, 48, 53)``."""
    if not tag:
        return None
    match = _VERSION_RE.match(tag)
    if match is None:
        return None
    return int(match[1]), int(match[2]), int(match[3])


def is_newer(remote: str | Version | None, local: str | Version | None) -> bool:
    """True only when both versions parse and ``remote`` is strictly higher."""
    remote_version = remote if isinstance(remote, tuple) else parse_version(remote)
    local_version = local if isinstance(local, tuple) else parse_version(local)
    if remote_version is None or local_version is None:
        return False
    return remote_version > local_version


def current_version() -> str | None:
    """The running app's version from its package metadata, or None if unknown."""
    try:
        return importlib.metadata.version("djmidi")
    except importlib.metadata.PackageNotFoundError:
        return None


def _default_fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"DJ-MIDI-Studio/{current_version() or 'unknown'} (update check)",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:  # nosec B310 - fixed https URL
        return response.read()


def latest_release(fetch: Fetcher | None = None) -> ReleaseInfo | None:
    """The latest published release, or None on any failure (logged at debug)."""
    fetch = fetch or _default_fetch
    try:
        payload = json.loads(fetch(LATEST_RELEASE_URL))
    except Exception as exc:  # noqa: BLE001 - offline/rate limit/bad JSON are all silent
        _LOGGER.debug("Update check failed: %s", exc)
        return None
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        _LOGGER.debug("Update check: no usable published release in the response")
        return None
    tag = payload.get("tag_name")
    version = parse_version(tag if isinstance(tag, str) else None)
    if version is None:
        _LOGGER.debug("Update check: unrecognized release tag %r", tag)
        return None
    url = payload.get("html_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        url = RELEASES_PAGE_URL
    name = payload.get("name")
    return ReleaseInfo(tag=tag, version=version, url=url, name=name if isinstance(name, str) else "")


def check_for_update(local: str | None = None, fetch: Fetcher | None = None) -> ReleaseInfo | None:
    """The latest release when it is newer than ``local`` (default: running version)."""
    release = latest_release(fetch)
    if release is None:
        return None
    return release if is_newer(release.version, local or current_version()) else None


def is_check_due(last_check: float | None, now: float, interval: float = CHECK_INTERVAL_S) -> bool:
    """Whether an automatic check should run, given the last check's epoch time."""
    if last_check is None or last_check > now:  # never checked, or a clock moved back
        return True
    return now - last_check >= interval
