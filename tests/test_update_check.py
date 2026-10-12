"""Qt-free release check (issue #193). Every test uses a fake fetcher: no network."""

import json
import logging
import urllib.error

from djmidi import update_check
from djmidi.update_check import (
    CHECK_INTERVAL_S,
    LATEST_RELEASE_URL,
    ReleaseInfo,
    check_for_update,
    is_check_due,
    is_newer,
    latest_release,
    parse_version,
)


def _payload(**overrides):
    payload = {
        "tag_name": "v0.48.70-some-feature",
        "name": "DJ MIDI Studio v0.48.70-some-feature",
        "html_url": "https://github.com/guillain/DJ-MIDI-Studio/releases/tag/v0.48.70-some-feature",
        "draft": False,
        "prerelease": False,
    }
    payload.update(overrides)
    return payload


def _fetcher(payload, seen=None):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        return json.dumps(payload).encode()

    return fetch


def test_parse_version_reads_the_numeric_prefix_and_ignores_the_slug():
    assert parse_version("v0.48.53-controller-sync-record") == (0, 48, 53)
    assert parse_version("0.48.65") == (0, 48, 65)
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("v0.48") is None
    assert parse_version("nightly") is None
    assert parse_version("") is None
    assert parse_version(None) is None


def test_is_newer_compares_numerically_not_as_text():
    assert is_newer("v0.48.100-x", "0.48.99")
    assert is_newer("v1.0.0-x", "0.99.99")
    assert not is_newer("v0.48.65-update-notice", "0.48.65")
    assert not is_newer("v0.48.60-old", "0.48.65")
    assert is_newer((0, 49, 0), "0.48.65")


def test_is_newer_is_false_when_either_side_is_unknown():
    assert not is_newer(None, "0.48.65")
    assert not is_newer("v0.49.0-x", None)
    assert not is_newer("garbage", "0.48.65")


def test_latest_release_parses_the_github_payload():
    seen = []
    release = latest_release(_fetcher(_payload(), seen))
    assert seen == [LATEST_RELEASE_URL]
    assert release == ReleaseInfo(
        tag="v0.48.70-some-feature",
        version=(0, 48, 70),
        url="https://github.com/guillain/DJ-MIDI-Studio/releases/tag/v0.48.70-some-feature",
        name="DJ MIDI Studio v0.48.70-some-feature",
    )


def test_latest_release_ignores_drafts_and_prereleases():
    assert latest_release(_fetcher(_payload(draft=True))) is None
    assert latest_release(_fetcher(_payload(prerelease=True))) is None


def test_latest_release_falls_back_to_the_releases_page_for_a_missing_url():
    release = latest_release(_fetcher(_payload(html_url=None)))
    assert release.url == update_check.RELEASES_PAGE_URL
    release = latest_release(_fetcher(_payload(html_url="javascript:alert(1)")))
    assert release.url == update_check.RELEASES_PAGE_URL


def test_latest_release_is_silent_on_network_and_format_errors(caplog):
    def offline(url):
        raise urllib.error.URLError("no route to host")

    def rate_limited(url):
        raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)

    with caplog.at_level(logging.DEBUG, logger="djmidi.update_check"):
        assert latest_release(offline) is None
        assert latest_release(rate_limited) is None
        assert latest_release(lambda url: b"<html>not json</html>") is None
        assert latest_release(lambda url: b"[]") is None
        assert latest_release(_fetcher(_payload(tag_name="nightly"))) is None
    assert all(record.levelno == logging.DEBUG for record in caplog.records)


def test_check_for_update_returns_only_a_newer_release():
    fetch = _fetcher(_payload())
    assert check_for_update("0.48.65", fetch).tag == "v0.48.70-some-feature"
    assert check_for_update("0.48.70", fetch) is None
    assert check_for_update("0.49.0", fetch) is None


def test_check_for_update_defaults_to_the_running_version(monkeypatch):
    monkeypatch.setattr(update_check, "current_version", lambda: "0.48.69")
    assert check_for_update(fetch=_fetcher(_payload())) is not None
    monkeypatch.setattr(update_check, "current_version", lambda: "0.48.70")
    assert check_for_update(fetch=_fetcher(_payload())) is None


def test_current_version_reads_the_installed_package():
    assert parse_version(update_check.current_version()) is not None


def test_is_check_due_limits_automatic_checks_to_once_a_day():
    now = 1_000_000.0
    assert is_check_due(None, now)
    assert not is_check_due(now - 60, now)
    assert not is_check_due(now - CHECK_INTERVAL_S + 1, now)
    assert is_check_due(now - CHECK_INTERVAL_S, now)
    assert is_check_due(now + 3600, now)  # clock moved back: check again
